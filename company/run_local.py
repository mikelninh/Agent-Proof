"""Compose the bounded company worker with an on-runner open-weight model.
GitHub Models was retired 2026-07-30. This entrypoint never calls it.
The model sees text, not credentials, shell access or customer action tools.
"""
from __future__ import annotations
import json, pathlib, sys
import worker

MODEL = 'qwen3.5:2b'
ENDPOINT = 'http://127.0.0.1:11434/api/chat'


def local_completion(system: str, text: str):
    response = worker.request_json(ENDPOINT, {
        'model': MODEL, 'stream': False, 'think': False, 'keep_alive': '10m',
        'messages': [{'role': 'system', 'content': system + ' Keep the deliverable under 420 words. Do not append invented links.'},
                     {'role': 'user', 'content': text[:16000]}],
        'options': {'temperature': 0.3, 'num_predict': 1000, 'num_ctx': 6144, 'num_thread': 4},
    }, timeout=250)
    content = response.get('message', {}).get('content')
    if response.get('done') is not True or not isinstance(content,str) or not content.strip():
        raise worker.DeliveryError('Local model returned no completed deliverable')
    if response.get('done_reason') == 'length':
        raise worker.DeliveryError('Local model output truncated; narrow the assignment')
    return content, {'prompt_tokens': response.get('prompt_eval_count'), 'completion_tokens': response.get('eval_count')}


def main():
    # A fixed adapter is selected by the trusted workflow, never by the brief.
    tags = worker.request_json('http://127.0.0.1:11434/api/tags',timeout=20)
    selected = next((m for m in tags.get('models',[]) if m.get('name') == MODEL),None)
    if not selected: raise worker.DeliveryError('Approved local model is not installed')
    evidence = worker.ROOT/'company-evidence'; evidence.mkdir(exist_ok=True)
    (evidence/'model-runtime.json').write_text(json.dumps({
        'model': MODEL, 'digest': selected.get('digest'), 'size': selected.get('size'),
        'runtime': worker.request_json('http://127.0.0.1:11434/api/version',timeout=20),
        'execution': 'CPU on ephemeral GitHub Actions runner',
        'hosted_model_api_key_required': False, 'independent_human_review': False,
    },indent=2))
    worker.MODEL = MODEL
    worker.call_model = local_completion
    original_context = worker.sources_and_context
    def bounded_context():
        context,sources=original_context();return context[:9000],sources
    worker.sources_and_context=bounded_context
    return worker.main()

if __name__ == '__main__':sys.exit(main())
