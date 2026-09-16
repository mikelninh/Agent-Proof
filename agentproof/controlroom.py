"""ASTRA evidence pilot. Standard library only; no merge/deploy capability.

Configured commands are trusted programs, NOT security-sandboxed agents. Run
untrusted agents in externally isolated workers. Buzz is an optional evidence
mirror, never the approval authority. See .ai-build/CONTROLROOM_PILOT.md.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any
import uuid

Json = dict[str, Any]
MAX_BYTES = 1_000_000


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def finite(value: Any, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"invalid {name}")
    return float(value)


def atomic_json(path: Path, value: Any) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temp.replace(path)


class Ledger:
    """Local hash chain detects edits; not authenticated or immutable storage."""
    def __init__(self, path: Path):
        self.path = path
        self.events: list[Json] = []
        if path.exists():
            self.events = [json.loads(x) for x in path.read_text().splitlines()]
            self.verify(self.events)

    @staticmethod
    def verify(events: list[Json]) -> None:
        previous = "0" * 64
        for index, event in enumerate(events):
            body = {k: v for k, v in event.items() if k != "hash"}
            if (body.get("seq") != index or body.get("previous") != previous
                    or digest(body) != event.get("hash")):
                raise ValueError("event-chain verification failed")
            previous = event["hash"]

    def emit(self, kind: str, **data: Any) -> Json:
        body = {"seq": len(self.events), "previous": self.events[-1]["hash"]
                if self.events else "0" * 64,
                "at": datetime.now(timezone.utc).isoformat(), "kind": kind,
                "data": data}
        event = dict(body, hash=digest(body))
        with self.path.open("a") as stream:
            stream.write(canonical(event) + "\n")
        self.events.append(event)
        return event


def call_worker(argv: list[str], payload: Json, timeout: float, cwd: Path) -> Json:
    """JSON stdin/stdout, bounded wait/output read, no shell interpolation.

    Only allowlisted environment variables are inherited. Temporary output files
    avoid RAM growth, but disk quotas / OS isolation belong to the worker host.
    """
    if not argv or not all(isinstance(x, str) and x for x in argv):
        raise ValueError("worker command must be a nonempty argv array")
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
           if k in os.environ}
    env.update({"LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"})
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=output,
                                stderr=errors, cwd=cwd, env=env,
                                start_new_session=(os.name == "posix"))
        try:
            proc.communicate(canonical(payload).encode(), timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.communicate()
            raise TimeoutError("worker exceeded deadline") from None
        if proc.returncode:
            # Raw stderr can contain secrets: retain the exit code, not the body.
            raise ValueError(f"worker exited {proc.returncode}")
        output.seek(0)
        raw = output.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("worker output exceeded limit")
    try:
        result = json.loads(raw)
        canonical(result)  # rejects non-finite values, including NaN
    except (ValueError, UnicodeError):
        raise ValueError("invalid worker JSON") from None
    if not isinstance(result, dict):
        raise ValueError("worker must return a JSON object")
    return result


def run_mission(mission: Json, directory: Path) -> Json:
    """Run a bounded builder -> independent verifier -> reviewer loop.

    Outputs are artifacts, not executed code. Only operator-configured commands
    execute. The verifier decides correctness, not the builder/reviewer.
    """
    required = ("id", "brief", "builder", "verifier", "reviewer")
    if any(k not in mission for k in required):
        raise ValueError("incomplete mission")
    for role in ("builder", "verifier", "reviewer"):
        worker = mission[role]
        if not isinstance(worker.get("id"), str) or not worker["id"]:
            raise ValueError("every worker needs an id")
        argv = worker.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
            raise ValueError("every worker needs a command array")
    identities = [mission[r]["id"] for r in ("builder", "verifier", "reviewer")]
    if len(set(identities)) != 3:
        raise ValueError("builder, verifier and reviewer identities must differ")
    attempts = mission.get("max_attempts", 2)
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError("max_attempts must be 1..3")
    timeout = finite(mission.get("worker_timeout_seconds", 15), "worker timeout", .01)
    deadline = finite(mission.get("mission_timeout_seconds", 60), "mission timeout", .01)
    if timeout > 300 or deadline > 900:
        raise ValueError("pilot deadline exceeds permitted range")
    execution_kind = mission.get("execution_kind", "fixture")
    if execution_kind not in ("fixture", "operator_commands"):
        raise ValueError("invalid execution kind")
    # A previous run can be inspected, never silently replayed or overwritten.
    directory.mkdir(parents=True, exist_ok=False)
    ledger = Ledger(directory / "events.jsonl")
    started = time.monotonic()
    mission_hash = digest(mission)
    ledger.emit("specified", mission_id=mission["id"], mission_hash=mission_hash,
                execution_kind=execution_kind, max_attempts=attempts)
    result: Json = {"schema": 1, "run_id": directory.name, "mission_id": mission["id"],
                   "mission_hash": mission_hash, "execution_kind": execution_kind,
                   "status": "blocked", "reason": "attempt_limit", "attempts": 0,
                   "artifact_hash": None, "provider_cost_eur": None,
                   "human_minutes": None, "released": False, "buzz_delivery": "not_attempted"}
    feedback: Json = {}
    # Snapshot operator-selected files and check before/after every worker.
    frozen = {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
              for p in mission.get("frozen_files", [])}

    def invoke(role: str, payload: Json) -> Json:
        def unchanged() -> bool:
            return all(Path(p).is_file() and hashlib.sha256(Path(p).read_bytes()).hexdigest() == h
                       for p, h in frozen.items())
        if not unchanged():
            raise ValueError("frozen evaluator/configuration was changed")
        remaining = deadline - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("mission deadline exceeded")
        ledger.emit("worker_started", role=role, actor=mission[role]["id"])
        output = call_worker(mission[role]["argv"], payload, min(timeout, remaining), directory)
        if not unchanged():
            raise ValueError("frozen evaluator/configuration was changed")
        ledger.emit("worker_finished", role=role, actor=mission[role]["id"])
        return output

    try:
        for attempt in range(1, attempts + 1):
            result["attempts"] = attempt
            # No ground truth, reviewer identity, or secrets in builder payload.
            built = invoke("builder", {"brief": mission["brief"], "attempt": attempt,
                                       "input": mission.get("input", {}), "feedback": feedback})
            if "artifact" not in built:
                raise ValueError("builder returned no artifact")
            artifact = built["artifact"]
            ahash = digest(artifact)
            atomic_json(directory / f"artifact-{attempt}.json", artifact)
            result["artifact_hash"] = ahash
            ledger.emit("artifact_created", attempt=attempt, artifact_hash=ahash)
            proof = invoke("verifier", {"artifact": artifact, "artifact_hash": ahash,
                                       "input": mission.get("input", {})})
            count = proof.get("checks")
            valid = (proof.get("artifact_hash") == ahash and proof.get("passed") is True
                     and type(count) is int and count > 0 and proof.get("critical") is False)
            atomic_json(directory / f"proof-{attempt}.json", proof)
            ledger.emit("verified", attempt=attempt, artifact_hash=ahash,
                        passed=valid, checks=count, proof_hash=digest(proof))
            if proof.get("critical") is True:
                result["reason"] = "critical_failure"
                break
            if not valid:
                feedback = {"reason": "independent_verification_failed"}
                ledger.emit("revision_requested", **feedback)
                continue
            review = invoke("reviewer", {"brief": mission["brief"], "artifact": artifact,
                                         "artifact_hash": ahash})
            atomic_json(directory / f"review-{attempt}.json", review)
            approved = review.get("artifact_hash") == ahash and review.get("approved") is True
            ledger.emit("reviewed", approved=approved, artifact_hash=ahash,
                        attempt=attempt, review_hash=digest(review))
            if approved:
                result.update(status="awaiting_human", reason="proof_and_review_passed")
                break
            feedback = {"reason": "review_rejected"}
            ledger.emit("revision_requested", **feedback)
    except (ValueError, TimeoutError, OSError) as exc:
        # Do not copy arbitrary worker output or OS command paths into evidence.
        result["reason"] = type(exc).__name__
        ledger.emit("execution_blocked", error_type=type(exc).__name__)
    result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    ledger.emit("finished", status=result["status"], reason=result["reason"],
                released=False, result_hash=digest(result))
    result["events"] = len(ledger.events)
    result["ledger_head"] = ledger.events[-1]["hash"]
    atomic_json(directory / "result.json", result)
    return result


def verify_run(directory: Path) -> Json:
    result = json.loads((directory / "result.json").read_text())
    ledger = Ledger(directory / "events.jsonl")
    if not ledger.events or result["ledger_head"] != ledger.events[-1]["hash"]:
        raise ValueError("ledger head mismatch")
    core = {k: v for k, v in result.items() if k not in ("events", "ledger_head")}
    if (result.get("events") != len(ledger.events)
            or ledger.events[-1]["data"].get("result_hash") != digest(core)):
        raise ValueError("result changed after checkpoint")
    for event in ledger.events:
        data = event["data"]
        if event["kind"] in ("verified", "reviewed"):
            prefix = "proof" if event["kind"] == "verified" else "review"
            receipt = json.loads((directory / f"{prefix}-{data['attempt']}.json").read_text())
            if digest(receipt) != data[f"{prefix}_hash"]:
                raise ValueError("evaluator receipt changed after checkpoint")
        if event["kind"] == "artifact_created":
            data = event["data"]
            artifact = json.loads((directory / f"artifact-{data['attempt']}.json").read_text())
            if digest(artifact) != data["artifact_hash"]:
                raise ValueError("artifact changed after verification")
    return result


def publish_buzz(directory: Path, relay: str, channel: str, binary: str = "buzz") -> Json:
    """Explicit single-attempt publication; ambiguous delivery is never retried.

    Publication uses ONE publisher identity. Actor names inside the receipt do
    not become independently authenticated Buzz identities. No approval action.
    """
    from urllib.parse import urlsplit
    target = urlsplit(relay)
    if target.scheme != "https" and not (target.scheme == "http" and target.hostname in ("localhost", "127.0.0.1", "::1")):
        raise ValueError("HTTPS is required outside localhost")
    if target.username or target.password or target.query or target.fragment:
        raise ValueError("relay URL must not contain credentials, query or fragment")
    uuid.UUID(channel)
    if not os.environ.get("BUZZ_PRIVATE_KEY"):
        raise ValueError("BUZZ_PRIVATE_KEY not configured")
    receipt_path = directory / "buzz-receipt.json"
    if receipt_path.exists():
        raise ValueError("publication already attempted; reconcile on relay before retrying")
    result = verify_run(directory)
    payload = {k: result[k] for k in ("schema", "run_id", "mission_id", "status", "reason",
                                    "execution_kind", "artifact_hash", "ledger_head", "released")}
    payload["receipt_id"] = digest(payload)
    # Write the intent before the network call. A crash leaves a reconcile-able intent.
    receipt = {"state": "delivery_unknown", "receipt_id": payload["receipt_id"],
               "relay": relay, "channel": channel}
    try:
        with receipt_path.open("x") as stream:
            stream.write(json.dumps(receipt, indent=2) + "\n")
    except FileExistsError:
        raise ValueError("publication already attempted; reconcile on relay before retrying") from None
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "HOME", "BUZZ_PRIVATE_KEY") if k in os.environ}
    env["BUZZ_RELAY_URL"] = relay
    try:
        sent = subprocess.run([binary, "messages", "send", "--channel", channel, "--content", "-"],
                              input=canonical(payload), text=True, capture_output=True,
                              timeout=20, env=env, check=False)
        if sent.returncode == 0:
            json.loads(sent.stdout)  # protocol-level acknowledgement, NOT read-back proof
            receipt["state"] = "cli_acknowledged"
        else:
            receipt["exit_code"] = sent.returncode
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    atomic_json(receipt_path, receipt)
    return receipt


def doctor() -> Json:
    return {"python": sys.version.split()[0], "buzz_cli": bool(shutil.which("buzz")),
            "docker": bool(shutil.which("docker")), "rust": bool(shutil.which("cargo")),
            "buzz_key_configured": bool(os.environ.get("BUZZ_PRIVATE_KEY")),
            "relay_configured": bool(os.environ.get("BUZZ_RELAY_URL")),
            "live_relay_tested": False}


def dashboard(summary: Json, path: Path) -> None:
    """Static evidence report. All data escaped; no fake live-agent controls."""
    rows = "".join(f"<tr><td>{html.escape(r['case'])}</td><td>{html.escape(r['result']['status'])}</td>"
                   f"<td>{r['result']['attempts']}</td><td>{r['result']['elapsed_seconds']:.3f}s</td>"
                   f"<td>{'PASS' if r['contract_passed'] else 'FAIL'}</td></tr>" for r in summary["runs"])
    count = sum(r["contract_passed"] for r in summary["runs"])
    payload = html.escape(json.dumps(summary, indent=2))
    path.write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ASTRA / Evidence room</title>
<style>body{{margin:0;background:#101114;color:#f6f5ef;font:16px system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:56px 24px}}header{{display:flex;justify-content:space-between;gap:20px;font-size:13px;letter-spacing:.12em}}.tag{{border:1px solid #555b65;border-radius:30px;padding:8px 13px;color:#cfd5df}}h1{{font-size:clamp(38px,7vw,76px);font-weight:550;letter-spacing:-.055em;margin:65px 0 18px;line-height:1.05}}p{{color:#b3b8c2;line-height:1.65;max-width:730px}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:34px 0}}article{{background:#1b1d22;padding:25px;border:1px solid #34373e;border-radius:18px}}strong{{font-size:38px;display:block;margin:8px 0}}small{{color:#aeb5c2}}.hold{{background:#292319;border:1px solid #6f5835;padding:22px;border-radius:16px;margin:28px 0;color:#ead2a9}}table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{text-align:left;padding:15px 10px;border-bottom:1px solid #34373e}}th{{color:#aeb5c2}}.scroll{{overflow-x:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:#afb9c9}}details{{margin:24px 0;padding:18px;border:1px solid #34373e;border-radius:14px}}h2{{font-weight:500;margin-top:40px}}footer{{margin-top:40px;color:#9299a8;font-size:13px}}@media(max-width:600px){{.grid{{grid-template-columns:1fr}}main{{padding:28px 18px}}header{{letter-spacing:0}}h1{{margin-top:42px}}}}</style>
<main><header><span>ASTRA / CONTROL ROOM</span><span class="tag">V0.1 · LOCAL EVIDENCE</span></header>
<h1>Prove the work.<br>Then scale the team.</h1><p>A working evaluation circuit, not a claim of autonomous intelligence. These are deterministic fixture workers in real subprocesses. No live models or Buzz relay were used.</p>
<div class="grid"><article><small>Integration contracts</small><strong>{count}/{len(summary['runs'])}</strong><small>Expected outcomes checked</small></article><article><small>Live agent comparisons</small><strong>0</strong><small>Productivity uplift unknown</small></article><article><small>Production releases</small><strong>0</strong><small>No release capability exists</small></article></div>
<div class="hold"><b>HOLD — no superiority claim.</b><br>Passing plumbing tests does not show that multiple agents beat one. Live quality, human effort, cost and business value are not yet measured.</div>
<h2>The first measured circuit</h2><p>Brief → builder → independent verifier → reviewer → human review queue. Failed verification triggers a bounded retry; critical failure stops the run. An agent’s own success claim is not evidence.</p>
<div class="scroll"><table><thead><tr><th>Failure injection / task</th><th>Actual terminal state</th><th>Attempts</th><th>Wall time</th><th>Contract</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>What would earn a live pilot PASS?</h2><p>At least 20 distinct tasks, three repetitions per arm: single agent, coordinated team, and the same team using Buzz. Predefine acceptance tests; count failures and retries. Aim for ≥90% verified completion, no critical failures, ≥30% less human effort, and no increase in all-in cost per accepted task. These are proposed thresholds, not results.</p>
<details><summary>Inspect the evidence JSON</summary><pre>{payload}</pre></details>
<footer>Evidence scope: local controller integration only. Missing costs and human timings stay unknown. No credentials, customer data or agent prompts are included in this report.</footer></main></html>''')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("doctor")
    run = subs.add_parser("run")
    run.add_argument("mission", type=Path)
    run.add_argument("--output", required=True, type=Path)
    verify = subs.add_parser("verify")
    verify.add_argument("directory", type=Path)
    publish = subs.add_parser("publish-buzz")
    publish.add_argument("directory", type=Path)
    publish.add_argument("--relay", required=True)
    publish.add_argument("--channel", required=True)
    demo = subs.add_parser("demo")
    demo.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "doctor":
            result = doctor()
        elif args.action == "run":
            result = run_mission(json.loads(args.mission.read_text()), args.output)
        elif args.action == "verify":
            result = verify_run(args.directory)
        elif args.action == "publish-buzz":
            result = publish_buzz(args.directory, args.relay, args.channel)
        else:
            from agentproof.controlroom_fixtures import run_demo
            result = run_demo(args.output)
        print(json.dumps(result, indent=2, allow_nan=False))
        if result.get("status") == "blocked" or result.get("state") == "delivery_unknown" or result.get("contracts_passed") is False:
            raise SystemExit(1)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
