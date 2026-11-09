/* All metrics and charts are computed client-side from history.csv. */
const $=s=>document.querySelector(s), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>Number.isFinite(+x)?'$'+(+x).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'—';
const int=x=>Number.isFinite(+x)?(+x).toLocaleString('en-US',{maximumFractionDigits:0}):'—';
const pct=x=>Number.isFinite(x)?`${x>=0?'+':''}${x.toFixed(2)}%`:'—';
const changeClass=x=>x>=0?'up':'down';
const nums=['close_usd','volume_shares','open_usd','high_usd','low_usd'];
const labels={close_usd:'Closing price ($)',volume_shares:'Volume (shares)',open_usd:'Opening price ($)',high_usd:'High price ($)',low_usd:'Low price ($)'};
function csv(text){const lines=text.trim().split(/\r?\n/).filter(Boolean);if(lines.length<2)return [];const cols=lines[0].split(',');return lines.slice(1).map(line=>{let obj={};line.split(',').forEach((v,i)=>obj[cols[i]]=v);return obj})}
async function get(url){const res=await fetch(url,{cache:'no-store'});if(!res.ok)throw Error(url+' HTTP '+res.status);return await res.text()}
function latestRows(rows){const d=[...new Set(rows.map(x=>x.date))].sort(),cur=rows.filter(x=>x.date===d.at(-1)),prev=rows.filter(x=>x.date===d.at(-2));const prevMap=new Map(prev.map(x=>[x.item_id,x]));return {dates:d,cur:cur.map(x=>({...x,delta:prevMap.has(x.item_id)?(Number(x.close_usd)/Number(prevMap.get(x.item_id).close_usd)-1)*100:null})),prev}}
function lineChart(canvas,series){if(!canvas)return;const rect=canvas.getBoundingClientRect(),width=Math.max(250,rect.width),height=Math.max(100,rect.height),dpr=window.devicePixelRatio||1;canvas.width=width*dpr;canvas.height=height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);const pad={l:50,r:15,t:15,b:26};const all=series.flatMap(s=>s.points.map(p=>p.y)).filter(Number.isFinite);if(!all.length)return;let min=Math.min(...all),max=Math.max(...all);if(min===max){min-=1;max+=1}const dates=[...new Set(series.flatMap(s=>s.points.map(p=>p.x)))].sort();const px=x=>pad.l+(dates.indexOf(x)/Math.max(1,dates.length-1))*(width-pad.l-pad.r),py=y=>height-pad.b-(y-min)/(max-min)*(height-pad.t-pad.b);ctx.font='11px DM Sans, sans-serif';ctx.textAlign='right';for(let i=0;i<4;i++){const y=pad.t+i*(height-pad.t-pad.b)/3;ctx.strokeStyle='#28374b';ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(width-pad.r,y);ctx.stroke();ctx.fillStyle='#91a4b8';ctx.fillText((max-(max-min)*i/3).toLocaleString('en-US',{maximumFractionDigits:1}),pad.l-7,y+3)}ctx.textAlign='center';ctx.fillText(dates[0]||'',pad.l,height-6);ctx.fillText(dates.at(-1)||'',width-pad.r-32,height-6);series.forEach((s,i)=>{ctx.strokeStyle=s.color||['#59d6c6','#6caafa','#f0bd6d','#f186a5','#a99bff','#83ce7c'][i%6];ctx.lineWidth=2.3;ctx.beginPath();s.points.forEach((p,j)=>{if(j===0)ctx.moveTo(px(p.x),py(p.y));else ctx.lineTo(px(p.x),py(p.y))});ctx.stroke()})}
function table(rows,stars=false){if(!rows.length)return '<div class="empty">No rows for this selection.</div>';return `<div class="tablewrap"><table><thead><tr>${stars?'<th>Save</th>':''}<th>Ticker</th><th>Company</th><th>Sector</th><th>Close</th><th>Volume</th><th>Change*</th><th>Market date</th></tr></thead><tbody>${rows.map(r=>`<tr>${stars?`<td><button class="star ${saved.has(r.item_id)?'on':''}" data-star="${esc(r.item_id)}" title="Save to shortlist">★</button></td>`:''}<td class="symbol">${esc(r.item_id)}</td><td>${esc(r.item)}</td><td class="muted">${esc(r.sector)}</td><td>${money(r.close_usd)}</td><td>${int(r.volume_shares)}</td><td class="${r.delta==null?'muted':changeClass(r.delta)}">${r.delta==null?'—':pct(r.delta)}</td><td class="muted">${esc(r.market_date||'Quote snapshot')}</td></tr>`).join('')}</tbody></table></div><p class="muted">*Change in closing price vs. previous successful tracker date, not necessarily previous trading session.</p>`}
let saved=new Set(JSON.parse(localStorage.getItem('infra-shortlist')||'[]'));
function wireStars(){document.querySelectorAll('[data-star]').forEach(el=>el.onclick=()=>{const t=el.dataset.star;saved.has(t)?saved.delete(t):saved.add(t);localStorage.setItem('infra-shortlist',JSON.stringify([...saved]));el.classList.toggle('on',saved.has(t))})}
function panel(title,content,note=''){return `<section class="panel"><h2>${title}</h2>${note?`<p class="panel-note">${note}</p>`:''}${content}</section>`}
function drawToday(rows,st){const {cur,prev,dates}=latestRows(rows);let movements=cur.filter(x=>x.delta!=null).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));const cards=[['Tracked companies',cur.length],['Successful source days',st.days_with_success??dates.length],['Source successes',(st.sources||[]).filter(s=>s.ok).length+' / '+(st.sources||[]).length],['Quote session date',cur.reduce((d,r)=>r.market_date>d?r.market_date:d,'')||'Not supplied']];$('#subtitle').textContent='Latest available market quote snapshots across 15 energy, industrial, construction and hardware companies.';$('#app').innerHTML=`<div class="metrics">${cards.map(([l,v])=>`<div class="metric"><span>${l}</span><b>${esc(v)}</b></div>`).join('')}</div><div class="split"><div>${panel('Latest market snapshot',table(cur))}</div><div>${panel('Biggest price moves',movements.length?movements.slice(0,6).map((r,i)=>`<div style="display:flex;justify-content:space-between;border-bottom:1px solid #2a394b;padding:13px 0"><span><span class="muted">0${i+1}</span> &nbsp; <b>${esc(r.item_id)}</b></span><span class="${changeClass(r.delta)}">${pct(r.delta)}</span></div>`).join(''):'<div class="empty">A second daily snapshot is needed to calculate changes.</div>')}${panel('Data source status',`<p>Last run: ${esc(st.run_time||'not yet')}</p><p>First run: ${esc(st.first_run_date||'—')}</p><p>New: ${esc((st.new_today||[]).join(', ')||'None')} / Gone: ${esc((st.gone_today||[]).join(', ')||'None')}</p><div style="max-height:260px;overflow:auto">${(st.sources||[]).map(s=>`<p style="margin:6px 0"><span class="pill ${s.ok?'':'bad'}">${s.ok?'OK':'FAIL'}</span> ${esc(s.name)} ${s.error?`<span class="muted">${esc(s.error)}</span>`:''}</p>`).join('')||'<p>No run recorded.</p>'}</div>`)}</div></div>`}
function drawBrowse(rows){const {cur}=latestRows(rows);$('#subtitle').textContent='Explore the 15-company universe. Filter, search, sort and save favorites on this device.';const sectors=[...new Set(cur.map(x=>x.sector))].sort();$('#app').innerHTML=`<section class="panel"><div class="controls"><input id="search" type="search" placeholder="Search companies / tickers"><select id="sector"><option value="">All sectors</option>${sectors.map(s=>`<option>${esc(s)}</option>`).join('')}</select><select id="watch"><option value="">All items</option><option value="saved">★ My shortlist</option></select><select id="sort">${nums.flatMap(n=>[`<option value="${n}:desc">${labels[n]} ↓</option>`,`<option value="${n}:asc">${labels[n]} ↑</option>`]).join('')}</select></div><div id="browseTable"></div></section>`;function render(){const q=$('#search').value.toLowerCase(),sector=$('#sector').value,watch=$('#watch').value,[column,dir]=$('#sort').value.split(':');const filtered=cur.filter(r=>(r.item.toLowerCase().includes(q)||r.item_id.toLowerCase().includes(q))&&(!sector||r.sector===sector)&&(!watch||saved.has(r.item_id))).sort((a,b)=>(Number(a[column])-Number(b[column]))*(dir==='asc'?1:-1));$('#browseTable').innerHTML=table(filtered,true);wireStars();document.querySelectorAll('[data-star]').forEach(btn=>btn.addEventListener('click',()=>{if(watch)render()}))}['search','sector','watch','sort'].forEach(id=>$('#'+id).addEventListener('input',render));render()}
function grouping(rows,fn){const m=new Map();rows.forEach(r=>{const k=fn(r);if(!m.has(k))m.set(k,[]);m.get(k).push(r)});return m}
const palette=['#59d6c6','#6caafa','#f0bd6d','#f186a5','#a99bff','#83ce7c'];
function drawTrends(rows){$('#subtitle').textContent='All analysis is calculated in your browser from the growing daily history CSV.';const {cur,dates}=latestRows(rows);let selected=new Set(cur.slice(0,5).map(r=>r.item_id));$('#app').innerHTML=panel('Historical market series',`<div class="controls"><select id="metric">${nums.map(n=>`<option value="${n}">${labels[n]}</option>`).join('')}</select></div><div id="chips" class="multi"></div><canvas class="chart" id="mainChart"></canvas><div id="seriesLegend" class="legend"></div>`,'Choose any metric and the companies to compare; units and axis values update dynamically.')+`<h2 style="margin:35px 0 18px">Research findings <span class="muted">/ dynamically calculated</span></h2><div id="findings" class="finding-grid"></div>`;
function drawMain(){const metric=$('#metric').value;$('#chips').innerHTML=cur.map(r=>`<button class="chip ${selected.has(r.item_id)?'on':''}" data-ticker="${r.item_id}">${r.item_id}</button>`).join('');$('#chips').querySelectorAll('button').forEach(b=>b.onclick=()=>{selected.has(b.dataset.ticker)?selected.delete(b.dataset.ticker):selected.add(b.dataset.ticker);drawMain()});const tickers=[...selected];const series=tickers.map((t,i)=>({name:t,color:palette[i%palette.length],points:rows.filter(r=>r.item_id===t&&r[metric]!==''&&Number.isFinite(+r[metric])).map(r=>({x:r.date,y:+r[metric]}))}));lineChart($('#mainChart'),series);$('#seriesLegend').innerHTML=series.map(s=>`<span><i class="dot" style="background:${s.color}"></i>${s.name}</span>`).join('')}
$('#metric').addEventListener('change',drawMain);drawMain();const grouped=grouping(rows,r=>r.item_id);const latest=cur.map(r=>{const a=grouped.get(r.item_id)||[];const first=a[0],last=a.at(-1);return {...r,initial:first,returnPct:first&&+first.close_usd?((+last.close_usd/+first.close_usd)-1)*100:0,volumeAvg:a.reduce((sum,r)=>sum+(+r.volume_shares||0),0)/a.length}});const returns=[...latest].sort((a,b)=>b.returnPct-a.returnPct),volumes=[...latest].sort((a,b)=>b.volumeAvg-a.volumeAvg);const gap=cur.length?Math.max(...cur.map(x=>+x.close_usd))-Math.min(...cur.map(x=>+x.close_usd)):0;const volumeByDate=[...grouping(rows,r=>r.date)].map(([d,list])=>({x:d,y:list.reduce((n,r)=>n+(+r.volume_shares||0),0)}));const maxVolume=volumeByDate.reduce((a,b)=>!a||b.y>a.y?b:a,null);

const movement=[...cur].filter(r=>r.delta!=null).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta)).slice(0,8);
const ideas=[
 {title:'Total return since first observation', desc:'Compare percentage price returns, not raw share prices. For each company: (latest close ÷ earliest recorded close − 1) × 100. Based on '+dates.length+' tracked collection dates; dividends are excluded.',kind:'bar',unit:'%',signed:true,points:returns.slice(0,10).map(r=>({x:r.item_id,y:r.returnPct}))},
 {title:'Average daily shares traded',desc:'Compare trading activity across companies, with volume measured in shares. Each bar is total reported volume divided by the number of recorded observations for that company.',kind:'bar',unit:' shares',points:volumes.slice(0,10).map(r=>({x:r.item_id,y:r.volumeAvg}))},
 {title:'Total shares traded by collection date',desc:'A genuine time-series line chart. Each date is the sum of reported share volume among companies observed on that collection date; missing companies are excluded.',kind:'line',unit:' shares',points:volumeByDate},
 {title:'Largest changes since previous collection',desc:movement.length?'Percentage changes in closing price between the two most recent tracker collection dates, ranked by absolute magnitude. Positive and negative bars extend in opposite directions.':'At least two successful collection dates are needed before price moves can be compared.',kind:'bar',unit:'%',signed:true,points:movement.map(r=>({x:r.item_id,y:r.delta}))}
];
$('#findings').innerHTML=ideas.map((f,i)=>panel(f.title,`<p>${f.desc}</p><canvas class="chart" id="finding${i}" role="img" aria-label="${esc(f.title)}"></canvas><div class="legend">${f.unit==='%'?'Values shown as percentages.':f.unit===' shares'?'Values shown in number of shares.':''}</div>`)).join('');
ideas.forEach((f,i)=>f.kind==='bar'?barChart($('#finding'+i),f.points,f.unit,f.signed):lineChart($('#finding'+i),[{name:f.title,points:f.points}]));
}
function barChart(canvas,points,unit='',signed=false){
  if(!canvas)return;
  const width=Math.max(280,canvas.getBoundingClientRect().width),height=Math.max(180,canvas.getBoundingClientRect().height),dpr=window.devicePixelRatio||1;
  canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
  const c=canvas.getContext('2d');c.scale(dpr,dpr);c.clearRect(0,0,width,height);
  if(!points.length){c.fillStyle='#91a4b8';c.font='13px sans-serif';c.fillText('More real daily observations are needed.',18,55);return}
  const margin={left:68,right:17,top:20,bottom:48},chartW=width-margin.left-margin.right,chartH=height-margin.top-margin.bottom;
  const values=points.map(p=>Number(p.y)).filter(Number.isFinite);
  if(!values.length)return;
  const lo=Math.min(signed?0:0,...values),hi=Math.max(0,...values);
  const span=(hi-lo)||1;
  const x0=margin.left;
  const yy=v=>margin.top+(hi-v)/span*chartH;
  const baseline=yy(0);
  c.strokeStyle='#40536c';c.lineWidth=1;c.beginPath();c.moveTo(x0,baseline);c.lineTo(width-margin.right,baseline);c.stroke();
  c.font='11px sans-serif';c.textAlign='right';c.fillStyle='#91a4b8';
  for(let tick=0;tick<=4;tick++){let v=lo+span*tick/4,y=yy(v);if(y<margin.top||y>height-margin.bottom)continue;c.fillText((Math.abs(v)>=1000000?(v/1000000).toFixed(1)+'M':Math.abs(v)>=1000?(v/1000).toFixed(1)+'K':v.toFixed(1))+(unit==='%'?'%':''),x0-8,y+4)}
  const slot=chartW/points.length,bw=Math.min(46,slot*.68);
  c.textAlign='center';
  points.forEach((p,i)=>{
    const v=Number(p.y);if(!Number.isFinite(v))return;
    const x=margin.left+slot*i+slot/2,y=yy(v);
    c.fillStyle=v<0?'#f186a5':'#59d6c6';
    c.fillRect(x-bw/2,Math.min(y,baseline),bw,Math.max(1,Math.abs(baseline-y)));
    c.fillStyle='#b8c9da';c.fillText(String(p.x).slice(0,11),x,height-margin.bottom+18);
    c.fillStyle='#e9f2fb';const val=unit==='%'?v.toFixed(1)+'%':Math.abs(v)>=1000000?(v/1000000).toFixed(1)+'M':Math.abs(v)>=1000?(v/1000).toFixed(0)+'K':v.toFixed(0);
    c.fillText(val,x,Math.max(12,Math.min(height-margin.bottom+32,v>=0?y-6:y+14)));
  });
}

const RUN_SCHEDULE_UTC='23:20 UTC';
function centralFormat(value){if(!value)return 'No run recorded';const d=new Date(value);return Number.isNaN(d.valueOf())?'Invalid timestamp':new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}).format(d)}
function centralRunSchedule(){return '5:20 PM CST / 6:20 PM CDT (same day)'}
function renderUpdateStatus(st,productionRows,usingDemo){
  const sources=Array.isArray(st.sources)?st.sources:[],ok=sources.filter(s=>s.ok).length;
  const count=productionRows.length;
  const latestDate=count?[...new Set(productionRows.map(r=>r.date))].sort().at(-1):null;
  const todayUTC=new Date().toISOString().slice(0,10);
  const todaysRows=productionRows.filter(r=>r.date===todayUTC);
  const latestMarketDate=count?productionRows.map(r=>r.market_date).sort().at(-1):null;
  const lastRun=st.run_time?new Date(st.run_time):null;
  const ranTodayUTC=lastRun&&!Number.isNaN(lastRun.valueOf())&&lastRun.toISOString().slice(0,10)===todayUTC;
  let condition=usingDemo?'No real quotes available':(count?'Live history available':'Awaiting real market data');
  if(sources.length&&ok===0)condition='All sources failed on last run';
  else if(sources.length&&ok<sources.length)condition='Partial source success';
  const box=document.createElement('section');box.className='panel update-status';
  box.innerHTML=`<h2>Daily update schedule & data health</h2>
  <div class="update-grid">
    <div><span class="update-label">Scheduled run</span><strong>Daily at ${RUN_SCHEDULE_UTC}</strong><small>${centralRunSchedule()} · GitHub Actions may start late</small></div>
    <div><span class="update-label">Last attempt (Central)</span><strong>${esc(centralFormat(st.run_time))}</strong><small>Actual pipeline attempt, not a successful quote timestamp</small></div>
    <div><span class="update-label">Last source result</span><strong class="${ok===0?'down':'up'}">${esc(condition)}</strong><small>${ok} / ${sources.length} sources succeeded</small></div>
    <div><span class="update-label">Real market observations</span><strong>${count.toLocaleString('en-US')} rows</strong><small>Latest collection: ${esc(latestDate||'None')} · Market date: ${esc(latestMarketDate||'Not provided by snapshot source')}</small></div>
  </div>
  <p class="update-note">Today's UTC collection (${todayUTC}): <b>${todaysRows.length} real rows</b>. ${ranTodayUTC?'A pipeline attempt is recorded today.':'No pipeline attempt recorded today in the latest status.'} ${usingDemo?'Visible charts and prices below are SYNTHETIC DEMO DATA, not real quotes.':''} Trading-day prices may not change on weekends or market holidays.</p>`;
  document.querySelector('.hero').insertAdjacentElement('afterend',box);
}
async function main(){
  const page=document.body.dataset.page;let productionRows=[],rows=[],st={},usingDemo=false;
  try{const statusText=await get('data/status.json');st=JSON.parse(statusText)}catch(err){console.warn('Production status unavailable',err)}
  try{productionRows=csv(await get('data/history.csv'));rows=productionRows}catch(err){console.warn('Production history unavailable',err)}
  if(!rows.length){
    usingDemo=true;
    try{rows=csv(await get('demo/history.csv'));$('#demoBanner').classList.remove('hidden');$('#demoBanner').textContent='DEMO PREVIEW — All prices, volumes and charts below are synthetic illustration data. Live source health and actual collection counts are displayed separately above.'}
    catch(err){$('#app').innerHTML='<div class="panel empty">No market data yet. Check the daily source status above.</div>'}
  }
  renderUpdateStatus(st,productionRows,usingDemo);
  if(!rows.length)return;
  // Keep production metadata truthful. Demo charts may use synthetic rows, but the data status panel never does.
  if(page==='index')drawToday(rows,usingDemo?{...st,days_with_success:st.days_with_success||0,items:st.items||0}:st);
  if(page==='browse')drawBrowse(rows);
  if(page==='trends')drawTrends(rows);
  window.addEventListener('resize',()=>{if(page==='trends')drawTrends(rows)});
}
main();if('serviceWorker'in navigator&&location.protocol.startsWith('http'))navigator.serviceWorker.register('sw.js').catch(console.error);