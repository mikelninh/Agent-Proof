"""Compose the bounded worker with verified on-runner open-weight inference.
The retired GitHub Models adapter is never called by this entrypoint.
The model receives text, never credentials, shell or customer action tools.
"""
from __future__ import annotations
import json, sys
import worker

MODEL = 'qwen3.5:2b'
ENDPOINT = 'http://127.0.0.1:11434/api/chat'


def local_completion(system: str, text: str):
    review = 'Act as a separate reviewer' in system
    limit = '150 words' if review else '300 words'
    instruction = (f' Final output must be at most {limit}. Return only the requested Markdown, no analysis or preamble. '
                   'Do not reproduce any source URL: use [README] or [SPEC] as source labels. The application attaches exact source links separately. '
                   'Do not include code examples or benchmark tables. Say quote pending where price is undecided. Stop after the requested document.')
    response = worker.request_json(ENDPOINT, {
        'model': MODEL, 'stream': False, 'think': False, 'keep_alive': '10m',
        'messages': [{'role': 'system', 'content': system + instruction},
                     {'role': 'user', 'content': text[:14000]}],
        'options': {'temperature': 0.3, 'num_predict': 1400 if review else 2000, 'num_ctx': 6144, 'num_thread': 4},
    }, timeout=250)
    content = response.get('message', {}).get('content')
    if response.get('done') is not True or not isinstance(content,str) or not content.strip():
        raise worker.DeliveryError('Local model returned no completed deliverable')
    if response.get('done_reason') == 'length':
        raise worker.DeliveryError('Local model output truncated; narrow the assignment')
    return content, {'prompt_tokens': response.get('prompt_eval_count'), 'completion_tokens': response.get('eval_count')}


def main():
    tags = worker.request_json('http://127.0.0.1:11434/api/tags',timeout=20)
    selected = next((m for m in tags.get('models',[]) if m.get('name') == MODEL),None)
    if not selected: raise worker.DeliveryError('Approved local model is not installed')
    runtime = {'model': MODEL, 'digest': selected.get('digest'), 'size': selected.get('size'),
               'runtime': worker.request_json('http://127.0.0.1:11434/api/version',timeout=20),
               'execution': 'CPU on ephemeral GitHub Actions runner',
               'hosted_model_api_key_required': False, 'independent_human_review': False}
    evidence = worker.ROOT/'company-evidence'; evidence.mkdir(exist_ok=True)
    (evidence/'model-runtime.json').write_text(json.dumps(runtime,indent=2))
    worker.MODEL = MODEL
    worker.call_model = local_completion
    original_context = worker.sources_and_context
    def bounded_context():
        context,sources=original_context();return context[:7000],sources
    worker.sources_and_context=bounded_context
    original_delivery=worker.draft_delivery
    def delivery_with_feedback(job):
        task=dict(job)
        if task.get('note'):
            task['brief'] += '\n\nFOUNDER REVISION FEEDBACK\n' + task['note'][:1000]
        result=original_delivery(task)
        result['runtime']=runtime
        result['limitations'].append('Small open-weight model; inspect factual claims and execution readiness before use.')
        return result
    worker.draft_delivery=delivery_with_feedback
    return worker.main()

if __name__ == '__main__':sys.exit(main())
