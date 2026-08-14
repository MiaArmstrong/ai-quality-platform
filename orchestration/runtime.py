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


RUNTIME_STATES = {
    "CREATED", "CONTEXT_READY", "ROUTED", "RUNNING", "VERIFYING",
    "AWAITING_HUMAN", "REWORK_REQUIRED", "BLOCKED", "COMPLETED",
    "FAILED", "CANCELLED", "INSUFFICIENT_EVIDENCE",
}
ALLOWED_STATE_TRANSITIONS = {
    "CREATED": {"CONTEXT_READY", "FAILED", "CANCELLED"},
    "CONTEXT_READY": {"ROUTED", "FAILED", "CANCELLED"},
    "ROUTED": {"RUNNING", "VERIFYING", "AWAITING_HUMAN", "COMPLETED", "FAILED", "CANCELLED"},
    "RUNNING": {"ROUTED", "VERIFYING", "AWAITING_HUMAN", "REWORK_REQUIRED", "FAILED", "INSUFFICIENT_EVIDENCE"},
    "VERIFYING": {"ROUTED", "AWAITING_HUMAN", "FAILED", "INSUFFICIENT_EVIDENCE"},
    "AWAITING_HUMAN": {"ROUTED", "REWORK_REQUIRED", "BLOCKED", "CANCELLED"},
    "REWORK_REQUIRED": {"ROUTED", "BLOCKED", "CANCELLED"},
    "BLOCKED": {"ROUTED", "CANCELLED"},
    "INSUFFICIENT_EVIDENCE": {"ROUTED", "BLOCKED", "CANCELLED"},
    "FAILED": set(), "CANCELLED": set(), "COMPLETED": set(),
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(content: Any) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RoleExecutor(Protocol):
    def execute(self, *, role_id: str, task_id: str, tier: str, inputs: dict[str, Any], produces: list[str], attempt: int, authorization_policy: dict[str, Any]) -> dict[str, Any]: ...


class MockRoleExecutor:
    """Deterministic, provider-neutral executor with no external capabilities."""

    def __init__(self, outcomes: dict[str, list[str]] | None = None):
        self.outcomes = {key: list(value) for key, value in (outcomes or {}).items()}
        self.calls: list[tuple[str, int]] = []

    def execute(self, *, role_id: str, task_id: str, tier: str, inputs: dict[str, Any], produces: list[str], attempt: int, authorization_policy: dict[str, Any]) -> dict[str, Any]:
        denied = set(authorization_policy.get("denied_capabilities", []))
        if not {"network", "external_write", "destructive_action"}.issubset(denied):
            raise PermissionError("mock executor requires outward-action capabilities to be denied")
        self.calls.append((task_id, attempt))
        outcome = self.outcomes.get(task_id, ["success"]).pop(0) if self.outcomes.get(task_id) else "success"
        if outcome == "escalate":
            return {"outcome": "escalate", "reason_code": "confidence_low", "artifacts": {}}
        artifacts = {
            artifact_type: {"mock": True, "task_id": task_id, "role_id": role_id, "tier": tier, "attempt": attempt, "outcome": outcome}
            for artifact_type in produces
        }
        return {"outcome": outcome, "reason_code": "mock_configured", "artifacts": artifacts}


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
        CREATE TABLE IF NOT EXISTS gates(gate_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, node_id TEXT NOT NULL, gate_type TEXT NOT NULL, status TEXT NOT NULL, evidence_json TEXT NOT NULL, requested_at TEXT NOT NULL, decided_at TEXT, decided_by TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS findings(finding_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
        """)
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
            gates = self.store.connection.execute("SELECT * FROM gates WHERE run_id=? AND status='approved'",(run_id,)).fetchall()
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

    def _inputs(self, run_id: str, required: list[str]) -> dict[str, Any]:
        result={}
        for artifact_type in required:
            row=self.store.connection.execute("SELECT * FROM artifacts WHERE run_id=? AND artifact_type=? AND active=1 ORDER BY created_at DESC LIMIT 1",(run_id,artifact_type)).fetchone()
            if not row: raise ValueError(f"missing required artifact {artifact_type}")
            result[artifact_type]=json.loads(row["content_json"])
        return result

    def _route(self, run_id: str, node: dict[str, Any], attempt: int, requested: str | None = None, reason: str="role_default") -> str:
        role=self.compiled.registry["agents"][node["role_id"]]; default=role["default_tier"]; selected=requested or default
        transition="none" if selected==default else ("escalate" if self.compiled.registry["enums"]["tiers"].index(selected)>self.compiled.registry["enums"]["tiers"].index(default) else "deescalate")
        self.store.connection.execute("INSERT INTO routing_events(run_id,workflow_id,task_id,role_id,requested_tier,selected_tier,reason_code,transition,attempt,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(run_id,"automate",node["id"],node["role_id"],default,selected,reason,transition,attempt,utcnow()))
        self.store.event(run_id,"routing_decision",node["id"],node["id"],role_id=node["role_id"],requested_tier=default,selected_tier=selected,reason_code=reason,transition=transition,attempt=attempt)
        return selected

    def _execute_task(self, run_id: str, node: dict[str, Any]) -> None:
        attempt=self.store.connection.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM task_attempts WHERE run_id=? AND node_id=?",(run_id,node["id"])).fetchone()[0]
        tier=self._route(run_id,node,attempt); self._set_state(run_id,"VERIFYING" if node["id"] in {"design_critique","verify"} else "RUNNING")
        while True:
            started=utcnow(); self.store.connection.execute("INSERT INTO task_attempts VALUES(?,?,?,?,?,?,?,?,?)",(run_id,node["id"],attempt,node["role_id"],tier,"RUNNING",None,started,None))
            result=self.executor.execute(role_id=node["role_id"],task_id=node["id"],tier=tier,inputs=self._inputs(run_id,node["requires"]),produces=node["produces"],attempt=attempt,authorization_policy=self.compiled.registry["authorization_policies"][self.compiled.registry["default_authorization_policy"]])
            outcome=result["outcome"]
            if outcome=="escalate":
                self.store.connection.execute("UPDATE task_attempts SET status='ESCALATED',outcome=?,finished_at=? WHERE run_id=? AND node_id=? AND attempt=?",(outcome,utcnow(),run_id,node["id"],attempt))
                target=self.compiled.registry["agents"][node["role_id"]].get("escalation_tier")
                if not target: raise ValueError(f"role {node['role_id']} cannot escalate")
                attempt+=1; tier=self._route(run_id,node,attempt,target,result["reason_code"]); continue
            for artifact_type,content in result["artifacts"].items(): self._artifact(run_id,artifact_type,node["id"],content)
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
            self.store.connection.execute("INSERT INTO gates VALUES(?,?,?,?,?,?,?,?,?,?)",(gate_id,run_id,node["id"],node["gate_type"],"pending",json.dumps(evidence,sort_keys=True),utcnow(),None,None,None))
            self.store.event(run_id,"gate_requested",node["id"],gate_id=gate_id,gate_type=node["gate_type"],evidence=evidence)
        self._set_state(run_id,"AWAITING_HUMAN")

    def decide_gate(self, run_id: str, decision: str, decided_by: str, reason: str) -> None:
        if decision not in {"approved","rejected"}: raise ValueError(decision)
        run=self.store.run(run_id); node=self.nodes[run["current_node"]]
        if node["type"]!="gate" or run["state"]!="AWAITING_HUMAN": raise ValueError("run is not awaiting a gate decision")
        gate=self.store.connection.execute("SELECT * FROM gates WHERE run_id=? AND node_id=? AND status='pending' ORDER BY requested_at DESC LIMIT 1",(run_id,node["id"])).fetchone()
        if not gate: raise ValueError("no pending gate")
        self.store.connection.execute("UPDATE gates SET status=?,decided_at=?,decided_by=?,reason=? WHERE gate_id=?",(decision,utcnow(),decided_by,reason,gate["gate_id"]))
        evidence=json.loads(gate["evidence_json"]); self._artifact(run_id,"human_gate_evidence",node["id"],{"gate_id":gate["gate_id"],"decision":decision,"evidence":evidence,"decided_by":decided_by,"reason":reason})
        self.store.event(run_id,"gate_decided",node["id"],gate_id=gate["gate_id"],decision=decision,reason=reason,decided_by=decided_by)
        self._move(run_id,node["id"],decision)
        self._set_state(run_id,"REWORK_REQUIRED" if decision=="rejected" else "ROUTED"); self.store.connection.commit()

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

    def inspect(self, run_id: str) -> dict[str, Any]:
        run=self.store.run(run_id)
        return {"run":run,"events":self.store.events(run_id),"artifacts":[dict(r) for r in self.store.connection.execute("SELECT artifact_id,artifact_type,producer_node,content_hash,active,created_at FROM artifacts WHERE run_id=? ORDER BY created_at",(run_id,))],"gates":[dict(r) for r in self.store.connection.execute("SELECT * FROM gates WHERE run_id=? ORDER BY requested_at",(run_id,))],"routing":[dict(r) for r in self.store.connection.execute("SELECT * FROM routing_events WHERE run_id=? ORDER BY id",(run_id,))]}
