#!/usr/bin/env python3
"""ASTRA pilot: local evidence gate, paired scorecard, optional Buzz receipt bridge.

Standard library only. No autonomous workers or production actions are implied.
The database and credentials must be kept outside any agent's writable workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
ROLES = ('coordinator', 'builder', 'prover', 'reviewer', 'human')


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a finite nonnegative number')
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{name} must be a finite nonnegative number')
    return float(value)


class GateError(ValueError):
    pass


class ControlRoom:
    """Trusted single-host control process; roles are mapped from bearer tokens.

    This is not OS isolation. Workers must never receive human/prover credentials
    or write access to this database. No merge, deployment or payment tool exists.
    """
    def __init__(self, path: str | Path = ':memory:', credentials: dict | None = None):
        self.credentials = credentials if credentials is not None else {role: secrets.token_hex(32) for role in ROLES}
        if (set(self.credentials) != set(ROLES)
                or any(not isinstance(v, str) or not v for v in self.credentials.values())
                or len(set(self.credentials.values())) != len(ROLES)):
            raise ValueError('Five distinct role credentials are required')
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL,
                previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
        ''')

    def close(self) -> None:
        self.db.close()

    def _role(self, token: str) -> str:
        for role, expected in self.credentials.items():
            if isinstance(token, str) and secrets.compare_digest(token, expected):
                return role
        raise GateError('Unauthenticated caller')

    def _event(self, mission: str, role: str, action: str, data: dict) -> None:
        prior = self.db.execute('SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        previous = prior[0] if prior else '0' * 64
        body = canonical(dict(mission=mission, role=role, action=action, data=data, at_ns=time.time_ns()))
        self.db.execute('INSERT INTO events(body,previous_hash,event_hash) VALUES(?,?,?)',
                        (body, previous, hashlib.sha256((previous + body).encode()).hexdigest()))

    def get(self, mission: str) -> dict:
        row = self.db.execute('SELECT body FROM missions WHERE id=?', (mission,)).fetchone()
        if row is None:
            raise GateError('Unknown mission')
        return json.loads(row[0])

    def events(self) -> list[dict]:
        return [dict(seq=r['seq'], **json.loads(r['body']), event_hash=r['event_hash'])
                for r in self.db.execute('SELECT * FROM events ORDER BY seq')]

    def verify_log(self, expected_head: str | None = None) -> bool:
        previous = '0' * 64
        for row in self.db.execute('SELECT * FROM events ORDER BY seq'):
            computed = hashlib.sha256((previous + row['body']).encode()).hexdigest()
            if row['previous_hash'] != previous or row['event_hash'] != computed:
                return False
            previous = computed
        return expected_head is None or secrets.compare_digest(previous, expected_head)

    def act(self, token: str, mission: str, action: str, **data: Any) -> dict:
        role = self._role(token)
        if not isinstance(mission, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', mission):
            raise GateError('Invalid mission identifier')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = self._apply(role, mission, action, data)
            self.db.commit()
            return result
        except Exception as exc:
            self.db.rollback()
            if isinstance(exc, (GateError, ValueError)):
                with self.db:
                    # Do not copy arbitrary payloads, artifacts or credentials into denials.
                    self._event(mission, role, 'denied', {'attempted_action': action, 'reason': str(exc)})
            raise

    def _apply(self, role: str, mission: str, action: str, data: dict) -> dict:
        if action == 'create':
            if role != 'coordinator':
                raise GateError('Only coordinator creates missions')
            required = {'brief', 'acceptance', 'budget_units', 'max_revisions'}
            if set(data) != required or any(not isinstance(data.get(k), str) or not data[k].strip() for k in ('brief','acceptance')):
                raise GateError('Freeze brief, acceptance, budget and revision cap first')
            number(data['budget_units'], 'budget_units')
            if type(data['max_revisions']) is not int or data['max_revisions'] < 1:
                raise GateError('max_revisions must be a positive integer')
            existing = self.db.execute('SELECT body FROM missions WHERE id=?', (mission,)).fetchone()
            if existing:
                saved = json.loads(existing[0])
                if saved['spec_hash'] != digest(data):
                    raise GateError('Mission id reused with different specification')
                return saved
            state = dict(id=mission, spec_hash=digest(data), spec=data, status='specified',
                         spent_units=0, revisions=0, artifact_hash=None, evidence=None,
                         review=None, approval=None)
            self.db.execute('INSERT INTO missions VALUES(?,?)', (mission, canonical(state)))
        else:
            state = self.get(mission)
            if state['status'] in ('release_candidate', 'cancelled'):
                raise GateError('Mission is terminal')
            if action == 'submit':
                if role != 'builder':
                    raise GateError('Only builder submits artifacts')
                units = number(data.get('units'), 'units')
                if state['spent_units'] + units > state['spec']['budget_units']:
                    raise GateError('Budget exhausted')
                if state['revisions'] >= state['spec']['max_revisions']:
                    raise GateError('Revision cap reached')
                if 'artifact' not in data:
                    raise GateError('Missing artifact')
                state.update(status='submitted', artifact_hash=digest(data['artifact']),
                             spent_units=state['spent_units'] + units,
                             revisions=state['revisions'] + 1,
                             evidence=None, review=None, approval=None)
            elif action in ('prove', 'review', 'approve', 'release'):
                needed = {'prove': 'prover', 'review': 'reviewer', 'approve': 'human', 'release': 'coordinator'}[action]
                if role != needed:
                    raise GateError(f'{needed} credential required')
                if not state['artifact_hash'] or data.get('artifact_hash') != state['artifact_hash']:
                    raise GateError('Stale or missing artifact hash')
                if action == 'prove':
                    if state['status'] != 'submitted':
                        raise GateError('Proof requires submitted artifact')
                    checks = data.get('checks')
                    if not isinstance(checks, dict) or not checks or any(type(v) is not bool for v in checks.values()):
                        raise GateError('Independent named boolean checks required')
                    state['evidence'] = dict(artifact_hash=state['artifact_hash'], checks=checks)
                    state['status'] = 'proved' if all(checks.values()) else 'rejected'
                elif action == 'review':
                    if state['status'] != 'proved' or type(data.get('passed')) is not bool:
                        raise GateError('Review requires passing proof and explicit verdict')
                    state['review'] = dict(artifact_hash=state['artifact_hash'], passed=data['passed'])
                    state['status'] = 'reviewed' if data['passed'] else 'rejected'
                elif action == 'approve':
                    if state['status'] != 'reviewed':
                        raise GateError('Approval requires independent proof and review')
                    state['approval'] = dict(artifact_hash=state['artifact_hash'], by='human')
                    state['status'] = 'approved'
                else:
                    if state['status'] != 'approved':
                        raise GateError('Human approval required')
                    state['status'] = 'release_candidate'  # Local marker; NO deployment.
            elif action == 'cancel':
                if role not in ('coordinator', 'human'):
                    raise GateError('Only coordinator or human can cancel')
                state['status'] = 'cancelled'
            else:
                raise GateError('Unknown action')
            self.db.execute('UPDATE missions SET body=? WHERE id=?', (canonical(state), mission))
        # Artifact bodies are intentionally excluded from the event feed.
        self._event(mission, role, action, dict(status=state['status'], artifact_hash=state['artifact_hash']))
        return state


def wilson(success: int, total: int) -> list[float] | None:
    if not total:
        return None
    z, p = 1.959963984540054, success / total
    d = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / d
    radius = z * math.sqrt(p * (1-p) / total + z*z / (4*total*total)) / d
    return [max(0, centre-radius), min(1, centre+radius)]


def scorecard(rows: list[dict], minimum_pairs: int = 20) -> dict:
    """Compare paired, externally measured runs. Fixtures NEVER enter live metrics.

    Receipts are measurement inputs, not cryptographically verified provider bills.
    Independent graders/operators must own their creation. All attempts, including
    failures and retries, must be rolled into each task/arm receipt.
    """
    if type(minimum_pairs) is not int or minimum_pairs < 1:
        raise ValueError('minimum_pairs must be a positive integer')
    live, ignored = [], 0
    seen = set()
    for row in rows:
        if row.get('provenance') != 'live_measured':
            ignored += 1
            continue
        for name in ('task_id', 'arm', 'spec_hash', 'protocol_hash', 'artifact_hash', 'grader_ref'):
            if not isinstance(row.get(name), str) or not row[name].strip():
                raise ValueError(f'Missing {name}')
        if row['arm'] not in ('single', 'team'):
            raise ValueError('Unknown arm')
        key = (row['task_id'], row['arm'])
        if key in seen:
            raise ValueError('Duplicate task/arm receipt; aggregate retries, do not cherry-pick')
        seen.add(key)
        for name in ('accepted', 'critical_failure'):
            if type(row.get(name)) is not bool:
                raise ValueError(f'{name} must be boolean')
        if row['accepted'] and row['critical_failure']:
            raise ValueError('A critical failure cannot be accepted')
        for name in ('cash_cost_eur', 'human_minutes', 'wall_seconds'):
            if row.get(name) is not None:
                number(row[name], name)
        live.append(row)
    groups = {arm: [r for r in live if r['arm'] == arm] for arm in ('single', 'team')}
    indices = {arm: {r['task_id']: r for r in group} for arm, group in groups.items()}
    pairs = set(indices['single']) & set(indices['team'])
    for task in pairs:
        a, b = indices['single'][task], indices['team'][task]
        if a['spec_hash'] != b['spec_hash'] or a['protocol_hash'] != b['protocol_hash']:
            raise ValueError('Paired task specifications or experimental protocols differ')
    metrics = {}
    for arm, group in groups.items():
        n, accepted = len(group), sum(r['accepted'] for r in group)
        def total(name: str) -> float | None:
            return sum(r[name] for r in group) if group and all(r.get(name) is not None for r in group) else None
        cost, human, wall = total('cash_cost_eur'), total('human_minutes'), total('wall_seconds')
        metrics[arm] = dict(tasks=n, accepted=accepted, success_rate=accepted/n if n else None,
                           success_95ci=wilson(accepted,n), critical_failures=sum(r['critical_failure'] for r in group),
                           cash_cost_eur=cost, human_minutes=human, wall_seconds=wall,
                           cost_per_accepted_eur=cost/accepted if cost is not None and accepted else None,
                           human_minutes_per_accepted=human/accepted if human is not None and accepted else None,
                           accepted_per_human_hour=60*accepted/human if human else None)
    baseline, team = metrics['single'], metrics['team']
    reasons = []
    missing = (len(pairs) < minimum_pairs or any(len(g) != len(pairs) for g in groups.values())
               or len({r['protocol_hash'] for r in live}) > 1
               or any(metrics[a][k] is None for a in metrics
                      for k in ('cost_per_accepted_eur','human_minutes_per_accepted','wall_seconds')))
    if team['critical_failures']:
        reasons.append('Critical failures observed: block regardless of sample size')
        verdict = 'BLOCK'
    elif missing:
        verdict = 'INSUFFICIENT_EVIDENCE'
        reasons.append('Need complete, same-protocol paired live runs and measured cost/time; fixtures do not qualify')
    else:
        if team['success_rate'] < .8 or team['success_rate'] < baseline['success_rate']:
            reasons.append('Team must achieve >=80% acceptance without lower quality than baseline')
        if not baseline['human_minutes_per_accepted'] or team['human_minutes_per_accepted'] > .5 * baseline['human_minutes_per_accepted']:
            reasons.append('Human minutes per accepted task must fall by at least 50%')
        if team['cost_per_accepted_eur'] > baseline['cost_per_accepted_eur']:
            reasons.append('Cash cost per accepted task must not increase')
        verdict = 'HOLD' if reasons else 'PILOT_TARGET_MET'
    return dict(verdict=verdict, reasons=reasons, minimum_pairs=minimum_pairs,
                complete_pairs=len(pairs), ignored_fixture_rows=ignored, metrics=metrics,
                caveat='Exploratory point-estimate gate, not proof of generalisation or production safety. Imported receipts are not independently authenticated.')


class BuzzBridge:
    """Optional, one-way receipt publisher. Not an agent runner or approval gate."""
    def __init__(self, channel: str, executable: str = 'buzz'):
        if not re.fullmatch(r'[0-9a-fA-F-]{36}', channel):
            raise ValueError('Use an explicit Buzz channel UUID')
        self.channel, self.executable = channel, executable

    def publish(self, event: dict) -> str:
        url = urlparse(os.environ.get('BUZZ_RELAY_URL', ''))
        if not os.environ.get('BUZZ_PRIVATE_KEY'):
            raise GateError('BUZZ_PRIVATE_KEY is not configured')
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')):
            raise GateError('Use HTTPS for remote relays or HTTP loopback for local development')
        # Fixed whitelist; do not send arbitrary task bodies, credentials or personal data.
        safe = {k: event[k] for k in ('seq','mission','role','action','event_hash') if k in event}
        result = subprocess.run([self.executable, 'messages', 'send', '--channel', self.channel,
                                 '--content', '-'], input=canonical(safe), text=True,
                                capture_output=True, timeout=20, check=False)
        if result.returncode:
            raise GateError(f'Buzz CLI failed with exit code {result.returncode}; output withheld')
        try:
            event_id = json.loads(result.stdout)['event_id']
        except (ValueError, KeyError, TypeError) as exc:
            raise GateError('Buzz returned no usable receipt') from exc
        if not isinstance(event_id, str) or not re.fullmatch(r'[0-9a-f]{64}', event_id):
            raise GateError('Buzz returned an invalid event id')
        return event_id


def demo() -> dict:
    """Exercise actual gate code using scripted role clients, NOT AI agents."""
    room = ControlRoom()
    def act(role, mission, action, **data):
        return room.act(room.credentials[role], mission, action, **data)
    results = []
    for name in ('happy_path','missing_proof','builder_self_approval','stale_approval','budget_cap','revision_cap','failed_test','cancelled'):
        act('coordinator', name, 'create', brief='Produce a reviewed fixture artifact',
            acceptance='Independent checks pass; human approves the exact hash', budget_units=2, max_revisions=2)
        state = act('builder', name, 'submit', artifact={'fixture':1}, units=1)
        h = state['artifact_hash']
        observed = ''
        try:
            if name == 'missing_proof':
                act('human',name,'approve',artifact_hash=h)
            elif name == 'builder_self_approval':
                act('builder',name,'approve',artifact_hash=h)
            elif name == 'budget_cap':
                act('builder',name,'submit',artifact={'fixture':2},units=2)
            elif name == 'revision_cap':
                act('builder',name,'submit',artifact={'fixture':2},units=0)
                act('builder',name,'submit',artifact={'fixture':3},units=0)
            elif name == 'cancelled':
                act('human',name,'cancel')
                act('builder',name,'submit',artifact={'fixture':2},units=0)
            else:
                act('prover',name,'prove',artifact_hash=h,checks={'artifact_contract':name != 'failed_test'})
                act('reviewer',name,'review',artifact_hash=h,passed=True)
                act('human',name,'approve',artifact_hash=h)
                if name == 'stale_approval':
                    act('builder',name,'submit',artifact={'fixture':2},units=1)
                act('coordinator',name,'release',artifact_hash=h)
            observed = 'release_candidate'
        except GateError as exc:
            observed = str(exc)
        results.append(dict(scenario=name, observed=observed, status=room.get(name)['status'],
                            expected='release_candidate' if name == 'happy_path' else 'blocked'))
    report = dict(schema='astra-pilot-v1', provenance='scripted_controls_only',
                  agent_runs=0, buzz_live_verified=False, production_actions=0,
                  scenarios=results, log_valid=room.verify_log(), events=room.events(),
                  scorecard=scorecard([]))
    room.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    smoke = commands.add_parser('demo')
    smoke.add_argument('--output', type=Path, default=ROOT/'evidence'/'demo.json')
    compare = commands.add_parser('compare')
    compare.add_argument('receipts', type=Path)
    compare.add_argument('--minimum-pairs', type=int, default=20)
    compare.add_argument('--output', type=Path)
    render = commands.add_parser('render')
    render.add_argument('--input', type=Path, default=ROOT/'evidence'/'demo.json')
    render.add_argument('--output', type=Path, default=ROOT/'control-room.html')
    bridge = commands.add_parser('buzz-publish')
    bridge.add_argument('--channel', required=True)
    bridge.add_argument('--input', type=Path, required=True)
    bridge.add_argument('--confirm-publish', action='store_true')
    args = parser.parse_args()
    if args.command == 'demo':
        report = demo()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k != 'events'}, indent=2))
    elif args.command == 'compare':
        if args.minimum_pairs < 1:
            parser.error('minimum-pairs must be positive')
        result = scorecard(json.loads(args.receipts.read_text(encoding='utf-8')),args.minimum_pairs)
        text = json.dumps(result, indent=2)
        if args.output:
            args.output.write_text(text,encoding='utf-8')
        print(text)
        raise SystemExit(0 if result['verdict'] == 'PILOT_TARGET_MET' else 2)
    elif args.command == 'render':
        data = json.loads(args.input.read_text(encoding='utf-8'))
        # Escape script terminators from imported text.
        payload = json.dumps(data, allow_nan=False).translate({60: chr(92) + 'u003c', 62: chr(92) + 'u003e', 38: chr(92) + 'u0026'})
        template = (ROOT/'dashboard.html').read_text(encoding='utf-8')
        args.output.write_text(template.replace('__REPORT_JSON__',payload),encoding='utf-8')
        print(args.output)
    else:
        if not args.confirm_publish:
            parser.error('Publishing requires --confirm-publish and a trusted relay/channel')
        report = json.loads(args.input.read_text(encoding='utf-8'))
        event = report['events'][-1]
        print(json.dumps({'buzz_event_id':BuzzBridge(args.channel).publish(event),
                          'status':'CLI_ACKNOWLEDGED_NOT_READBACK_VERIFIED'}))


if __name__ == '__main__':
    main()
