from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from orchestration.authorization import AuthorizationService, GateApproval
from orchestration.compiler import compile_system
from orchestration.runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore


ROOT = Path(__file__).resolve().parents[1]


class AuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = compile_system(ROOT)

    def setUp(self):
        self.service = AuthorizationService(self.compiled.registry, self.compiled.capabilities)

    def decide(self, role, capability, resource=".", context=None, approvals=()):
        return self.service.decide(role_id=role, capability=capability, resource=resource, task_context=context or {}, gate_approvals=approvals)

    def test_unknown_capability_is_denied(self):
        result = self.decide("architect", "unknown.action")
        self.assertEqual(("DENY", "UNKNOWN_CAPABILITY"), (result.decision, result.reason_code))

    def test_role_denied_repo_write_cannot_write(self):
        result = self.decide("requirements_analyst", "repo.write", "requirements.md")
        self.assertEqual(("DENY", "EXPLICITLY_DENIED"), (result.decision, result.reason_code))

    def test_implementer_can_write_within_task_scope(self):
        result = self.decide("implementer", "repo.write", "orchestration/authorization.py", {"authorized_paths": ["orchestration/"]})
        self.assertEqual("ALLOW", result.decision)

    def test_implementer_cannot_write_outside_task_scope(self):
        result = self.decide("implementer", "repo.write", "tests/test_other.py", {"authorized_paths": ["orchestration/"]})
        self.assertEqual(("DENY", "WRITE_SCOPE_NOT_AUTHORIZED"), (result.decision, result.reason_code))

    def test_implementer_cannot_override_read_only_directory(self):
        result = self.decide("implementer", "repo.write", ".agents/roles/architect.md", {"authorized_paths": [".agents/"]})
        self.assertEqual(("DENY", "READ_ONLY_SCOPE"), (result.decision, result.reason_code))

    def test_test_executor_cannot_modify_product_code(self):
        result = self.decide("test_executor", "repo.write", "orchestration/runtime.py")
        self.assertEqual("DENY", result.decision)

    def test_knowledge_curator_can_propose_but_publish_requires_gate(self):
        proposal = self.decide("knowledge_curator", "wiki.propose_write", "github_wiki:Architecture", {"external_system_category": "github_wiki"})
        publish = self.decide("knowledge_curator", "wiki.write", "github_wiki:Architecture", {"external_system_category": "github_wiki"})
        self.assertEqual("ALLOW", proposal.decision)
        self.assertEqual(("REQUIRE_GATE", "knowledge_publication_approval"), (publish.decision, publish.applicable_gate))
        forged = GateApproval("run-1", "gate-1", "knowledge_publication_approval", "wiki.write", ("x",), ("y",), "human", "now", "role-capability-policy/v1")
        approved = self.decide("knowledge_curator", "wiki.write", "github_wiki:Architecture", {"external_system_category": "github_wiki", "workflow_run_id": "run-1"}, [forged])
        self.assertEqual("REQUIRE_GATE", approved.decision)

    def test_merge_deploy_and_destructive_actions_require_gate(self):
        for capability, resource in (("vcs.merge", "main"), ("deploy.execute", "production"), ("destructive.execute", "fixture:42")):
            with self.subTest(capability=capability):
                self.assertEqual("REQUIRE_GATE", self.decide("orchestrator", capability, resource).decision)

    def test_stale_gate_approval_does_not_authorize(self):
        stale = GateApproval("run-1", "gate-1", "release_approval", "vcs.merge", ("x",), ("y",), "human", "now", "role-capability-policy/v1", stale=True)
        result = self.decide("orchestrator", "vcs.merge", "main", approvals=[stale])
        self.assertEqual(("REQUIRE_GATE", "HUMAN_GATE_REQUIRED"), (result.decision, result.reason_code))

    def test_untrusted_approval_record_cannot_authorize(self):
        approval = GateApproval("run-1", "gate-1", "knowledge_publication_approval", "wiki.write", ("x",), ("y",), "human", "now", "role-capability-policy/v1")
        result = self.decide("knowledge_curator", "wiki.write", "github_wiki:Architecture", {"external_system_category": "github_wiki"}, [approval])
        self.assertEqual("REQUIRE_GATE", result.decision)

    def test_only_genuine_persisted_current_approval_authorizes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "runtime.db")
            try:
                engine = OrchestrationEngine(self.compiled, store, MockRoleExecutor())
                run_id = engine.start({"id": "GATE-AUTH"})
                evidence_row = store.connection.execute("SELECT artifact_id,content_hash FROM artifacts WHERE run_id=? AND artifact_type='work_item' AND active=1",(run_id,)).fetchone()
                evidence = {"work_item": dict(evidence_row)}
                resource = "github_wiki:Architecture"
                resource_hash = hashlib.sha256(resource.encode()).hexdigest()
                store.connection.execute("INSERT INTO gates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",("publish-1",run_id,"design_gate","knowledge_publication_approval","approved",json.dumps(evidence),"now","now","human","approved",engine.authorization.policy_version,json.dumps([resource_hash]),"wiki.write"))
                store.connection.commit()
                allowed = engine.authorization.decide(role_id="knowledge_curator",capability="wiki.write",resource=resource,task_context={"external_system_category":"github_wiki","workflow_run_id":run_id})
                self.assertEqual("ALLOW", allowed.decision)
                for changed in ({"task_context":{"external_system_category":"github_wiki","workflow_run_id":"other"}},{"capability":"vcs.merge"},{"resource":"github_wiki:Other"}):
                    args={"role_id":"knowledge_curator","capability":"wiki.write","resource":resource,"task_context":{"external_system_category":"github_wiki","workflow_run_id":run_id}}
                    args.update(changed)
                    self.assertNotEqual("ALLOW", engine.authorization.decide(**args).decision)
                engine.replace_artifact(run_id,"work_item",{"id":"changed"})
                stale = engine.authorization.decide(role_id="knowledge_curator",capability="wiki.write",resource=resource,task_context={"external_system_category":"github_wiki","workflow_run_id":run_id})
                self.assertEqual("REQUIRE_GATE", stale.decision)
            finally:
                store.close()

    def test_failure_triage_test_execution_requires_task_grant(self):
        denied = self.decide("failure_triage_analyst", "tests.run", "tests", {"command_category": "test"})
        allowed = self.decide("failure_triage_analyst", "tests.run", "tests", {"command_category": "test", "granted_capabilities": ["tests.run"]})
        self.assertEqual("DENY", denied.decision)
        self.assertEqual("ALLOW", allowed.decision)

    def test_decisions_are_auditable(self):
        result = self.decide("architect", "repo.read", "orchestration/runtime.py")
        self.assertEqual(result, self.service.audit_log[-1])
        self.assertEqual("authorization-event/v1", result.schema_version)
        self.assertTrue(result.decision_id)

    def test_mock_executor_enforces_declared_action(self):
        executor = MockRoleExecutor(authorization=self.service)
        with self.assertRaisesRegex(PermissionError, "authorization DENY"):
            executor.execute(role_id="test_executor", task_id="bad_write", tier="economy", inputs={}, produces=[], attempt=1, actions=[{"capability": "repo.write", "resource": "orchestration/runtime.py"}], task_context={}, gate_approvals=[])

    def test_workflow_authorization_decisions_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteEventStore(Path(directory) / "runtime.db")
            try:
                engine = OrchestrationEngine(self.compiled, store, MockRoleExecutor())
                run_id = engine.start({"id": "AUTH-1"})
                events = [event for event in store.events(run_id) if event["event_type"] == "authorization_decision"]
                self.assertGreaterEqual(len(events), 4)
                self.assertTrue(all(event["payload"]["decision"] == "ALLOW" for event in events))
            finally:
                store.close()

    def test_denied_and_gate_required_attempts_are_durable_and_terminal(self):
        cases=(
            ({"id":"design","type":"task","role_id":"architect","requires":[],"produces":[],"actions":[{"capability":"repo.write","resource":"orchestration/runtime.py"}]},"DENY","FAILED"),
            ({"id":"design","type":"task","role_id":"orchestrator","requires":[],"produces":[],"actions":[{"capability":"vcs.merge","resource":"main"}]},"REQUIRE_GATE","BLOCKED"),
        )
        for node,decision,state in cases:
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as directory:
                store=SQLiteEventStore(Path(directory)/"runtime.db")
                try:
                    engine=OrchestrationEngine(self.compiled,store,MockRoleExecutor())
                    run_id=str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
                    store.connection.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",(run_id,"automate",self.compiled.snapshot_hash,"design","ROUTED",now,now)); store.connection.commit()
                    with self.assertRaises(PermissionError): engine._execute_task(run_id,node)
                    events=[event for event in store.events(run_id) if event["event_type"]=="authorization_decision"]
                    self.assertTrue(any(event["payload"]["decision"]==decision for event in events))
                    self.assertEqual(state,store.run(run_id)["state"])
                finally: store.close()

    def test_undeclared_artifact_read_and_write_are_denied(self):
        nodes=(
            {"id":"design","type":"task","role_id":"architect","requires":["work_item"],"produces":[],"actions":[]},
            {"id":"design","type":"task","role_id":"architect","requires":[],"produces":["automation_design"],"actions":[]},
        )
        for node in nodes:
            with self.subTest(node=node), tempfile.TemporaryDirectory() as directory:
                store=SQLiteEventStore(Path(directory)/"runtime.db")
                try:
                    engine=OrchestrationEngine(self.compiled,store,MockRoleExecutor())
                    run_id=str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
                    store.connection.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",(run_id,"automate",self.compiled.snapshot_hash,"design","ROUTED",now,now))
                    engine._artifact(run_id,"work_item","input",{"id":"IO"}); store.connection.commit()
                    with self.assertRaisesRegex(PermissionError,"WORKFLOW_ACTION_UNDECLARED"): engine._execute_task(run_id,node)
                    decisions=[e["payload"] for e in store.events(run_id) if e["event_type"]=="authorization_decision"]
                    self.assertTrue(any(item["reason_code"]=="WORKFLOW_ACTION_UNDECLARED" for item in decisions))
                finally: store.close()


if __name__ == "__main__":
    unittest.main()
