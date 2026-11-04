"""Generate illustrative, non-market sample data strictly for UI preview."""
import csv,json,math,random
from pathlib import Path
from datetime import date,timedelta
ROOT=Path(__file__).resolve().parents[1]
companies=json.loads((ROOT/'companies.json').read_text())
out=ROOT/'demo'
rng=random.Random(20261103)
dates=[(date(2026,10,29)+timedelta(days=i)).isoformat() for i in [0,1,4,5]]
with (out/'history.csv').open('w',newline='') as f:
    writer=csv.writer(f);writer.writerow(['date','item_id','item','source','sector','close_usd','volume_shares','open_usd','high_usd','low_usd','market_date'])
    for day_i,d in enumerate(dates):
        market_date=d if d!='2026-11-01' else '2026-10-30'
        for i,c in enumerate(companies):
            baseline=45+i*37
            close=baseline*(1+.012*math.sin(day_i+i/2)+.006*day_i)
            vol=int((1_200_000+i*350_000)*(1+.14*math.cos(day_i+i)))
            writer.writerow([d,c['ticker'],c['name'],'Synthetic demo',c['sector'],f'{close:.2f}',vol,f'{close*.996:.2f}',f'{close*1.014:.2f}',f'{close*.985:.2f}',market_date])
(out/'status.json').write_text(json.dumps({'run_time':'2026-11-03T02:20:00Z','first_run_date':dates[0],'days_with_success':len(dates),'items':len(companies),'new_today':[],'gone_today':[],'sources':[{'name':'Synthetic preview','ok':True,'count':15}]},indent=2)+'\n')