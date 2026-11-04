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
from urllib.parse import urlencode
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


def download(run_date, fetcher=fetch_csv, pause=0.75):
    folder = DATA / "raw" / run_date
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for c in companies():
        ticker = c["ticker"]
        target = folder / f"stooq_{ticker}.csv.gz"
        target.unlink(missing_ok=True)  # Same-day reruns replace rather than reuse stale data.
        try:
            raw = fetcher(ticker, run_date)
            parse_csv_bytes(raw, ticker, c["name"], c["sector"], run_date)  # Validate before persisting.
            with target.open("wb") as stream:
                with gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as f:
                    f.write(raw)
            results.append({"name":f"Stooq {ticker}", "ok":True, "count":1})
        except Exception as exc:
            results.append({"name":f"Stooq {ticker}", "ok":False, "count":0, "error":str(exc)[:180]})
        if pause: time.sleep(pause)
    return results


def raw_days():
    base = DATA / "raw"
    return sorted(p for p in base.glob("????-??-??") if p.is_dir() and any(p.glob("*.csv.gz")))


def build():
    result = []
    lookup = {c["ticker"]: c for c in companies()}
    for day in raw_days():
        for raw in sorted(day.glob("stooq_*.csv.gz")):
            ticker = raw.name.removeprefix("stooq_").removesuffix(".csv.gz")
            if ticker not in lookup: continue
            c = lookup[ticker]
            try:
                with gzip.open(raw, "rb") as f: payload = f.read()
                result.append(parse_csv_bytes(payload, ticker, c["name"], c["sector"], day.name))
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