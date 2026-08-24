from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .compiler import CompiledSystem
from .authorization import AuthorizationService, GateApproval, _resource_hash


RUNTIME_STATES = {
    "CREATED", "CONTEXT_READY", "ROUTED", "RUNNING", "VERIFYING",
    "AWAITING_HUMAN", "REWORK_REQUIRED", "BLOCKED", "COMPLETED",
    "FAILED", "CANCELLED", "INSUFFICIENT_EVIDENCE",
}
ALLOWED_STATE_TRANSITIONS = {
    "CREATED": {"CONTEXT_READY", "FAILED", "CANCELLED"},
    "CONTEXT_READY": {"ROUTED", "FAILED", "CANCELLED"},
    "ROUTED": {"RUNNING", "VERIFYING", "AWAITING_HUMAN", "COMPLETED", "FAILED", "CANCELLED"},
    "RUNNING": {"ROUTED", "VERIFYING", "AWAITING_HUMAN", "REWORK_REQUIRED", "BLOCKED", "FAILED", "INSUFFICIENT_EVIDENCE"},
    "VERIFYING": {"ROUTED", "AWAITING_HUMAN", "FAILED", "INSUFFICIENT_EVIDENCE"},
    "AWAITING_HUMAN": {"ROUTED", "REWORK_REQUIRED", "BLOCKED", "CANCELLED"},
    "REWORK_REQUIRED": {"ROUTED", "BLOCKED", "CANCELLED"},
    "BLOCKED": {"ROUTED", "FAILED", "CANCELLED"},
    "INSUFFICIENT_EVIDENCE": {"ROUTED", "BLOCKED", "CANCELLED"},
    "FAILED": set(), "CANCELLED": set(), "COMPLETED": set(),
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(content: Any) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def gate_approval_from_persisted_decision(**_: Any) -> GateApproval:
    """Deprecated: approvals can only be resolved from SQLite runtime state."""
    raise PermissionError("callers cannot manufacture trusted gate approvals")


class RoleExecutor(Protocol):
    def attempt_descriptor(self, role_id: str, tier: str) -> dict[str, str] | None: ...
    def execute(self, *, role_id: str, task_id: str, tier: str, inputs: dict[str, Any], produces: list[str], attempt: int, actions: list[dict[str, Any]], task_context: dict[str, Any], gate_approvals: list[GateApproval]) -> dict[str, Any]: ...


class MockRoleExecutor:
    """Deterministic, provider-neutral executor with no external capabilities."""

    def __init__(self, outcomes: dict[str, list[str]] | None = None, authorization: AuthorizationService | None = None):
        self.outcomes = {key: list(value) for key, value in (outcomes or {}).items()}
        self.calls: list[tuple[str, int]] = []
        self.authorization = authorization

    def execute(self, *, role_id: str, task_id: str, tier: str, inputs: dict[str, Any], produces: list[str], attempt: int, actions: list[dict[str, Any]], task_context: dict[str, Any], gate_approvals: list[GateApproval]) -> dict[str, Any]:
        if self.authorization is None:
            raise RuntimeError("mock executor requires an authorization service")
        for action in actions:
            context = dict(task_context)
            for key in ("command_category", "external_system_category"):
                if key in action:
                    context[key] = action[key]
            decision = self.authorization.decide(role_id=role_id, capability=action["capability"], resource=action["resource"], task_context=context, gate_approvals=gate_approvals)
            if decision.decision != "ALLOW":
                raise PermissionError(f"authorization {decision.decision}: {decision.reason_code}")
        self.calls.append((task_id, attempt))
        outcome = self.outcomes.get(task_id, ["success"]).pop(0) if self.outcomes.get(task_id) else "success"
        if outcome == "escalate":
            return {"outcome": "escalate", "reason_code": "confidence_low", "artifacts": {}}
        artifacts = {
            artifact_type: {"mock": True, "task_id": task_id, "role_id": role_id, "tier": tier, "attempt": attempt, "outcome": outcome}
            for artifact_type in produces
        }
        return {"outcome": outcome, "reason_code": "mock_configured", "artifacts": artifacts}

    def attempt_descriptor(self, role_id: str, tier: str) -> None:
        return None


class SQLiteEventStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL, current_node TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, event_type TEXT NOT NULL, node_id TEXT, task_id TEXT, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, artifact_type TEXT NOT NULL, producer_node TEXT NOT NULL, content_json TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS task_attempts(run_id TEXT NOT NULL, node_id TEXT NOT NULL, attempt INTEGER NOT NULL, role_id TEXT NOT NULL, tier TEXT NOT NULL, status TEXT NOT NULL, outcome TEXT, started_at TEXT NOT NULL, finished_at TEXT, PRIMARY KEY(run_id,node_id,attempt));
        CREATE TABLE IF NOT EXISTS routing_events(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, workflow_id TEXT NOT NULL, task_id TEXT NOT NULL, role_id TEXT NOT NULL, requested_tier TEXT NOT NULL, selected_tier TEXT NOT NULL, reason_code TEXT NOT NULL, transition TEXT NOT NULL, attempt INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS gates(gate_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, node_id TEXT NOT NULL, gate_type TEXT NOT NULL, status TEXT NOT NULL, evidence_json TEXT NOT NULL, requested_at TEXT NOT NULL, decided_at TEXT, decided_by TEXT, reason TEXT, policy_version TEXT, approved_resource_hashes_json TEXT, capability TEXT);
        CREATE TABLE IF NOT EXISTS provider_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, correlation_id TEXT UNIQUE, run_id TEXT NOT NULL, node_id TEXT NOT NULL, attempt INTEGER NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'IN_PROGRESS', input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER, latency_ms INTEGER, estimated_cost REAL, response_id TEXT, raw_output TEXT, validation_errors_json TEXT NOT NULL DEFAULT '[]', semantic_validation_status TEXT, semantic_rule_ids_json TEXT NOT NULL DEFAULT '[]', semantic_validation_json TEXT, repair_attempted INTEGER NOT NULL DEFAULT 0, repair_succeeded INTEGER NOT NULL DEFAULT 0, source_hashes_json TEXT NOT NULL DEFAULT '{}', safe_error_json TEXT, created_at TEXT NOT NULL, finished_at TEXT);
        CREATE TABLE IF NOT EXISTS findings(finding_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
        gate_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(gates)")}
        if "policy_version" not in gate_columns:
            self.connection.execute("ALTER TABLE gates ADD COLUMN policy_version TEXT")
        if "approved_resource_hashes_json" not in gate_columns:
            self.connection.execute("ALTER TABLE gates ADD COLUMN approved_resource_hashes_json TEXT")
        if "capability" not in gate_columns:
            self.connection.execute("ALTER TABLE gates ADD COLUMN capability TEXT")
        provider_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(provider_attempts)")}
        for name, declaration in {
            "semantic_validation_status": "TEXT",
            "semantic_rule_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "semantic_validation_json": "TEXT",
            "repair_attempted": "INTEGER NOT NULL DEFAULT 0",
            "repair_succeeded": "INTEGER NOT NULL DEFAULT 0",
            "correlation_id": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'SUCCEEDED'",
            "safe_error_json": "TEXT",
            "finished_at": "TEXT",
        }.items():
            if name not in provider_columns:
                self.connection.execute(f"ALTER TABLE provider_attempts ADD COLUMN {name} {declaration}")
        self.connection.commit()

    def event(self, run_id: str, event_type: str, node_id: str | None = None, task_id: str | None = None, **payload: Any) -> None:
        self.connection.execute("INSERT INTO events(run_id,event_type,node_id,task_id,payload_json,created_at) VALUES(?,?,?,?,?,?)", (run_id,event_type,node_id,task_id,json.dumps(payload,sort_keys=True),utcnow()))

    def events(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(row) | {"payload": json.loads(row["payload_json"])} for row in self.connection.execute("SELECT * FROM events WHERE run_id=? ORDER BY event_id", (run_id,))]

    def run(self, run_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row: raise KeyError(run_id)
        return dict(row)

    def close(self) -> None:
        self.connection.close()


class OrchestrationEngine:
    def __init__(self, compiled: CompiledSystem, store: SQLiteEventStore, executor: RoleExecutor):
        self.compiled, self.store, self.executor = compiled, store, executor
        self.workflow = compiled.workflows["automate"]
        self.nodes = {node["id"]: node for node in self.workflow["nodes"]}
        self.authorization = AuthorizationService(compiled.registry, compiled.capabilities, approval_resolver=self._resolve_gate_approvals)
        if hasattr(executor, "authorization"):
            executor.authorization = self.authorization

    def _active_evidence_matches(self, run_id: str, evidence: dict[str, Any]) -> bool:
        for artifact_type, expected in evidence.items():
            row = self.store.connection.execute(
                "SELECT artifact_id,content_hash FROM artifacts WHERE run_id=? AND artifact_type=? AND active=1",
                (run_id, artifact_type),
            ).fetchone()
            if not row or row["artifact_id"] != expected.get("artifact_id") or row["content_hash"] != expected.get("content_hash"):
                return False
        return True

    def _resolve_gate_approvals(self, *, workflow_run_id: str, gate_type: str, capability: str, resource: str) -> list[GateApproval]:
        approvals: list[GateApproval] = []
        rows = self.store.connection.execute(
            "SELECT * FROM gates WHERE run_id=? AND gate_type=? AND capability=? AND status='approved'",
            (workflow_run_id, gate_type, capability),
        ).fetchall()
        for row in rows:
            evidence = json.loads(row["evidence_json"])
            resource_hashes = tuple(json.loads(row["approved_resource_hashes_json"] or "[]"))
            if not row["gate_id"] or not row["decided_by"] or not row["decided_at"] or not evidence or _resource_hash(resource) not in resource_hashes or not self._active_evidence_matches(workflow_run_id, evidence):
                continue
            approvals.append(GateApproval(
                workflow_run_id, row["gate_id"], row["gate_type"], capability,
                resource_hashes, tuple(item["content_hash"] for item in evidence.values()),
                row["decided_by"], row["decided_at"], row["policy_version"],
                status=row["status"], stale=False,
            ))
        return approvals

    def _persist_authorization(self, run_id: str, node_id: str, decision: Any) -> None:
        self.store.event(run_id, "authorization_decision", node_id, node_id, **decision.as_dict())
        self.store.connection.commit()

    def _authorize(self, run_id: str, node: dict[str, Any], capability: str, resource: str, context: dict[str, Any]) -> None:
        declared = any(action["capability"] == capability and action["resource"] == resource for action in node.get("actions", []))
        if not declared:
            decision = self.authorization._emit(node["role_id"], capability, resource, "DENY", "WORKFLOW_ACTION_UNDECLARED")
        else:
            decision = self.authorization.decide(
                role_id=node["role_id"], capability=capability, resource=resource,
                task_context=context,
            )
        self._persist_authorization(run_id, node["id"], decision)
        if decision.decision != "ALLOW":
            self.store.connection.execute("UPDATE task_attempts SET status=?,outcome=?,finished_at=? WHERE run_id=? AND node_id=? AND status='RUNNING'",("BLOCKED" if decision.decision == "REQUIRE_GATE" else "DENIED",decision.reason_code,utcnow(),run_id,node["id"]))
            self._set_state(run_id, "BLOCKED" if decision.decision == "REQUIRE_GATE" else "FAILED")
            self.store.event(run_id, "task_authorization_failed", node["id"], node["id"], decision=decision.decision, reason_code=decision.reason_code)
            self.store.connection.commit()
            raise PermissionError(f"authorization {decision.decision}: {decision.reason_code}")

    def _set_state(self, run_id: str, state: str) -> None:
        run = self.store.run(run_id)
        if state != run["state"] and state not in ALLOWED_STATE_TRANSITIONS[run["state"]]:
            raise ValueError(f"invalid state transition {run['state']} -> {state}")
        self.store.connection.execute("UPDATE runs SET state=?,updated_at=? WHERE run_id=?", (state,utcnow(),run_id))
        self.store.event(run_id,"state_changed",self.store.run(run_id)["current_node"],from_state=run["state"],to_state=state)

    def _move(self, run_id: str, node_id: str, event: str) -> None:
        matches = [t for t in self.workflow["transitions"] if t["from"] == node_id and t["on"] == event]
        if len(matches) != 1: raise ValueError(f"no unique transition from {node_id} on {event}")
        target = matches[0]["to"]
        self.store.connection.execute("UPDATE runs SET current_node=?,updated_at=? WHERE run_id=?", (target,utcnow(),run_id))
        self.store.event(run_id,"workflow_transition",node_id,outcome=event,to_node=target)

    def _artifact(self, run_id: str, artifact_type: str, producer: str, content: Any) -> str:
        if artifact_type not in self.compiled.artifact_types: raise ValueError(f"unknown artifact type {artifact_type}")
        digest, artifact_id = content_hash(content), str(uuid.uuid4())
        prior = self.store.connection.execute("SELECT artifact_id,content_hash FROM artifacts WHERE run_id=? AND artifact_type=? AND active=1",(run_id,artifact_type)).fetchone()
        self.store.connection.execute("UPDATE artifacts SET active=0 WHERE run_id=? AND artifact_type=?",(run_id,artifact_type))
        self.store.connection.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,1)",(artifact_id,run_id,artifact_type,producer,json.dumps(content,sort_keys=True),digest,utcnow()))
        self.store.event(run_id,"artifact_recorded",producer,artifact_id=artifact_id,artifact_type=artifact_type,content_hash=digest)
        if prior and prior["content_hash"] != digest:
            gates = self.store.connection.execute("SELECT * FROM gates WHERE run_id=? AND status IN ('approved','pending')",(run_id,)).fetchall()
            for gate in gates:
                evidence=json.loads(gate["evidence_json"])
                if evidence.get(artifact_type, {}).get("content_hash") == prior["content_hash"]:
                    self.store.connection.execute("UPDATE gates SET status='stale' WHERE gate_id=?",(gate["gate_id"],))
                    self.store.event(run_id,"gate_invalidated",gate["node_id"],gate_id=gate["gate_id"],artifact_type=artifact_type)
        return artifact_id

    def replace_artifact(self, run_id: str, artifact_type: str, content: Any) -> str:
        result=self._artifact(run_id,artifact_type,"external_input",content)
        stale=self.store.connection.execute("SELECT * FROM gates WHERE run_id=? AND status='stale' ORDER BY requested_at DESC LIMIT 1",(run_id,)).fetchone()
        if stale:
            self.store.connection.execute("UPDATE gates SET status='stale' WHERE run_id=? AND status='pending' AND node_id<>?",(run_id,stale["node_id"]))
            self.store.connection.execute("UPDATE runs SET current_node=?,state='AWAITING_HUMAN',updated_at=? WHERE run_id=?",(stale["node_id"],utcnow(),run_id))
            self.store.event(run_id,"gate_reapproval_required",stale["node_id"],gate_id=stale["gate_id"])
        self.store.connection.commit(); return result

    def start(self, work_item: Any) -> str:
        run_id=str(uuid.uuid4()); now=utcnow()
        self.store.connection.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",(run_id,"automate",self.compiled.snapshot_hash,self.workflow["initial_node"],"CREATED",now,now))
        self.store.event(run_id,"run_created",self.workflow["initial_node"],snapshot_hash=self.compiled.snapshot_hash)
        self._artifact(run_id,"work_item","input",work_item); self._set_state(run_id,"CONTEXT_READY"); self.store.connection.commit()
        self.resume(run_id); return run_id

    def _inputs(self, run_id: str, node: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        result={}
        for artifact_type in node["requires"]:
            self._authorize(run_id, node, "artifacts.read", artifact_type, context)
            row=self.store.connection.execute("SELECT * FROM artifacts WHERE run_id=? AND artifact_type=? AND active=1 ORDER BY created_at DESC LIMIT 1",(run_id,artifact_type)).fetchone()
            if not row: raise ValueError(f"missing required artifact {artifact_type}")
            result[artifact_type]=json.loads(row["content_json"])
        return result

    def _accept_artifacts(self, run_id: str, node: dict[str, Any], artifacts: dict[str, Any], context: dict[str, Any]) -> None:
        undeclared = set(artifacts) - set(node["produces"])
        if undeclared:
            raise ValueError(f"provider returned undeclared artifacts: {sorted(undeclared)}")
        for artifact_type, content in artifacts.items():
            self._authorize(run_id, node, "artifacts.write", artifact_type, context)
            self._artifact(run_id, artifact_type, node["id"], content)

    def _route(self, run_id: str, node: dict[str, Any], attempt: int, requested: str | None = None, reason: str="role_default") -> str:
        role=self.compiled.registry["agents"][node["role_id"]]; default=role["default_tier"]; selected=requested or default
        transition="none" if selected==default else ("escalate" if self.compiled.registry["enums"]["tiers"].index(selected)>self.compiled.registry["enums"]["tiers"].index(default) else "deescalate")
        self.store.connection.execute("INSERT INTO routing_events(run_id,workflow_id,task_id,role_id,requested_tier,selected_tier,reason_code,transition,attempt,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(run_id,"automate",node["id"],node["role_id"],default,selected,reason,transition,attempt,utcnow()))
        self.store.event(run_id,"routing_decision",node["id"],node["id"],role_id=node["role_id"],requested_tier=default,selected_tier=selected,reason_code=reason,transition=transition,attempt=attempt)
        return selected

    def _execute_task(self, run_id: str, node: dict[str, Any]) -> None:
        unresolved = self.store.connection.execute(
            "SELECT correlation_id FROM provider_attempts WHERE run_id=? AND node_id=? AND status='IN_PROGRESS' ORDER BY id DESC LIMIT 1",
            (run_id, node["id"]),
        ).fetchone()
        if unresolved:
            self._set_state(run_id, "BLOCKED")
            self.store.event(run_id, "provider_attempt_recovery_required", node["id"], node["id"], correlation_id=unresolved["correlation_id"])
            self.store.connection.commit()
            return
        attempt=self.store.connection.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM task_attempts WHERE run_id=? AND node_id=?",(run_id,node["id"])).fetchone()[0]
        tier=self._route(run_id,node,attempt); self._set_state(run_id,"VERIFYING" if node["id"] in {"design_critique","verify"} else "RUNNING")
        repair_used = False
        repair_context = None
        escalation_count = 0
        while True:
            started=utcnow(); self.store.connection.execute("INSERT INTO task_attempts VALUES(?,?,?,?,?,?,?,?,?)",(run_id,node["id"],attempt,node["role_id"],tier,"RUNNING",None,started,None))
            context={"workflow_run_id": run_id, "workflow_context": {"workflow_id": "automate", "workflow_run_id": run_id, "node_id": node["id"]}}
            if repair_context: context["repair_context"] = repair_context
            inputs = self._inputs(run_id, node, context)
            audit_start=len(self.authorization.audit_log)
            descriptor = self.executor.attempt_descriptor(node["role_id"], tier)
            correlation_id = str(uuid.uuid4()) if descriptor else None
            if descriptor:
                self.store.connection.execute(
                    "INSERT INTO provider_attempts(correlation_id,run_id,node_id,attempt,provider,model,status,latency_ms,validation_errors_json,source_hashes_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (correlation_id,run_id,node["id"],attempt,descriptor["provider"],descriptor["model"],"IN_PROGRESS",0,"[]","{}",utcnow()),
                )
                self.store.event(run_id,"provider_attempt_started",node["id"],node["id"],attempt=attempt,correlation_id=correlation_id,provider=descriptor["provider"],model=descriptor["model"])
                self.store.connection.commit()
            executable_actions = [action for action in node.get("actions", []) if not action["capability"].startswith("artifacts.")]
            try:
                result=self.executor.execute(role_id=node["role_id"],task_id=node["id"],tier=tier,inputs=inputs,produces=node["produces"],attempt=attempt,actions=executable_actions,task_context=context,gate_approvals=[])
            except Exception as exc:
                for decision in self.authorization.audit_log[audit_start:]:
                    self.store.event(run_id,"authorization_decision",node["id"],node["id"],**decision.as_dict())
                safe_error = {"exception_type": exc.__class__.__name__, "message": getattr(exc, "safe_message", "provider or executor request failed")}
                if descriptor:
                    self.store.connection.execute("UPDATE provider_attempts SET status='FAILED',safe_error_json=?,finished_at=? WHERE correlation_id=?",(json.dumps(safe_error,sort_keys=True),utcnow(),correlation_id))
                    self.store.event(run_id,"provider_attempt_failed",node["id"],node["id"],attempt=attempt,correlation_id=correlation_id,error=safe_error)
                self.store.connection.execute("UPDATE task_attempts SET status='FAILED',outcome='execution_error',finished_at=? WHERE run_id=? AND node_id=? AND attempt=?",(utcnow(),run_id,node["id"],attempt))
                self._set_state(run_id,"BLOCKED" if isinstance(exc, PermissionError) and "REQUIRE_GATE" in str(exc) else "FAILED")
                self.store.connection.commit()
                raise
            for decision in self.authorization.audit_log[audit_start:]:
                self.store.event(run_id,"authorization_decision",node["id"],node["id"],**decision.as_dict())
            outcome=result["outcome"]
            if "telemetry" in result:
                telemetry=result["telemetry"]
                semantic=result.get("semantic_validation") or {}
                self.store.connection.execute("UPDATE provider_attempts SET status='SUCCEEDED',input_tokens=?,output_tokens=?,cached_tokens=?,latency_ms=?,estimated_cost=?,response_id=?,raw_output=?,validation_errors_json=?,semantic_validation_status=?,semantic_rule_ids_json=?,semantic_validation_json=?,source_hashes_json=?,finished_at=? WHERE correlation_id=?",(telemetry.get("input_tokens"),telemetry.get("output_tokens"),telemetry.get("cached_tokens"),telemetry["latency_ms"],telemetry.get("estimated_cost"),result.get("provider_response_id"),result.get("raw_output"),json.dumps(result.get("validation_errors",[])),semantic.get("status"),json.dumps(semantic.get("rule_ids",[])),json.dumps(semantic,sort_keys=True) if semantic else None,json.dumps(result.get("source_hashes",{}),sort_keys=True),utcnow(),correlation_id))
                self.store.event(run_id,"provider_attempt_recorded",node["id"],node["id"],attempt=attempt,provider=telemetry["provider"],model=telemetry["model"],latency_ms=telemetry["latency_ms"],input_tokens=telemetry.get("input_tokens"),output_tokens=telemetry.get("output_tokens"),cached_tokens=telemetry.get("cached_tokens"),validation_errors=result.get("validation_errors",[]),semantic_validation=semantic or None,semantic_validation_status=semantic.get("status"),semantic_rule_ids=semantic.get("rule_ids",[]),repair_attempted=repair_context is not None,source_hashes=result.get("source_hashes",{}))
            invalid_reason=result.get("reason_code") in {"malformed_json","schema_validation_failed","provider_no_output","semantic_validation_failed"}
            if outcome=="failure" and invalid_reason:
                self.store.connection.execute("UPDATE task_attempts SET status='INVALID_OUTPUT',outcome=?,finished_at=? WHERE run_id=? AND node_id=? AND attempt=?",(result["reason_code"],utcnow(),run_id,node["id"],attempt))
                semantic=result.get("semantic_validation") or {}
                repairable=result["reason_code"] != "semantic_validation_failed" or semantic.get("repairable") is True
                if not repair_used and repairable:
                    repair_used=True
                    repair_context={"original_output": result.get("raw_output"), "validation_errors": result.get("validation_errors", []), "semantic_validation": semantic, "original_output_hash": content_hash(result.get("raw_output"))}
                    self.store.connection.execute("UPDATE provider_attempts SET repair_attempted=1 WHERE run_id=? AND node_id=? AND attempt=?",(run_id,node["id"],attempt))
                    attempt+=1
                    self.store.event(run_id,"provider_repair_requested",node["id"],node["id"],attempt=attempt,original_output_hash=repair_context["original_output_hash"],reason_code=result["reason_code"],semantic_rule_ids=semantic.get("rule_ids",[]))
                    continue
                if repair_used and "telemetry" in result:
                    self.store.event(run_id,"provider_repair_completed",node["id"],node["id"],attempt=attempt,succeeded=False,semantic_validation_status=semantic.get("status"),semantic_rule_ids=semantic.get("rule_ids",[]))
                self._set_state(run_id,"FAILED")
                self.store.event(run_id,"task_failed",node["id"],node["id"],reason_code=result["reason_code"])
                return
            if repair_used and "telemetry" in result:
                self.store.connection.execute("UPDATE provider_attempts SET repair_succeeded=1 WHERE run_id=? AND node_id=? AND attempt=?",(run_id,node["id"],attempt))
                self.store.event(run_id,"provider_repair_completed",node["id"],node["id"],attempt=attempt,succeeded=True,semantic_validation_status=(result.get("semantic_validation") or {}).get("status"))
            if outcome=="escalate":
                self.store.connection.execute("UPDATE task_attempts SET status='ESCALATED',outcome=?,finished_at=? WHERE run_id=? AND node_id=? AND attempt=?",(outcome,utcnow(),run_id,node["id"],attempt))
                target=self.compiled.registry["agents"][node["role_id"]].get("escalation_tier")
                tiers=list(self.compiled.registry["enums"]["tiers"])
                if not target or tiers.index(target) <= tiers.index(tier) or escalation_count >= 1:
                    self.store.connection.execute("UPDATE task_attempts SET status='INSUFFICIENT_EVIDENCE',outcome='impossible_escalation',finished_at=? WHERE run_id=? AND node_id=? AND attempt=?",(utcnow(),run_id,node["id"],attempt))
                    self._set_state(run_id,"INSUFFICIENT_EVIDENCE")
                    self.store.event(run_id,"escalation_unavailable",node["id"],node["id"],attempt=attempt,current_tier=tier,requested_tier=target,reason_code="NO_HIGHER_TIER")
                    return
                escalation_count += 1
                attempt+=1; tier=self._route(run_id,node,attempt,target,result["reason_code"]); continue
            if outcome == "failure":
                self.store.connection.execute("UPDATE task_attempts SET status='FAILED',outcome=?,finished_at=? WHERE run_id=? AND node_id=? AND attempt=?",(result.get("reason_code","failure"),utcnow(),run_id,node["id"],attempt))
                self._set_state(run_id,"FAILED")
                self.store.event(run_id,"task_failed",node["id"],node["id"],reason_code=result.get("reason_code","provider_failure"))
                return
            self._accept_artifacts(run_id, node, result["artifacts"], context)
            self.store.connection.execute("UPDATE task_attempts SET status='COMPLETED',outcome=?,finished_at=? WHERE run_id=? AND node_id=? AND attempt=?",(outcome,utcnow(),run_id,node["id"],attempt))
            self.store.event(run_id,"task_completed",node["id"],node["id"],attempt=attempt,tier=tier,outcome=outcome,duration_ms=0)
            self._move(run_id,node["id"],outcome); self._set_state(run_id,"ROUTED"); return

    def _enter_gate(self, run_id: str, node: dict[str, Any]) -> None:
        existing=self.store.connection.execute("SELECT * FROM gates WHERE run_id=? AND node_id=? AND status='pending'",(run_id,node["id"])).fetchone()
        if not existing:
            evidence={}
            for artifact_type in node["requires"]:
                row=self.store.connection.execute("SELECT artifact_id,content_hash FROM artifacts WHERE run_id=? AND artifact_type=? AND active=1",(run_id,artifact_type)).fetchone()
                if not row: raise ValueError(f"gate missing evidence {artifact_type}")
                evidence[artifact_type]={"artifact_id":row["artifact_id"],"content_hash":row["content_hash"]}
            gate_id=str(uuid.uuid4())
            self.store.connection.execute("INSERT INTO gates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(gate_id,run_id,node["id"],node["gate_type"],"pending",json.dumps(evidence,sort_keys=True),utcnow(),None,None,None,self.authorization.policy_version,json.dumps([]),None))
            self.store.event(run_id,"gate_requested",node["id"],gate_id=gate_id,gate_type=node["gate_type"],evidence=evidence)
        self._set_state(run_id,"AWAITING_HUMAN")

    def decide_gate(self, run_id: str, decision: str, decided_by: str, reason: str) -> None:
        if decision not in {"approved","rejected"}: raise ValueError(decision)
        run=self.store.run(run_id); node=self.nodes[run["current_node"]]
        if node["type"]!="gate" or run["state"]!="AWAITING_HUMAN": raise ValueError("run is not awaiting a gate decision")
        gate=self.store.connection.execute("SELECT * FROM gates WHERE run_id=? AND node_id=? AND status='pending' ORDER BY requested_at DESC LIMIT 1",(run_id,node["id"])).fetchone()
        if not gate: raise ValueError("no pending gate")
        evidence=json.loads(gate["evidence_json"])
        if not self._active_evidence_matches(run_id, evidence):
            self.store.connection.execute("UPDATE gates SET status='stale' WHERE gate_id=?",(gate["gate_id"],))
            self.store.event(run_id,"gate_invalidated",node["id"],gate_id=gate["gate_id"],reason_code="EVIDENCE_CHANGED_BEFORE_DECISION")
            self.store.connection.commit()
            raise ValueError("pending gate evidence is stale; resume to request a new gate")
        self.store.connection.execute("UPDATE gates SET status=?,decided_at=?,decided_by=?,reason=?,policy_version=? WHERE gate_id=?",(decision,utcnow(),decided_by,reason,self.authorization.policy_version,gate["gate_id"]))
        self._artifact(run_id,"human_gate_evidence",node["id"],{"gate_id":gate["gate_id"],"decision":decision,"evidence":evidence,"decided_by":decided_by,"reason":reason})
        self.store.event(run_id,"gate_decided",node["id"],gate_id=gate["gate_id"],decision=decision,reason=reason,decided_by=decided_by)
        self._move(run_id,node["id"],decision)
        self._set_state(run_id,"REWORK_REQUIRED" if decision=="rejected" else "ROUTED"); self.store.connection.commit()

    def abandon_provider_attempt(self, run_id: str, correlation_id: str, decided_by: str, reason: str) -> None:
        if not decided_by.strip() or not reason.strip():
            raise ValueError("provider-attempt recovery requires an actor and reason")
        row = self.store.connection.execute("SELECT * FROM provider_attempts WHERE run_id=? AND correlation_id=? AND status='IN_PROGRESS'",(run_id,correlation_id)).fetchone()
        if not row or self.store.run(run_id)["state"] != "BLOCKED":
            raise ValueError("run has no matching blocked provider attempt")
        self.store.connection.execute("UPDATE provider_attempts SET status='ABANDONED',safe_error_json=?,finished_at=? WHERE correlation_id=?",(json.dumps({"reason_code":"UNRESOLVED_ATTEMPT_ABANDONED","decided_by":decided_by,"reason":reason},sort_keys=True),utcnow(),correlation_id))
        self.store.event(run_id,"provider_attempt_abandoned",row["node_id"],row["node_id"],correlation_id=correlation_id,decided_by=decided_by,reason=reason)
        self._set_state(run_id,"FAILED"); self.store.connection.commit()

    def resume(self, run_id: str) -> dict[str, Any]:
        while True:
            run=self.store.run(run_id)
            if run["snapshot_hash"]!=self.compiled.snapshot_hash: raise ValueError("compiled snapshot does not match persisted run")
            if run["state"] in {"COMPLETED","FAILED","CANCELLED"}: return run
            node=self.nodes[run["current_node"]]
            if node["type"]=="gate": self._enter_gate(run_id,node); self.store.connection.commit(); return self.store.run(run_id)
            if node["type"]=="state":
                self._set_state(run_id,node["state"]); self._move(run_id,node["id"],"rework"); self._set_state(run_id,"ROUTED"); self.store.connection.commit(); continue
            if node["type"]=="terminal":
                for gate_type in self.workflow["required_gates"]:
                    gate=self.store.connection.execute("SELECT status FROM gates WHERE run_id=? AND gate_type=? ORDER BY requested_at DESC LIMIT 1",(run_id,gate_type)).fetchone()
                    if not gate or gate["status"]!="approved": raise ValueError(f"required gate is not approved: {gate_type}")
                self._set_state(run_id,node["state"]); self.store.event(run_id,"run_completed",node["id"]); self.store.connection.commit(); return self.store.run(run_id)
            if run["state"] in {"CONTEXT_READY","REWORK_REQUIRED","BLOCKED","INSUFFICIENT_EVIDENCE"}: self._set_state(run_id,"ROUTED")
            self._execute_task(run_id,node); self.store.connection.commit()
            if self.store.run(run_id)["state"] in {"BLOCKED","INSUFFICIENT_EVIDENCE"}:
                return self.store.run(run_id)

    def inspect(self, run_id: str, *, include_sensitive_evidence: bool = False) -> dict[str, Any]:
        run=self.store.run(run_id)
        provider_columns = "*" if include_sensitive_evidence else "id,correlation_id,run_id,node_id,attempt,provider,model,status,input_tokens,output_tokens,cached_tokens,latency_ms,estimated_cost,response_id,validation_errors_json,semantic_validation_status,semantic_rule_ids_json,semantic_validation_json,repair_attempted,repair_succeeded,source_hashes_json,safe_error_json,created_at,finished_at"
        return {"run":run,"events":self.store.events(run_id),"artifacts":[dict(r) for r in self.store.connection.execute("SELECT artifact_id,artifact_type,producer_node,content_hash,active,created_at FROM artifacts WHERE run_id=? ORDER BY created_at",(run_id,))],"gates":[dict(r) for r in self.store.connection.execute("SELECT * FROM gates WHERE run_id=? ORDER BY requested_at",(run_id,))],"routing":[dict(r) for r in self.store.connection.execute("SELECT * FROM routing_events WHERE run_id=? ORDER BY id",(run_id,))],"provider_attempts":[dict(r) for r in self.store.connection.execute(f"SELECT {provider_columns} FROM provider_attempts WHERE run_id=? ORDER BY id",(run_id,))]}
