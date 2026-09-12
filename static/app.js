let latest=null;
async function loadSample(){
  const r=await fetch('/api/sample');
  const d=await r.json();
  latest=d;
  render(d.entry_5m,d.latest,d.spot_15m_bias);
}
function render(entry,r,bias){
  document.querySelector('#signal').textContent=entry.signal;
  document.querySelector('#score').textContent=`Score ${entry.score}/10`;
  const biasText=bias?`15M bias: ${bias.bias}. ${entry.reasons.join(' · ')||'No confirmation'}`:'No confirmation';
  document.querySelector('#reasons').textContent=biasText;
  if(r){for(const [id,key] of [['price','close'],['ema9','ema9'],['ema21','ema21'],['vwap','vwap'],['res','prev_resistance'],['sup','prev_support']]){document.querySelector('#'+id).textContent=r[key]==null?'—':Number(r[key]).toFixed(2)}}
}
async function upload(){
  const f=document.querySelector('#file').files[0]; if(!f)return;
  const fd=new FormData(); fd.append('file',f);
  const r=await fetch('/api/analyze',{method:'POST',body:fd}); const d=await r.json();
  if(!r.ok){document.querySelector('#uploadStatus').textContent=d.detail;return}
  render(d.execution_5m,d.latest,d.spot_15m_bias);
  document.querySelector('#uploadStatus').textContent=`Analysis complete. Risk: ${d.risk_guard.action}`;
}
function paper(side){document.querySelector('#tradeStatus').textContent=`Paper ${side} signal recorded at ${new Date().toLocaleTimeString()}. Live orders remain disabled.`}
loadSample();
