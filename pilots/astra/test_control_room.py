"""Executable control, measurement and CLI-contract checks. No real LLM claims."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from control_room import BuzzBridge, ControlRoom, GateError, ROLES, demo, digest, scorecard


class GateTests(unittest.TestCase):
    def setUp(self):
        self.room = ControlRoom()
        self.act('coordinator','create',brief='Fixture task',acceptance='Independent expected output',budget_units=3,max_revisions=2)

    def tearDown(self):
        self.room.close()

    def act(self,role,action,**data):
        return self.room.act(self.room.credentials[role],'task-1',action,**data)

    def submit(self,artifact=None):
        return self.act('builder','submit',artifact=artifact or {'result':42},units=1)['artifact_hash']

    def approved(self):
        h=self.submit()
        self.act('prover','prove',artifact_hash=h,checks={'independent_contract':True})
        self.act('reviewer','review',artifact_hash=h,passed=True)
        self.act('human','approve',artifact_hash=h)
        return h

    def test_happy_path(self):
        h=self.approved()
        self.assertEqual('release_candidate',self.act('coordinator','release',artifact_hash=h)['status'])

    def test_invalid_credential(self):
        with self.assertRaises(GateError):
            self.room.act('fake','task-1','cancel')

    def test_builder_cannot_self_prove(self):
        h=self.submit()
        with self.assertRaises(GateError):
            self.act('builder','prove',artifact_hash=h,checks={'test':True})

    def test_builder_cannot_self_approve(self):
        h=self.submit()
        with self.assertRaises(GateError):
            self.act('builder','approve',artifact_hash=h,claimed_role='human')

    def test_coordinator_cannot_approve(self):
        h=self.submit()
        with self.assertRaises(GateError):
            self.act('coordinator','approve',artifact_hash=h)

    def test_missing_proof_blocks_approval(self):
        with self.assertRaises(GateError):
            self.act('human','approve',artifact_hash=self.submit())

    def test_failed_check_blocks_review(self):
        h=self.submit()
        self.act('prover','prove',artifact_hash=h,checks={'critical':False,'format':True})
        with self.assertRaises(GateError):
            self.act('reviewer','review',artifact_hash=h,passed=True)

    def test_empty_or_string_checks_rejected(self):
        h=self.submit()
        for checks in ({},{'a':'true'},{'a':1},None):
            with self.subTest(checks=checks), self.assertRaises(GateError):
                self.act('prover','prove',artifact_hash=h,checks=checks)

    def test_false_review_blocks_human(self):
        h=self.submit()
        self.act('prover','prove',artifact_hash=h,checks={'a':True})
        self.act('reviewer','review',artifact_hash=h,passed=False)
        with self.assertRaises(GateError):
            self.act('human','approve',artifact_hash=h)

    def test_stale_proof_rejected(self):
        old=self.submit(); self.submit({'result':43})
        with self.assertRaises(GateError):
            self.act('prover','prove',artifact_hash=old,checks={'a':True})

    def test_edit_invalidates_approval(self):
        h=self.approved(); fresh=self.submit({'result':43})
        self.assertIsNone(self.room.get('task-1')['approval'])
        for sha in (h,fresh):
            with self.assertRaises(GateError):
                self.act('coordinator','release',artifact_hash=sha)

    def test_approval_replay_rejected(self):
        h=self.approved()
        self.act('coordinator','release',artifact_hash=h)
        with self.assertRaises(GateError):
            self.act('coordinator','release',artifact_hash=h)
        self.assertEqual(1,len([e for e in self.room.events() if e['action']=='release']))

    def test_budget_is_not_spent_on_rejection(self):
        self.submit()
        with self.assertRaises(GateError):
            self.act('builder','submit',artifact={'a':1},units=3)
        self.assertEqual(1,self.room.get('task-1')['spent_units'])

    def test_invalid_budget_values(self):
        for bad in (-1,float('nan'),float('inf'),True,'1'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.act('builder','submit',artifact={'a':1},units=bad)

    def test_revision_cap(self):
        self.submit(); self.submit({'result':43})
        with self.assertRaises(GateError):
            self.act('builder','submit',artifact={'result':44},units=0)

    def test_cancellation_terminal(self):
        self.act('human','cancel')
        with self.assertRaises(GateError):
            self.submit()

    def test_idempotent_create(self):
        before=len(self.room.events())
        self.act('coordinator','create',brief='Fixture task',acceptance='Independent expected output',budget_units=3,max_revisions=2)
        self.assertEqual(before,len(self.room.events()))

    def test_reused_id_different_spec_rejected(self):
        with self.assertRaises(GateError):
            self.act('coordinator','create',brief='Different task',acceptance='anything',budget_units=3,max_revisions=2)

    def test_unknown_action_rejected(self):
        with self.assertRaises(GateError):
            self.act('builder','send_money',amount=10)

    def test_invalid_mission_id(self):
        with self.assertRaises(GateError):
            self.room.act(self.room.credentials['human'],'../task','cancel')

    def test_shared_credentials_rejected(self):
        with self.assertRaises(ValueError):
            ControlRoom(credentials={r:'shared' for r in ROLES})

    def test_log_detects_tampering(self):
        self.submit()
        self.assertTrue(self.room.verify_log())
        with self.room.db:
            self.room.db.execute("UPDATE events SET body='{}' WHERE seq=1")
        self.assertFalse(self.room.verify_log())

    def test_anchor_detects_truncation(self):
        self.submit(); head=self.room.events()[-1]['event_hash']
        with self.room.db:
            self.room.db.execute('DELETE FROM events WHERE seq=(SELECT MAX(seq) FROM events)')
        self.assertFalse(self.room.verify_log(head))

    def test_denials_are_audited_without_payload(self):
        with self.assertRaises(GateError):
            self.act('builder','send_money',secret='do-not-log')
        self.assertEqual('denied',self.room.events()[-1]['action'])
        self.assertNotIn('do-not-log',json.dumps(self.room.events()))

    def test_restart_preserves_state_and_log(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'room.db'; creds=self.room.credentials
            first=ControlRoom(path,creds)
            first.act(creds['coordinator'],'persist','create',brief='b',acceptance='a',budget_units=1,max_revisions=1)
            first.close()
            second=ControlRoom(path,creds)
            self.assertEqual('specified',second.get('persist')['status'])
            self.assertTrue(second.verify_log()); second.close()


class MetricsTests(unittest.TestCase):
    def rows(self,n=20):
        # These are fabricated unit-test inputs, never published as observed live runs.
        return [dict(task_id=f't{i}',arm=arm,spec_hash=f'spec{i}',protocol_hash='protocol-v1',
                     artifact_hash=f'artifact{i}',grader_ref=f'test-fixture-{i}',provenance='live_measured',
                     accepted=True,critical_failure=False,cash_cost_eur=1,
                     human_minutes=10 if arm=='single' else 4,wall_seconds=30)
                for i in range(n) for arm in ('single','team')]

    def test_no_data_is_not_success(self):
        self.assertEqual('INSUFFICIENT_EVIDENCE',scorecard([])['verdict'])

    def test_targets_pass_on_fabricated_inputs_only(self):
        self.assertEqual('PILOT_TARGET_MET',scorecard(self.rows())['verdict'])

    def test_fixtures_never_count_as_live(self):
        rows=self.rows()
        for row in rows: row['provenance']='scripted_controls_only'
        report=scorecard(rows)
        self.assertEqual(0,report['complete_pairs'])
        self.assertEqual(40,report['ignored_fixture_rows'])
        self.assertEqual('INSUFFICIENT_EVIDENCE',report['verdict'])

    def test_small_sample_insufficient(self):
        self.assertEqual('INSUFFICIENT_EVIDENCE',scorecard(self.rows(19))['verdict'])

    def test_unpaired_run_insufficient(self):
        self.assertEqual('INSUFFICIENT_EVIDENCE',scorecard(self.rows()[:-1])['verdict'])

    def test_duplicate_run_rejected(self):
        rows=self.rows()
        with self.assertRaises(ValueError): scorecard(rows+[rows[0]])

    def test_mismatched_specs_rejected(self):
        rows=self.rows();rows[0]['spec_hash']='other'
        with self.assertRaises(ValueError): scorecard(rows)

    def test_mismatched_protocol_rejected(self):
        rows=self.rows();rows[0]['protocol_hash']='other'
        with self.assertRaises(ValueError): scorecard(rows)

    def test_multiple_protocols_insufficient(self):
        rows=self.rows();rows[0]['protocol_hash']=rows[1]['protocol_hash']='other'
        self.assertEqual('INSUFFICIENT_EVIDENCE',scorecard(rows)['verdict'])

    def test_unknown_cost_not_zero(self):
        rows=self.rows();rows[1]['cash_cost_eur']=None
        report=scorecard(rows)
        self.assertIsNone(report['metrics']['team']['cost_per_accepted_eur'])
        self.assertEqual('INSUFFICIENT_EVIDENCE',report['verdict'])

    def test_unknown_time_insufficient(self):
        rows=self.rows();rows[1]['human_minutes']=None
        self.assertEqual('INSUFFICIENT_EVIDENCE',scorecard(rows)['verdict'])

    def test_failure_costs_in_denominator(self):
        rows=self.rows();rows[1]['accepted']=False
        report=scorecard(rows)
        self.assertAlmostEqual(20/19,report['metrics']['team']['cost_per_accepted_eur'])
        self.assertAlmostEqual(80/19,report['metrics']['team']['human_minutes_per_accepted'])

    def test_critical_failure_blocks_even_with_missing_cost(self):
        rows=self.rows(1);rows[1].update(accepted=False,critical_failure=True,cash_cost_eur=None)
        self.assertEqual('BLOCK',scorecard(rows)['verdict'])

    def test_cannot_accept_critical_failure(self):
        rows=self.rows();rows[1]['critical_failure']=True
        with self.assertRaises(ValueError): scorecard(rows)

    def test_zero_human_time_not_infinite_productivity(self):
        rows=self.rows()
        for row in rows: row['human_minutes']=0
        report=scorecard(rows)
        self.assertIsNone(report['metrics']['team']['accepted_per_human_hour'])
        self.assertEqual('HOLD',report['verdict'])

    def test_cost_regression_holds(self):
        rows=self.rows();rows[1]['cash_cost_eur']=100
        self.assertEqual('HOLD',scorecard(rows)['verdict'])

    def test_invalid_measurements_rejected(self):
        for bad in (float('nan'),float('inf'),-1,True,'1'):
            rows=self.rows();rows[1]['cash_cost_eur']=bad
            with self.subTest(bad=bad), self.assertRaises(ValueError): scorecard(rows)

    def test_missing_evidence_ref_rejected(self):
        rows=self.rows();rows[1]['grader_ref']=''
        with self.assertRaises(ValueError): scorecard(rows)

    def test_wilson_not_100_percent_certain(self):
        interval=scorecard(self.rows())['metrics']['team']['success_95ci']
        self.assertLess(interval[0],1)
        self.assertAlmostEqual(interval[1],1)

    def test_bad_minimum_rejected(self):
        for value in (0,-1,True):
            with self.assertRaises(ValueError): scorecard([],value)


class BridgeTests(unittest.TestCase):
    CHANNEL='12345678-1234-1234-1234-123456789abc'

    def test_missing_identity_fails_closed(self):
        with patch.dict(os.environ,{},clear=True), self.assertRaises(GateError):
            BuzzBridge(self.CHANNEL).publish({})

    def test_remote_plaintext_rejected(self):
        with patch.dict(os.environ,{'BUZZ_PRIVATE_KEY':'test','BUZZ_RELAY_URL':'http://example.com'}), self.assertRaises(GateError):
            BuzzBridge(self.CHANNEL).publish({})

    def test_cli_contract_uses_stdin_and_no_shell(self):
        result=subprocess.CompletedProcess([],0,json.dumps({'event_id':'a'*64}),'')
        with patch.dict(os.environ,{'BUZZ_PRIVATE_KEY':'test','BUZZ_RELAY_URL':'https://example.com'}), patch('control_room.subprocess.run',return_value=result) as run:
            self.assertEqual('a'*64,BuzzBridge(self.CHANNEL).publish({'mission':'task','secret':'never-send'}))
            args,kwargs=run.call_args
            self.assertEqual(['buzz','messages','send','--channel',self.CHANNEL,'--content','-'],args[0])
            self.assertNotIn('secret',kwargs['input'])
            self.assertFalse(kwargs.get('shell',False))

    def test_failure_does_not_leak_cli_output(self):
        result=subprocess.CompletedProcess([],3,'','sensitive')
        with patch.dict(os.environ,{'BUZZ_PRIVATE_KEY':'test','BUZZ_RELAY_URL':'https://example.com'}), patch('control_room.subprocess.run',return_value=result):
            with self.assertRaises(GateError) as error: BuzzBridge(self.CHANNEL).publish({})
            self.assertNotIn('sensitive',str(error.exception))

    def test_malformed_ack_fails(self):
        for output in ('{}','not-json',json.dumps({'event_id':'bad'})):
            result=subprocess.CompletedProcess([],0,output,'')
            with patch.dict(os.environ,{'BUZZ_PRIVATE_KEY':'test','BUZZ_RELAY_URL':'https://example.com'}), patch('control_room.subprocess.run',return_value=result), self.assertRaises(GateError):
                BuzzBridge(self.CHANNEL).publish({})

    def test_simulated_replay_never_claims_live_agents(self):
        report=demo()
        self.assertEqual(8,len(report['scenarios']))
        self.assertEqual(0,report['agent_runs'])
        self.assertFalse(report['buzz_live_verified'])
        self.assertEqual('INSUFFICIENT_EVIDENCE',report['scorecard']['verdict'])
        self.assertTrue(report['log_valid'])
        self.assertEqual(1,sum(r['status']=='release_candidate' for r in report['scenarios']))


if __name__=='__main__': unittest.main(verbosity=2)
