from __future__ import annotations

import tempfile
import unittest
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
        self.assertEqual(("REQUIRE_GATE", "release_approval"), (publish.decision, publish.applicable_gate))
        approval = GateApproval.for_resource("release_approval", "wiki.write", "github_wiki:Architecture")
        approved = self.decide("knowledge_curator", "wiki.write", "github_wiki:Architecture", {"external_system_category": "github_wiki"}, [approval])
        self.assertEqual("ALLOW", approved.decision)

    def test_merge_deploy_and_destructive_actions_require_gate(self):
        for capability, resource in (("vcs.merge", "main"), ("deploy.execute", "production"), ("destructive.execute", "fixture:42")):
            with self.subTest(capability=capability):
                self.assertEqual("REQUIRE_GATE", self.decide("orchestrator", capability, resource).decision)

    def test_stale_gate_approval_does_not_authorize(self):
        approval = GateApproval.for_resource("release_approval", "vcs.merge", "main")
        stale = GateApproval(approval.gate_type, approval.capability, approval.resource_hash, approval.policy_version, stale=True)
        result = self.decide("orchestrator", "vcs.merge", "main", approvals=[stale])
        self.assertEqual(("REQUIRE_GATE", "GATE_APPROVAL_STALE_OR_INVALID"), (result.decision, result.reason_code))

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


if __name__ == "__main__":
    unittest.main()
