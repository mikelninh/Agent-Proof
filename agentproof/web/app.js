const $ = (id) => document.getElementById(id);
const fmtPct = (x) => `${(x*100).toFixed(1)}%`;
const fmtEur = (x) => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(x);
const fmtSmallEur = (x) => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:4}).format(x);
const fmtSignedPct = (x) => `${x>=0?'+':''}${(x*100).toFixed(1)}%`;
const fmtSignedEur = (x) => `${x>=0?'+':''}${new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(x)}`;
let currentRun = null;
let currentComparison = null;
let latestRuns = [];
let csvState = null;

async function api(url, options={}) {
  const r = await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
  if(!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json();
}

async function loadPacks(){
  const packs=await api('/api/packs');
  $('packSelect').innerHTML=packs.map(p=>`<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} · ${p.case_count} cases</option>`).join('');
}

function providerUI(){
  document.querySelectorAll('.remote').forEach(e=>e.style.display='none');
  if($('provider').value==='openai_compatible') document.querySelectorAll('.only-openai').forEach(e=>e.style.display='block');
  if($('provider').value==='webhook') document.querySelectorAll('.only-webhook').forEach(e=>e.style.display='block');
}
$('provider').addEventListener('change',providerUI);

function requestPayload(){
  const p=$('provider').value;
  return {
    pack_id:$('packSelect').value,
    agent:{
      provider:p,
      name:p==='heuristic'?'Built-in heuristic baseline':p==='heuristic_v2'?'Built-in candidate v2':($('model').value || 'Custom agent'),
      model:$('model').value||null,
      base_url:$('baseUrl').value||null,
      api_key:$('apiKey').value||null,
      webhook_url:$('webhookUrl').value||null,
      input_cost_per_million_eur:Number($('inputCost').value||0),
      output_cost_per_million_eur:Number($('outputCost').value||0)
    },
    economics:{
      human_minutes_per_case:Number($('humanMinutes').value),
      human_hourly_cost_eur:Number($('humanHourly').value),
      annual_case_volume:Number($('annualVolume').value),
      implementation_cost_eur:Number($('implementationCost').value)
    },
    gate:{
      min_success_rate:Number($('minSuccess').value)/100,
      max_critical_failure_rate:Number($('maxCritical').value)/100,
      max_agent_cost_per_case_eur:null
    }
  };
}

async function runEval(){
  $('runState').classList.remove('hidden');
  $('results').classList.add('hidden');
  try{
    const run=await api('/api/runs',{method:'POST',body:JSON.stringify(requestPayload())});
    currentRun=run; renderRun(run); await loadHistory();
  }catch(e){alert(`Evaluation failed: ${e.message}`)}
  finally{$('runState').classList.add('hidden')}
}

function metric(k,v,s='',cls='') {return `<div class="metric ${cls}"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`}
function renderRun(run){
  currentRun=run;
  const m=run.metrics;
  $('runTitle').textContent=`${run.pack_name} · ${run.agent.name}`;
  $('metrics').innerHTML=[
    metric('Deployment gate',run.gate.status==='pass'?'PASS':'BLOCKED',run.gate.reasons[0]||'thresholds satisfied',run.gate.status==='pass'?'good':'danger'),
    metric('Success',fmtPct(m.success_rate),`${m.total_cases} cases`,m.success_rate>=.9?'good':''),
    metric('Critical failures',fmtPct(m.critical_failure_rate),'configured dangerous mismatch',m.critical_failure_rate>0?'danger':'good'),
    metric('Avg cost / case',fmtSmallEur(m.agent_cost_per_case_eur),`human ${fmtSmallEur(m.human_cost_per_case_eur)}`),
    metric('Annual savings',fmtEur(m.estimated_annual_savings_eur),`${run.economics.annual_case_volume.toLocaleString()} cases/year`,'good'),
    metric('First-year ROI',m.roi_multiple===null?'—':`${m.roi_multiple.toFixed(1)}×`,`${fmtEur(run.economics.implementation_cost_eur)} implementation`)
  ].join('');
  const critical=run.cases.filter(c=>c.grade.critical_failure).length;
  const failed=run.cases.filter(c=>!c.grade.passed).length;
  $('summaryStrip').innerHTML=`<span><b>${failed}</b> mismatches</span><span><b>${critical}</b> critical</span><span><b>${fmtPct(m.escalation_rate)}</b> escalated</span><span><b>${m.avg_latency_ms.toFixed(0)}ms</b> avg latency</span>`;
  $('caseRows').innerHTML=run.cases.map((c,i)=>{
    const exp=Object.values(c.expected)[0]??'—';
    const targetField=Object.keys(c.expected)[0];
    const act=(targetField && c.output.parsed[targetField]!==undefined)?c.output.parsed[targetField]:(c.output.parsed.decision??'error');
    const risk=c.grade.critical_failure?'<span class="pill critical">critical</span>':c.grade.passed?'<span class="pill ok">pass</span>':'<span class="pill review">mismatch</span>';
    return `<tr data-i="${i}"><td>${escapeHtml(c.title)}</td><td><span class="pill neutral">${escapeHtml(exp)}</span></td><td><span class="pill neutral">${escapeHtml(act)}</span></td><td>${(c.grade.score*100).toFixed(0)}</td><td>${risk}</td></tr>`
  }).join('');
  document.querySelectorAll('#caseRows tr').forEach(tr=>tr.onclick=()=>renderTrace(run.cases[Number(tr.dataset.i)]));
  $('results').classList.remove('hidden');
  $('results').scrollIntoView({behavior:'smooth',block:'start'});
}

function renderTrace(c){
  $('traceEmpty').classList.add('hidden'); $('trace').classList.remove('hidden');
  const reasons=c.grade.reasons.length?c.grade.reasons.map(r=>`<div class="reason">${escapeHtml(r)}</div>`).join(''):'<div class="pill ok">all graded fields matched</div>';
  $('trace').innerHTML=`
    <div class="trace-block"><h4>Case input · agent-visible</h4><pre>${escapeHtml(JSON.stringify(c.input,null,2))}</pre></div>
    <div class="trace-block"><h4>Agent output</h4><pre>${escapeHtml(c.output.raw_text || c.output.error || 'No output')}</pre></div>
    <div class="trace-block"><h4>Hidden ground truth</h4><pre>${escapeHtml(JSON.stringify(c.expected,null,2))}</pre></div>
    <div class="trace-block"><h4>Grader</h4>${reasons}</div>
    <div class="trace-block"><h4>Runtime evidence</h4><pre>${c.output.latency_ms.toFixed(0)} ms\n${c.output.input_tokens} input tokens\n${c.output.output_tokens} output tokens\n${fmtSmallEur(c.output.estimated_cost_eur)}</pre></div>`;
}
function escapeHtml(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[c]))}

async function loadHistory(){
  const runs=await api('/api/runs');
  latestRuns=runs;
  $('history').innerHTML=runs.length?runs.map(r=>`<div class="history-card" data-id="${r.id}"><div><strong>${escapeHtml(r.pack_name)}</strong><br/><span>${escapeHtml(r.agent_name)}${r.model?' · '+escapeHtml(r.model):''}</span></div><div><span>Success</span><br/><div class="num">${fmtPct(r.metrics.success_rate)}</div></div><div><span>Critical</span><br/><div class="num">${fmtPct(r.metrics.critical_failure_rate)}</div></div><div><span>Savings</span><br/><div class="num">${fmtEur(r.metrics.estimated_annual_savings_eur)}</div></div><div><span>Run</span><br/><div class="num">${new Date(r.created_at).toLocaleString()}</div></div></div>`).join(''):'<div class="empty">No runs yet. Run the demo to create your first evidence record.</div>';
  document.querySelectorAll('.history-card').forEach(el=>el.onclick=async()=>renderRun(await api('/api/runs/'+el.dataset.id)));
  const options=runs.map(r=>`<option value="${r.id}">${escapeHtml(r.pack_name)} · ${escapeHtml(r.agent_name)} · ${fmtPct(r.metrics.success_rate)}</option>`).join('');
  $('baselineRun').innerHTML=options; $('candidateRun').innerHTML=options;
  if(runs.length>=2){ $('candidateRun').value=runs[0].id; const samePack=runs.slice(1).find(r=>r.pack_id===runs[0].pack_id); $('baselineRun').value=(samePack||runs[1]).id; }
}

async function compareSelectedRuns(){
  const baseline_run_id=$('baselineRun').value, candidate_run_id=$('candidateRun').value;
  if(!baseline_run_id || !candidate_run_id){alert('Create at least two runs first.'); return;}
  if(baseline_run_id===candidate_run_id){alert('Choose two different runs.'); return;}
  try{
    const comparison=await api('/api/compare',{method:'POST',body:JSON.stringify({baseline_run_id,candidate_run_id})});
    currentComparison=comparison; renderComparison(comparison);
  }catch(e){alert(`Comparison failed: ${e.message}`)}
}

function deltaClass(x,lowerIsBetter=false){
  if(Math.abs(x)<1e-12)return 'delta-neutral';
  const good=lowerIsBetter?x<0:x>0; return good?'delta-good':'delta-bad';
}

function renderComparison(c){
  $('compareEmpty').classList.add('hidden'); $('compareResult').classList.remove('hidden'); $('exportComparison').classList.remove('hidden');
  const banner=$('comparisonBanner'); banner.className=`comparison-banner ${c.recommendation}`;
  banner.innerHTML=`${c.recommendation.toUpperCase()} · ${escapeHtml(c.candidate_agent)} vs ${escapeHtml(c.baseline_agent)}`;
  $('compareMetrics').innerHTML=[
    metric('Success delta',`<span class="${deltaClass(c.success_rate_delta)}">${fmtSignedPct(c.success_rate_delta)}</span>`,`${fmtPct(c.baseline_success_rate)} → ${fmtPct(c.candidate_success_rate)}`),
    metric('Regressions',c.regressions,`${c.fixes} fixes`,c.regressions>c.fixes?'danger':c.fixes>c.regressions?'good':''),
    metric('New critical',c.new_critical_failures,`${c.resolved_critical_failures} resolved`,c.new_critical_failures?'danger':'good'),
    metric('Cost delta',`<span class="${deltaClass(c.cost_per_case_delta_eur,true)}">${fmtSmallEur(c.cost_per_case_delta_eur)}</span>`,'per case'),
    metric('Annual savings Δ',`<span class="${deltaClass(c.annual_savings_delta_eur)}">${fmtSignedEur(c.annual_savings_delta_eur)}</span>`,`paired p=${c.mcnemar_p_value.toFixed(4)}`)
  ].join('');
  $('comparisonReasons').innerHTML=c.reasons.map(r=>`<span class="reason-chip">${escapeHtml(r)}</span>`).join('');
  const changed=c.cases.filter(x=>x.status!=='unchanged');
  $('comparisonRows').innerHTML=changed.length?changed.map(x=>{
    const outcome=x.status==='fix'?'<span class="pill ok">fix</span>':'<span class="pill critical">regression</span>';
    const critical=x.candidate_critical&&!x.baseline_critical?' <span class="pill critical">new critical</span>':'';
    return `<tr><td>${escapeHtml(x.title)}</td><td>${escapeHtml(x.baseline_decision??'—')}</td><td>${escapeHtml(x.candidate_decision??'—')}</td><td>${outcome}${critical}</td></tr>`;
  }).join(''):'<tr><td colspan="4" class="empty">No pass/fail changes on paired cases.</td></tr>';
}

// ---- Pilot Mode: browser-side historical CSV importer ----
const piiPattern = /(full.?name|first.?name|last.?name|email|e-mail|phone|mobile|address|street|postcode|postal|zip|birth|dob|ssn|social.?security|iban|bank.?account|card.?number|pan|passport|national.?id|ip.?address|device.?id)/i;

function parseCsv(text){
  const rows=[]; let row=[],field='',quoted=false;
  text=text.replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++){
    const ch=text[i];
    if(quoted){
      if(ch==='"' && text[i+1]==='"'){field+='"';i++;}
      else if(ch==='"'){quoted=false;}
      else field+=ch;
    }else{
      if(ch==='"') quoted=true;
      else if(ch===','){row.push(field);field='';}
      else if(ch==='\n'){row.push(field.replace(/\r$/,''));rows.push(row);row=[];field='';}
      else field+=ch;
    }
  }
  if(field.length||row.length){row.push(field.replace(/\r$/,''));rows.push(row);}
  const nonEmpty=rows.filter(r=>r.some(v=>String(v).trim()!==''));
  if(nonEmpty.length<2) throw new Error('CSV needs a header row and at least one data row.');
  const headers=nonEmpty[0].map(h=>h.trim());
  if(headers.some(h=>!h)) throw new Error('Every CSV column needs a header.');
  if(new Set(headers).size!==headers.length) throw new Error('CSV contains duplicate column names.');
  const malformed=nonEmpty.slice(1).filter(r=>r.length!==headers.length).length;
  const data=nonEmpty.slice(1).map(r=>Object.fromEntries(headers.map((h,i)=>[h,(r[i]??'').trim()])));
  return {headers,data,malformed};
}

function slugify(value){return value.toLowerCase().trim().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,60)}
function openCsvModal(state){
  csvState=state;
  const suggested=state.fileName.replace(/\.csv$/i,'').replace(/[_-]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
  $('csvPackName').value=suggested || 'Historical Evaluation';
  $('csvPackId').value=slugify(suggested||'historical-eval')+'-v1';
  $('csvInstruction').value='Review this case and return one JSON object containing the correct decision.';
  const opts=state.headers.map(h=>`<option value="${escapeHtml(h)}">${escapeHtml(h)}</option>`).join('');
  $('csvTarget').innerHTML=opts;
  $('csvTitleColumn').innerHTML='<option value="">Auto-number cases</option>'+opts;
  const likelyTarget=state.headers.find(h=>/(decision|outcome|label|status|resolution|target|result)/i.test(h));
  if(likelyTarget) $('csvTarget').value=likelyTarget;
  renderCsvColumns(); renderCsvProfile();
  $('csvModal').classList.remove('hidden'); document.body.classList.add('modal-open');
}
function closeCsvModal(){ $('csvModal').classList.add('hidden'); document.body.classList.remove('modal-open'); }

function renderCsvColumns(){
  if(!csvState)return;
  const target=$('csvTarget').value;
  $('csvColumns').innerHTML=csvState.headers.filter(h=>h!==target).map(h=>{
    const pii=piiPattern.test(h);
    return `<label class="column-choice ${pii?'pii':''}"><input type="checkbox" data-column="${escapeHtml(h)}" ${pii?'':'checked'} /><span><strong>${escapeHtml(h)}</strong>${pii?'<em>possible PII</em>':''}</span></label>`;
  }).join('');
  document.querySelectorAll('#csvColumns input').forEach(i=>i.onchange=renderCsvProfile);
}

function selectedVisibleColumns(){ return [...document.querySelectorAll('#csvColumns input:checked')].map(i=>i.dataset.column); }
function renderCsvProfile(){
  if(!csvState)return;
  const target=$('csvTarget').value;
  const visible=selectedVisibleColumns();
  const labels=csvState.data.map(r=>r[target]);
  const missing=labels.filter(v=>v==='').length;
  const counts={};labels.forEach(v=>counts[v||'(missing)']=(counts[v||'(missing)']||0)+1);
  const duplicateKeys=new Set(),seen=new Set();
  csvState.data.forEach(r=>{const key=JSON.stringify([...visible.map(h=>r[h]),r[target]]);if(seen.has(key))duplicateKeys.add(key);else seen.add(key)});
  const piiSelected=visible.filter(h=>piiPattern.test(h));
  const warnings=[];
  if(csvState.malformed)warnings.push(`${csvState.malformed} row(s) had a different number of columns; missing cells were filled with blanks.`);
  if(missing)warnings.push(`${missing} row(s) have no ground-truth value and cannot produce a reliable grade.`);
  if(piiSelected.length)warnings.push(`Possible personal data selected: ${piiSelected.join(', ')}. Only include it if your pilot has an appropriate data-handling basis.`);
  $('csvWarnings').innerHTML=warnings.length?`<div class="warning-box">${warnings.map(w=>`<div>⚠ ${escapeHtml(w)}</div>`).join('')}</div>`:'<div class="safe-box">✓ No obvious import blockers detected. Still verify the data is synthetic or appropriately anonymised.</div>';
  const distribution=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8).map(([k,v])=>`${escapeHtml(k)} <b>${v}</b>`).join(' · ');
  $('csvStats').innerHTML=`<div><span>Rows</span><strong>${csvState.data.length}</strong></div><div><span>Agent-visible fields</span><strong>${visible.length}</strong></div><div><span>Duplicates</span><strong>${duplicateKeys.size}</strong></div><div class="wide"><span>Target distribution</span><strong>${distribution||'—'}</strong></div>`;
  const head=[...visible.slice(0,5),target];
  $('csvPreviewHead').innerHTML='<tr>'+head.map(h=>`<th class="${h===target?'ground-truth':''}">${escapeHtml(h)}${h===target?' · hidden':''}</th>`).join('')+'</tr>';
  $('csvPreviewBody').innerHTML=csvState.data.slice(0,5).map(r=>'<tr>'+head.map(h=>`<td class="${h===target?'ground-truth':''}">${escapeHtml(r[h]||'')}</td>`).join('')+'</tr>').join('');
}

function createPackFromCsv(){
  if(!csvState)return;
  const name=$('csvPackName').value.trim(), id=slugify($('csvPackId').value), instruction=$('csvInstruction').value.trim();
  const target=$('csvTarget').value, titleColumn=$('csvTitleColumn').value, visible=selectedVisibleColumns();
  if(!name||!id||!instruction) throw new Error('Pack name, ID and agent instruction are required.');
  if(!target) throw new Error('Choose a ground-truth column.');
  if(!visible.length) throw new Error('Select at least one agent-visible input column.');
  const validRows=csvState.data.filter(r=>String(r[target]??'').trim()!=='');
  if(!validRows.length) throw new Error('No rows contain ground truth.');
  const criticalExpected=$('csvCriticalExpected').value.trim(),criticalActual=$('csvCriticalActual').value.trim();
  const critical=(criticalExpected&&criticalActual)?[{field:target,expected:criticalExpected,actual:criticalActual}]:[];
  return {
    id,name,
    description:`Imported from ${csvState.fileName}. ${validRows.length} historical-style cases; target ${target} held out from agent-visible input.`,
    task_instruction:instruction,
    grader:{type:'json_fields',required_fields:[target],field_weights:{[target]:1.0},critical_mismatches:critical},
    cases:validRows.map((r,i)=>({
      id:`${id}-${String(i+1).padStart(4,'0')}`,
      title:titleColumn&&r[titleColumn]?String(r[titleColumn]):`Case ${i+1}`,
      input:Object.fromEntries(visible.map(h=>[h,r[h]])),
      expected:{[target]:r[target]},tags:[]
    }))
  };
}

$('runDemo').onclick=()=>{$('provider').value='heuristic'; providerUI(); runEval()};
$('runCandidate').onclick=()=>{$('provider').value='heuristic_v2'; providerUI(); runEval()};
$('rerun').onclick=runEval;
$('exportReport').onclick=()=>{if(currentRun) window.open(`/api/runs/${currentRun.id}/report.md`,'_blank')};
$('compareRuns').onclick=compareSelectedRuns;
$('exportComparison').onclick=()=>{if(currentComparison) window.open(`/api/compare/${currentComparison.baseline_run_id}/${currentComparison.candidate_run_id}/report.md`,'_blank')};
$('uploadBtn').onclick=()=>$('packFile').click();
$('packFile').onchange=async(e)=>{
  const f=e.target.files[0]; if(!f)return;
  try{const pack=JSON.parse(await f.text()); await api('/api/packs',{method:'POST',body:JSON.stringify(pack)}); await loadPacks(); $('packSelect').value=pack.id; alert(`Loaded ${pack.name} with ${pack.cases.length} cases.`)}catch(err){alert(`Pack import failed: ${err.message}`)}
};
$('importCsvBtn').onclick=()=>$('csvFile').click();
$('csvFile').onchange=async(e)=>{
  const f=e.target.files[0]; if(!f)return;
  try{const parsed=parseCsv(await f.text()); openCsvModal({...parsed,fileName:f.name});}catch(err){alert(`CSV import failed: ${err.message}`)}finally{e.target.value=''}
};
$('csvClose').onclick=closeCsvModal;$('csvCancel').onclick=closeCsvModal;
$('csvModal').onclick=e=>{if(e.target===$('csvModal'))closeCsvModal()};
$('csvTarget').onchange=()=>{renderCsvColumns();renderCsvProfile()};
$('csvPackName').oninput=()=>{if(!$('csvPackId').dataset.edited)$('csvPackId').value=slugify($('csvPackName').value)+'-v1'};
$('csvPackId').oninput=()=>{$('csvPackId').dataset.edited='1'};
$('selectSafeColumns').onclick=()=>{document.querySelectorAll('#csvColumns .pii input').forEach(i=>i.checked=false);renderCsvProfile()};
$('csvCreate').onclick=async()=>{try{const pack=createPackFromCsv();await api('/api/packs',{method:'POST',body:JSON.stringify(pack)});await loadPacks();$('packSelect').value=pack.id;closeCsvModal();alert(`Created ${pack.name} with ${pack.cases.length} graded cases. The ${Object.keys(pack.cases[0].expected)[0]} target is hidden from the agent.`)}catch(err){alert(`Could not create pack: ${err.message}`)}};

document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('csvModal').classList.contains('hidden'))closeCsvModal()});
Promise.all([loadPacks(),loadHistory()]).catch(console.error); providerUI();
