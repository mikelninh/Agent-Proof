export const KINDS=['service_pack','support_evaluation','launch_brief','custom_brief'];
export function stable(value){if(value===null||typeof value!=='object')return JSON.stringify(value);if(Array.isArray(value))return '['+value.map(stable).join(',')+']';return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}';}
export function validateAction(action,data,actor){
 if(!data||Array.isArray(data)||typeof data!=='object')throw Error('Object required');
 const allowed=actor==='founder'?['snapshot','create','pause','decide','retry']:actor==='worker'?['claim','finish','fail']:[];
 if(!allowed.includes(action))throw Error('Action denied');
 if(action==='create'){
 if(!KINDS.includes(data.kind)||typeof data.title!=='string'||!data.title.trim()||data.title.length>180)throw Error('Invalid job');
 if(typeof data.brief!=='string'||data.brief.length>6000||typeof data.request_key!=='string'||data.request_key.length<8||data.request_key.length>120)throw Error('Invalid brief or request key');
 if(!Number.isInteger(data.priority)||data.priority<0||data.priority>100)throw Error('Invalid priority');}
 if(action==='pause'&&typeof data.paused!=='boolean')throw Error('Boolean required');
 if(['finish','fail','decide','retry'].includes(action)&&!/^[0-9a-f-]{36}$/.test(data.id||''))throw Error('Job ID required');
 if(['finish','fail'].includes(action)&&!/^[0-9a-f-]{36}$/.test(data.lease_token||''))throw Error('Lease required');
 if(action==='decide'&&(!['approve','reject'].includes(data.decision)||!/^[0-9a-f]{64}$/.test(data.result_hash||'')))throw Error('Version-bound decision required');
 if(data.note!==undefined&&(typeof data.note!=='string'||data.note.length>1000))throw Error('Note too long');
 if(action==='finish')validateResult(data.result);return data;
}
export function validateResult(r){
 if(!r||!['model_backed','deterministic'].includes(r.mode)||typeof r.summary!=='string'||!r.summary.trim()||r.summary.length>2000)throw Error('Evidence summary required');
 if(!Array.isArray(r.artifacts)||r.artifacts.length<1||r.artifacts.length>5)throw Error('1–5 artifacts required');
 const seen=new Set();for(const a of r.artifacts){if(!/^[a-zA-Z0-9_-]+\.(md|json|txt)$/.test(a.name||'')||seen.has(a.name)||typeof a.content!=='string'||!a.content.trim()||a.content.length>60000)throw Error('Invalid artifact');seen.add(a.name);}
 if(!Array.isArray(r.sources)||r.sources.length>20||r.sources.some(s=>typeof s!=='string'||!s.startsWith('https://github.com/mikelninh/Agent-Proof/')||s.length>500))throw Error('Invalid source');
 if(!r.usage||!['not_billed_here','reported_tokens','unknown'].includes(r.usage.status))throw Error('Usage status required');
 for(const key of ['input_tokens','output_tokens'])if(r.usage[key]!==null&&(!Number.isInteger(r.usage[key])||r.usage[key]<0))throw Error('Invalid token usage');
 if(r.mode==='model_backed'&&(typeof r.model!=='string'||!r.model))throw Error('Model required');
 if(stable(r).length>180000)throw Error('Evidence too large');return r;
}
export function validClaims(p,now=Math.floor(Date.now()/1000)){return p.iss==='https://token.actions.githubusercontent.com'&&p.aud==='astra-company'&&p.repository==='mikelninh/Agent-Proof'&&p.repository_id==='1371282495'&&p.ref==='refs/heads/astra/company-operations'&&p.workflow_ref==='mikelninh/Agent-Proof/.github/workflows/astra-company.yml@refs/heads/astra/company-operations'&&['push','workflow_dispatch'].includes(p.event_name)&&Number.isFinite(p.exp)&&p.exp>now&&Number.isFinite(p.iat)&&p.iat<=now+30&&now-p.iat<=900&&p.exp-p.iat<=900&&(p.nbf===undefined||p.nbf<=now+30);}