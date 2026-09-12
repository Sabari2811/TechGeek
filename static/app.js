let latest=null;
async function loadSample(){
  const r=await fetch('/api/sample');
  const d=await r.json();
  latest=d;
  render(d.entry_5m,d.latest,d.spot_15m_bias,d.astra_decision);
}
function render(entry,r,bias,astra){
  document.querySelector('#signal').textContent=entry.signal;
  document.querySelector('#score').textContent=`Score ${entry.score}/10`;
  const biasText=bias?`15M bias: ${bias.bias}. ${entry.reasons.join(' · ')||'No confirmation'}`:'No confirmation';
  document.querySelector('#reasons').textContent=biasText;
  if(astra){ document.querySelector('#astraDecision').textContent=astra.decision||'WAIT'; document.querySelector('#astraConfidence').textContent=astra.confidence==null?'—':`${Number(astra.confidence).toFixed(0)}%`; document.querySelector('#astraSetup').textContent=astra.setup||'—'; document.querySelector('#astraReason').textContent=astra.reason||'—'; }
  if(r){for(const [id,key] of [['price','close'],['ema9','ema9'],['ema21','ema21'],['vwap','vwap'],['res','prev_resistance'],['sup','prev_support']]){document.querySelector('#'+id).textContent=r[key]==null?'—':Number(r[key]).toFixed(2)}}
}
async function upload(){
  const f=document.querySelector('#file').files[0]; if(!f)return;
  const fd=new FormData(); fd.append('file',f);
  const r=await fetch('/api/analyze',{method:'POST',body:fd}); const d=await r.json();
  if(!r.ok){document.querySelector('#uploadStatus').textContent=d.detail;return}
  render(d.execution_5m,d.latest,d.spot_15m_bias,d.astra_decision);
  document.querySelector('#uploadStatus').textContent=`Analysis complete. ASTRA: ${d.astra_decision.decision}. Risk: ${d.risk_guard.action}`;
}
function paper(side){document.querySelector('#tradeStatus').textContent=`Paper ${side} signal recorded at ${new Date().toLocaleTimeString()}. Live orders remain disabled.`}
loadSample();
