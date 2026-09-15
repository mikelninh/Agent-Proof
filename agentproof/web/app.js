const $ = (id) => document.getElementById(id);
const fmtPct = (x) => `${(x*100).toFixed(1)}%`;
const fmtEur = (x) => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(x);
const fmtSmallEur = (x) => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:4}).format(x);
const fmtSignedPct = (x) => `${x>=0?'+':''}${(x*100).toFixed(1)}%`;
const fmtSignedEur = (x) => `${x>=0?'+':''}${new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(x)}`;
let currentRun = null;
let currentComparison = null;
let latestRuns = [];

async function api(url, options={}) {
  const r = await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options});
  if(!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json();
}

async function loadPacks(){
  const packs=await api('/api/packs');
  $('packSelect').innerHTML=packs.map(p=>`<option value="${p.id}">${p.name} · ${p.case_count} cases</option>`).join('');
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
  const m=run.metrics;
  $('runTitle').textContent=`${run.pack_name} · ${run.agent.name}`;
  $('metrics').innerHTML=[
    metric('Deployment gate',run.gate.status==='pass'?'PASS':'BLOCKED',run.gate.reasons[0]||'thresholds satisfied',run.gate.status==='pass'?'good':'danger'),
    metric('Success',fmtPct(m.success_rate),`${m.total_cases} cases`,m.success_rate>=.9?'good':''),
    metric('Critical failures',fmtPct(m.critical_failure_rate),'block → approve',m.critical_failure_rate>0?'danger':'good'),
    metric('Avg cost / case',fmtSmallEur(m.agent_cost_per_case_eur),`human ${fmtSmallEur(m.human_cost_per_case_eur)}`),
    metric('Annual savings',fmtEur(m.estimated_annual_savings_eur),`${run.economics.annual_case_volume.toLocaleString()} cases/year`,'good'),
    metric('First-year ROI',m.roi_multiple===null?'—':`${m.roi_multiple.toFixed(1)}×`,`${fmtEur(run.economics.implementation_cost_eur)} implementation`)
  ].join('');
  const critical=run.cases.filter(c=>c.grade.critical_failure).length;
  const failed=run.cases.filter(c=>!c.grade.passed).length;
  $('summaryStrip').innerHTML=`<span><b>${failed}</b> mismatches</span><span><b>${critical}</b> critical</span><span><b>${fmtPct(m.escalation_rate)}</b> escalated</span><span><b>${m.avg_latency_ms.toFixed(0)}ms</b> avg latency</span>`;
  $('caseRows').innerHTML=run.cases.map((c,i)=>{
    const exp=c.expected.decision||'—', act=c.output.parsed.decision||'error';
    const risk=c.grade.critical_failure?'<span class="pill critical">critical</span>':c.grade.passed?'<span class="pill ok">pass</span>':'<span class="pill review">mismatch</span>';
    return `<tr data-i="${i}"><td>${c.title}</td><td><span class="pill ${exp}">${exp}</span></td><td><span class="pill ${act}">${act}</span></td><td>${(c.grade.score*100).toFixed(0)}</td><td>${risk}</td></tr>`
  }).join('');
  document.querySelectorAll('#caseRows tr').forEach(tr=>tr.onclick=()=>renderTrace(run.cases[Number(tr.dataset.i)]));
  $('results').classList.remove('hidden');
  $('results').scrollIntoView({behavior:'smooth',block:'start'});
}

function renderTrace(c){
  $('traceEmpty').classList.add('hidden'); $('trace').classList.remove('hidden');
  const reasons=c.grade.reasons.length?c.grade.reasons.map(r=>`<div class="reason">${r}</div>`).join(''):'<div class="pill ok">all graded fields matched</div>';
  $('trace').innerHTML=`
    <div class="trace-block"><h4>Case input</h4><pre>${escapeHtml(JSON.stringify(c.input,null,2))}</pre></div>
    <div class="trace-block"><h4>Agent output</h4><pre>${escapeHtml(c.output.raw_text || c.output.error || 'No output')}</pre></div>
    <div class="trace-block"><h4>Ground truth</h4><pre>${escapeHtml(JSON.stringify(c.expected,null,2))}</pre></div>
    <div class="trace-block"><h4>Grader</h4>${reasons}</div>
    <div class="trace-block"><h4>Runtime evidence</h4><pre>${c.output.latency_ms.toFixed(0)} ms\n${c.output.input_tokens} input tokens\n${c.output.output_tokens} output tokens\n${fmtSmallEur(c.output.estimated_cost_eur)}</pre></div>`;
}
function escapeHtml(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#039;','"':'&quot;'}[c]))}

async function loadHistory(){
  const runs=await api('/api/runs');
  latestRuns=runs;
  $('history').innerHTML=runs.length?runs.map(r=>`<div class="history-card" data-id="${r.id}"><div><strong>${r.pack_name}</strong><br/><span>${r.agent_name}${r.model?' · '+r.model:''}</span></div><div><span>Success</span><br/><div class="num">${fmtPct(r.metrics.success_rate)}</div></div><div><span>Critical</span><br/><div class="num">${fmtPct(r.metrics.critical_failure_rate)}</div></div><div><span>Savings</span><br/><div class="num">${fmtEur(r.metrics.estimated_annual_savings_eur)}</div></div><div><span>Run</span><br/><div class="num">${new Date(r.created_at).toLocaleString()}</div></div></div>`).join(''):'<div class="empty">No runs yet. Run the demo to create your first evidence record.</div>';
  document.querySelectorAll('.history-card').forEach(el=>el.onclick=async()=>renderRun(await api('/api/runs/'+el.dataset.id)));
  const options=runs.map(r=>`<option value="${r.id}">${r.pack_name} · ${r.agent_name} · ${fmtPct(r.metrics.success_rate)}</option>`).join('');
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

Promise.all([loadPacks(),loadHistory()]).catch(console.error); providerUI();
