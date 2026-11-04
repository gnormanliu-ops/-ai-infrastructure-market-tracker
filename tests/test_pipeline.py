import csv
import gzip
import io
import json
from pathlib import Path
import pipeline

C=[{"ticker":"AAA","name":"Alpha Power","sector":"Energy"},{"ticker":"BBB","name":"Beta Hardware","sector":"Hardware"}]
def payload(date,close,vol=1000):
    return f"Date,Open,High,Low,Close,Volume\n{date},{close-1},{close+1},{close-2},{close},{vol}\n".encode()

def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(pipeline,"DATA",tmp_path/"data")
    monkeypatch.setattr(pipeline,"companies",lambda:C)

def test_source_conversion():
    row=pipeline.parse_csv_bytes(payload("2026-11-02",25),"AAA","Alpha Power","Energy","2026-11-03")
    assert row["date"]=="2026-11-03" and row["market_date"]=="2026-11-02"
    assert row["close_usd"]=="25.0" and row["volume_shares"]=="1000"

def test_invalid_response_rejected():
    import pytest
    with pytest.raises(ValueError):
        pipeline.parse_csv_bytes(b"blocked", "AAA", "Alpha Power", "Energy", "2026-11-03")

def test_history_idempotent_and_same_day_replacement(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    def first(t,d):return payload(d,20 if t=="AAA" else 30)
    pipeline.download("2026-11-02",first,pause=0)
    pipeline.download("2026-11-03",lambda t,d:payload(d,22 if t=="AAA" else 27),pause=0)
    rows=pipeline.build()
    assert len(rows)==4
    assert [r["item_id"] for r in rows]==["AAA","BBB","AAA","BBB"]
    before=(pipeline.DATA/"history.csv").read_bytes()
    assert pipeline.build()==rows
    assert (pipeline.DATA/"history.csv").read_bytes()==before
    new,gone,moves=pipeline.changes(rows)
    assert new==[] and gone==[]
    assert moves[0]["ticker"]=="AAA" and round(moves[0]["percent"])==10
    pipeline.download("2026-11-03",lambda t,d:payload(d,24 if t=="AAA" else 27),pause=0)
    rows=pipeline.build()
    assert len(rows)==4 and rows[2]["close_usd"]=="24.0"
    assert len(pipeline.raw_days())==2

def test_failure_survives(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    def flaky(t,d):
        if t=="BBB":raise RuntimeError("unavailable")
        return payload(d,10)
    sources=pipeline.download("2026-11-03",flaky,pause=0)
    assert sources[0]["ok"] and not sources[1]["ok"]
    rows=pipeline.build()
    assert len(rows)==1 and rows[0]["item_id"]=="AAA"
    assert not (pipeline.DATA/"raw"/"2026-11-03"/"stooq_BBB.csv.gz").exists()

def test_missing_item_move(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    folder=pipeline.DATA/"raw"/"2026-11-02";folder.mkdir(parents=True)
    with gzip.open(folder/"stooq_AAA.csv.gz","wb") as f:f.write(payload("2026-11-02",10))
    folder2=pipeline.DATA/"raw"/"2026-11-03";folder2.mkdir(parents=True)
    with gzip.open(folder2/"stooq_BBB.csv.gz","wb") as f:f.write(payload("2026-11-03",10))
    new,gone,moved=pipeline.changes(pipeline.build())
    assert new==["BBB"] and gone==["AAA"] and moved==[]