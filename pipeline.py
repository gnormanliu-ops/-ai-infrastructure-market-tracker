"""Daily market data tracker. Rebuilds history exclusively from preserved raw CSV files."""
import argparse
import csv
import gzip
import io
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HEADERS = ["date", "item_id", "item", "source", "sector", "close_usd", "volume_shares", "open_usd", "high_usd", "low_usd", "market_date"]


def companies():
    return json.loads((ROOT / "companies.json").read_text(encoding="utf-8"))


def parse_csv_bytes(content, ticker, name, sector, run_date):
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"Date", "Close", "Volume"}.issubset(reader.fieldnames):
        raise ValueError("Source did not return OHLCV CSV")
    rows = [r for r in reader if r.get("Date") and r["Date"] <= run_date and r.get("Close") not in ("", "N/D", None)]
    if not rows:
        raise ValueError("No market close available on/before run date")
    r = max(rows, key=lambda x: x["Date"])
    def num(key):
        return str(float(r[key])) if r.get(key) not in (None, "") else ""
    return {"date":run_date, "item_id":ticker, "item":name, "source":"Stooq", "sector":sector,
            "close_usd":num("Close"), "volume_shares":str(int(float(r["Volume"]))) if r.get("Volume") else "",
            "open_usd":num("Open"), "high_usd":num("High"), "low_usd":num("Low"), "market_date":r["Date"]}


def fetch_csv(ticker, run_date):
    start = (datetime.strptime(run_date, "%Y-%m-%d") - timedelta(days=12)).strftime("%Y%m%d")
    end = run_date.replace("-", "")
    url = "https://stooq.com/q/d/l/?" + urlencode({"s":ticker.lower()+".us", "d1":start, "d2":end, "i":"d"})
    req = Request(url, headers={"User-Agent":"FDA-Course-Data-Tracker/1.0 (educational research)", "Accept":"text/csv"})
    with urlopen(req, timeout=25) as resp:
        content = resp.read()
    if len(content) > 500_000:
        raise ValueError("Unexpectedly large response")
    return content



def parse_yahoo_json(content, ticker, name, sector, run_date):
    """Convert an unmodified Yahoo chart JSON response to one valid daily observation."""
    payload = json.loads(content.decode("utf-8-sig"))
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        raise ValueError("Yahoo chart response has no results: " + str(chart.get("error"))[:100])
    result = results[0]
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [])
    if not quotes:
        raise ValueError("Yahoo chart response missing OHLCV")
    q = quotes[0]
    tz_offset = int((result.get("meta") or {}).get("gmtoffset") or 0)
    bars = []
    for i, stamp in enumerate(timestamps):
        trading_day = datetime.fromtimestamp(int(stamp) + tz_offset, timezone.utc).date().isoformat()
        close = (q.get("close") or [])
        volume = (q.get("volume") or [])
        if trading_day > run_date or i >= len(close) or i >= len(volume):
            continue
        if close[i] is None or volume[i] is None or float(close[i]) <= 0 or int(volume[i]) < 0:
            continue
        bars.append((trading_day, i))
    if not bars:
        raise ValueError("Yahoo chart response has no valid market close")
    trading_day, i = max(bars)
    def price(k):
        a = q.get(k) or []
        return str(float(a[i])) if len(a) > i and a[i] is not None else ""
    return {"date":run_date,"item_id":ticker,"item":name,"source":"Yahoo Finance","sector":sector,
            "close_usd":price("close"),"volume_shares":str(int(q["volume"][i])),
            "open_usd":price("open"),"high_usd":price("high"),"low_usd":price("low"),
            "market_date":trading_day}


def fetch_yahoo(ticker, run_date):
    """Download Yahoo public daily chart JSON; try both official chart hosts."""
    last_error = None
    for host in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        url = ("https://" + host + "/v8/finance/chart/" + quote(ticker) +
               "?range=1mo&interval=1d")
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json", "Referer": "https://finance.yahoo.com/"
        })
        try:
            with urlopen(req, timeout=12) as resp:
                content = resp.read(250_001)
            if len(content) > 250_000:
                raise ValueError("Unexpectedly large Yahoo response")
            parse_yahoo_json(content, ticker, ticker, "test", run_date)
            return content
        except Exception as exc:
            last_error = exc
    raise RuntimeError("Both Yahoo hosts failed: " + str(last_error)[:160])


TV_EXCHANGES = {"CEG":"NASDAQ","MU":"NASDAQ"}
TV_COLUMNS = ["close","volume","open","high","low"]

def fetch_tradingview():
    """One raw JSON scan for exactly the 15 selected US tickers."""
    tickers = [TV_EXCHANGES.get(c["ticker"],"NYSE") + ":" + c["ticker"] for c in companies()]
    payload = {"symbols":{"tickers":tickers,"query":{"types":[]}},
               "columns":TV_COLUMNS}
    req = Request("https://scanner.tradingview.com/america/scan",
                  data=json.dumps(payload).encode("utf-8"),
                  headers={"Content-Type":"application/json",
                           "User-Agent":"Mozilla/5.0",
                           "Origin":"https://www.tradingview.com",
                           "Referer":"https://www.tradingview.com/"},method="POST")
    with urlopen(req,timeout=20) as response:
        content = response.read(250_001)
    if len(content)>250_000:
        raise ValueError("TradingView response too large")
    parsed = json.loads(content)
    if not isinstance(parsed.get("data"),list):
        raise ValueError("TradingView response has no data rows")
    return content

def parse_tradingview_json(content,ticker,name,sector,run_date):
    """TradingView scanner returns a snapshot, not a timestamped EOD bar."""
    parsed = json.loads(content.decode("utf-8-sig"))
    matches = [r for r in parsed.get("data",[]) if r.get("s","").split(":")[-1]==ticker]
    if not matches:
        raise ValueError("Ticker missing from TradingView scan")
    d=matches[0].get("d") or []
    if len(d)<5 or d[0] is None or d[1] is None or float(d[0])<=0:
        raise ValueError("TradingView missing valid close/volume")
    def number(i):
        return str(float(d[i])) if len(d)>i and d[i] is not None else ""
    return {"date":run_date,"item_id":ticker,"item":name,"source":"TradingView","sector":sector,
            "close_usd":number(0),"volume_shares":str(int(float(d[1]))),
            "open_usd":number(2),"high_usd":number(3),"low_usd":number(4),
            "market_date":""}

def download(run_date, fetcher=None, pause=0.5):
    """Yahoo JSON first, Stooq CSV fallback. Retain each successful original response."""
    folder = DATA / "raw" / run_date
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    tv_content = None
    tv_error = None
    if fetcher is None:
        try:
            tv_content = fetch_tradingview()
        except Exception as exc:
            tv_error = str(exc)[:130]
    for c in companies():
        ticker = c["ticker"]
        targets = [folder / f"yahoo_{ticker}.json.gz", folder / f"stooq_{ticker}.csv.gz", folder / f"tradingview_{ticker}.json.gz"]
        # A second run on the same date must not reuse the earlier snapshot.
        for target in targets:
            target.unlink(missing_ok=True)
        attempts = []
        if tv_content is not None and fetcher is None:
            try:
                parse_tradingview_json(tv_content,ticker,c["name"],c["sector"],run_date)
                with targets[2].open("wb") as stream:
                    with gzip.GzipFile(fileobj=stream,mode="wb",mtime=0) as comp:
                        comp.write(tv_content)
                results.append({"name":f"TradingView {ticker}","ok":True,"count":1})
                if pause: time.sleep(pause)
                continue
            except Exception as exc:
                attempts.append("TradingView: "+str(exc)[:110])
        elif tv_error:
            attempts.append("TradingView: "+tv_error)
        sources = (
            [("Stooq", fetcher, parse_csv_bytes, targets[1])]
            if fetcher is not None else
            [("Yahoo Finance", fetch_yahoo, parse_yahoo_json, targets[0]),
             ("Stooq", fetch_csv, parse_csv_bytes, targets[1])]
        )
        succeeded = False
        for source_name, fn, parser, target in sources:
            try:
                raw = fn(ticker, run_date)
                parser(raw, ticker, c["name"], c["sector"], run_date)
                with target.open("wb") as stream:
                    with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as compressed:
                        compressed.write(raw)
                results.append({"name":f"{source_name} {ticker}", "ok":True, "count":1})
                succeeded = True
                break
            except Exception as exc:
                attempts.append(f"{source_name}: {str(exc)[:110]}")
        if not succeeded:
            results.append({"name":f"Yahoo/Stooq {ticker}", "ok":False, "count":0,
                            "error":"; ".join(attempts)[:340]})
        if pause:
            time.sleep(pause)
    return results


def raw_days():
    base = DATA / "raw"
    return sorted(p for p in base.glob("????-??-??") if p.is_dir() and any(p.glob("*.gz")))


def build():
    """Only gzipped native source snapshots are used: deterministic reprocessing."""
    result = []
    lookup = {c["ticker"]: c for c in companies()}
    for day in raw_days():
        # Prefer Yahoo when both sources exist; no duplicate item/date rows.
        candidates = {}
        for raw in sorted(day.glob("*.gz")):
            filename = raw.name
            if filename.startswith("tradingview_") and filename.endswith(".json.gz"):
                ticker, parser, priority = filename[12:-8], parse_tradingview_json, 0
            elif filename.startswith("yahoo_") and filename.endswith(".json.gz"):
                ticker, parser, priority = filename[6:-8], parse_yahoo_json, 1
            elif filename.startswith("stooq_") and filename.endswith(".csv.gz"):
                ticker, parser, priority = filename[6:-7], parse_csv_bytes, 2
            else:
                continue
            if ticker not in lookup:
                continue
            if ticker not in candidates or priority < candidates[ticker][0]:
                candidates[ticker] = (priority, raw, parser)
        for ticker, (_, raw, parser) in sorted(candidates.items()):
            c = lookup[ticker]
            try:
                with gzip.open(raw, "rb") as f:
                    payload = f.read()
                result.append(parser(payload, ticker, c["name"], c["sector"], day.name))
            except Exception as exc:
                print(f"Skipping invalid raw file {raw}: {exc}")
    result.sort(key=lambda r: (r["date"], r["item_id"]))
    DATA.mkdir(exist_ok=True)
    with (DATA / "history.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(result)
    return result


def changes(rows):
    days = sorted(set(r["date"] for r in rows))
    if not days: return [], [], []
    today = {r["item_id"]: r for r in rows if r["date"] == days[-1]}
    prior = {r["item_id"]: r for r in rows if r["date"] == days[-2]} if len(days)>1 else {}
    new = sorted(set(today)-set(prior)) if len(days)>1 else sorted(today)
    gone = sorted(set(prior)-set(today))
    moved = []
    for ticker in sorted(set(today)&set(prior)):
        old, current = float(prior[ticker]["close_usd"]), float(today[ticker]["close_usd"])
        pct = (current-old)/old*100 if old else 0
        moved.append({"ticker":ticker,"old":old,"new":current,"percent":pct})
    moved.sort(key=lambda x: -abs(x["percent"]))
    return new, gone, moved


def status(rows, sources, now):
    days = raw_days()
    latest_date = max((r["date"] for r in rows), default=None)
    latest = [r for r in rows if r["date"] == latest_date] if latest_date else []
    new, gone, _ = changes(rows)
    doc = {"run_time": now.isoformat().replace("+00:00","Z"), "first_run_date":days[0].name if days else None,
           "days_with_success":len(days), "items":len(latest), "new_today":new, "gone_today":gone,
           "sources":sources}
    (DATA / "status.json").write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8")
    return doc


def issue_markdown(rows, run_date, sources):
    new, gone, moved = changes(rows)
    lines=[f"# Market movements — {run_date}", "", "Rule: top 5 absolute percentage changes in closing price between the latest two collected run dates.", "", "## Top moves"]
    if moved:
        lines += ["| Ticker | Previous close ($) | Latest close ($) | Change |", "|---|---:|---:|---:|"]
        lines += [f"| {m['ticker']} | {m['old']:.2f} | {m['new']:.2f} | {m['percent']:+.2f}% |" for m in moved[:5]]
    else: lines.append("No comparable changes available.")
    lines += ["", "## Appeared", ", ".join(new) or "None", "", "## Disappeared", ", ".join(gone) or "None", "", "## Source status"]
    lines += [f"- {s['name']}: {'OK' if s['ok'] else 'FAILED'}" for s in sources]
    return "\n".join(lines)+"\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--date", help="UTC YYYY-MM-DD for testing/backfills")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    run_date = args.date or now.date().isoformat()
    sources = [] if args.build_only else download(run_date)
    rows = build()
    if args.build_only:
        existing = DATA / "status.json"
        if existing.exists():
            try: sources=json.loads(existing.read_text()).get("sources", [])
            except Exception: pass
    status(rows, sources, now)
    (DATA / "issue.md").write_text(issue_markdown(rows,run_date,sources),encoding="utf-8")
    print(f"Date={run_date} rows={len(rows)} sources_ok={sum(s['ok'] for s in sources)}")

if __name__ == "__main__": main()