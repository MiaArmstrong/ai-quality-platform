from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestration.compiler import compile_system
from orchestration.runtime import MockRoleExecutor, OrchestrationEngine, SQLiteEventStore


ROOT = Path(__file__).resolve().parents[1]


class AutomateRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "runtime.db"
        self.compiled = compile_system(ROOT)
        self.store = SQLiteEventStore(self.db)
        self.executor = MockRoleExecutor()
        self.engine = OrchestrationEngine(self.compiled, self.store, self.executor)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def start(self):
        return self.engine.start({"id": "WORK-1", "objective": "mock automation"})

    def approve(self, run_id, reason="approved evidence"):
        self.engine.decide_gate(run_id, "approved", "test-human", reason)
        return self.engine.resume(run_id)

    def test_contracts_compile_to_immutable_snapshot(self):
        self.assertEqual("compiled-system/v1", self.compiled.schema_version)
        self.assertEqual(64, len(self.compiled.snapshot_hash))
        with self.assertRaises(TypeError):
            self.compiled.registry["new"] = "value"
        with self.assertRaises(TypeError):
            self.compiled.registry["agents"]["architect"]["default_tier"] = "economy"

    def test_invalid_runtime_transition_fails(self):
        run_id = self.start()
        self.store.connection.execute("UPDATE runs SET state='CREATED' WHERE run_id=?", (run_id,))
        self.store.connection.commit()
        with self.assertRaisesRegex(ValueError, "invalid state transition"):
            self.engine._set_state(run_id, "COMPLETED")

    def test_stops_at_design_gate_and_cannot_bypass(self):
        run_id = self.start()
        run = self.store.run(run_id)
        self.assertEqual(("design_gate", "AWAITING_HUMAN"), (run["current_node"], run["state"]))
        self.store.connection.execute("UPDATE runs SET current_node='implement',state='ROUTED' WHERE run_id=?", (run_id,))
        self.store.connection.commit()
        with self.assertRaisesRegex(ValueError, "missing required artifact human_gate_evidence"):
            self.engine.resume(run_id)

    def test_design_approval_resumes_to_release_gate(self):
        run_id = self.start()
        run = self.approve(run_id)
        self.assertEqual(("release_gate", "AWAITING_HUMAN"), (run["current_node"], run["state"]))

    def test_design_rejection_returns_to_design(self):
        run_id = self.start()
        self.engine.decide_gate(run_id, "rejected", "test-human", "design needs rework")
        self.assertEqual("design", self.store.run(run_id)["current_node"])
        run = self.engine.resume(run_id)
        self.assertEqual("design_gate", run["current_node"])
        self.assertEqual(2, sum(1 for task, _ in self.executor.calls if task == "design"))

    def test_changed_approved_artifact_invalidates_gate(self):
        run_id = self.start()
        self.engine.decide_gate(run_id, "approved", "test-human", "design approved")
        self.engine.replace_artifact(run_id, "automation_design", {"material_change": True})
        run = self.store.run(run_id)
        self.assertEqual(("design_gate", "AWAITING_HUMAN"), (run["current_node"], run["state"]))
        statuses = [row[0] for row in self.store.connection.execute("SELECT status FROM gates WHERE run_id=? AND gate_type='design_approval'", (run_id,))]
        self.assertIn("stale", statuses)

    def test_changed_pending_evidence_rejects_old_gate_and_requires_reissue(self):
        run_id=self.start()
        old_gate=self.store.connection.execute("SELECT gate_id FROM gates WHERE run_id=? AND status='pending'",(run_id,)).fetchone()[0]
        self.engine.replace_artifact(run_id,"automation_design",{"material_change":True})
        with self.assertRaisesRegex(ValueError,"no pending gate"):
            self.engine.decide_gate(run_id,"approved","test-human","stale approval")
        self.assertEqual("stale",self.store.connection.execute("SELECT status FROM gates WHERE gate_id=?",(old_gate,)).fetchone()[0])
        self.engine.resume(run_id)
        new_gate=self.store.connection.execute("SELECT gate_id FROM gates WHERE run_id=? AND status='pending'",(run_id,)).fetchone()[0]
        self.assertNotEqual(old_gate,new_gate)

    def test_release_gate_blocks_and_rejection_uses_rework_state(self):
        run_id = self.start()
        self.approve(run_id)
        self.engine.decide_gate(run_id, "rejected", "test-human", "implementation rework")
        run = self.store.run(run_id)
        self.assertEqual(("release_rework", "REWORK_REQUIRED"), (run["current_node"], run["state"]))
        run = self.engine.resume(run_id)
        self.assertEqual(("release_gate", "AWAITING_HUMAN"), (run["current_node"], run["state"]))

    def test_release_gate_cannot_be_bypassed_and_completion_requires_both_gates(self):
        run_id = self.start()
        self.approve(run_id)
        self.store.connection.execute("UPDATE runs SET current_node='completed',state='ROUTED' WHERE run_id=?", (run_id,))
        self.store.connection.commit()
        with self.assertRaisesRegex(ValueError, "release_approval"):
            self.engine.resume(run_id)

    def test_complete_only_after_both_approvals(self):
        run_id = self.start()
        self.approve(run_id)
        run = self.approve(run_id, "release evidence approved")
        self.assertEqual("COMPLETED", run["state"])
        gate_types = {row[0] for row in self.store.connection.execute("SELECT gate_type FROM gates WHERE run_id=? AND status='approved'", (run_id,))}
        self.assertEqual({"design_approval", "release_approval"}, gate_types)

    def test_persistence_reload_and_completed_attempt_idempotency(self):
        run_id = self.start()
        attempts_before = self.store.connection.execute("SELECT COUNT(*) FROM task_attempts WHERE run_id=?", (run_id,)).fetchone()[0]
        self.store.close()
        self.store = SQLiteEventStore(self.db)
        self.engine = OrchestrationEngine(self.compiled, self.store, MockRoleExecutor())
        self.engine.resume(run_id)
        attempts_after = self.store.connection.execute("SELECT COUNT(*) FROM task_attempts WHERE run_id=?", (run_id,)).fetchone()[0]
        self.assertEqual(attempts_before, attempts_after)

    def test_unresolved_provider_attempt_blocks_resume_without_duplicate_request(self):
        class CrashBoundaryExecutor:
            def __init__(self, phase): self.phase=phase; self.calls=0; self.authorization=None
            def attempt_descriptor(self, role_id, tier): return {"provider":"synthetic","model":"synthetic-model"}
            def execute(self, **kwargs):
                self.calls+=1
                if self.phase=="after_response": self.response_observed=True
                raise SystemExit(self.phase)
        for phase in ("before_request","after_response"):
            with self.subTest(phase=phase):
                self.store.close(); self.temp.cleanup()
                self.temp=tempfile.TemporaryDirectory(); self.db=Path(self.temp.name)/"runtime.db"
                self.store=SQLiteEventStore(self.db); crashing=CrashBoundaryExecutor(phase)
                self.engine=OrchestrationEngine(self.compiled,self.store,crashing)
                with self.assertRaises(SystemExit): self.engine.start({"id":phase})
                run_id=self.store.connection.execute("SELECT run_id FROM runs").fetchone()[0]
                row=self.store.connection.execute("SELECT status,correlation_id FROM provider_attempts WHERE run_id=?",(run_id,)).fetchone()
                self.assertEqual("IN_PROGRESS",row["status"]); self.assertTrue(row["correlation_id"])
                self.store.close(); self.store=SQLiteEventStore(self.db)
                replacement=CrashBoundaryExecutor("must_not_run"); self.engine=OrchestrationEngine(self.compiled,self.store,replacement)
                result=self.engine.resume(run_id)
                self.assertEqual("BLOCKED",result["state"]); self.assertEqual(0,replacement.calls)
                self.engine.abandon_provider_attempt(run_id,row["correlation_id"],"test-human","cannot prove idempotent retry")
                self.assertEqual("FAILED",self.store.run(run_id)["state"])
                self.assertEqual("ABANDONED",self.store.connection.execute("SELECT status FROM provider_attempts WHERE correlation_id=?",(row["correlation_id"],)).fetchone()[0])

    def test_routing_events_are_recorded(self):
        run_id = self.start()
        rows = self.store.connection.execute("SELECT role_id,selected_tier FROM routing_events WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        self.assertEqual([("architect", "high_reasoning"), ("adversarial_verifier", "high_reasoning")], [tuple(row) for row in rows])

    def test_escalation_creates_new_attempt_and_event(self):
        self.executor = MockRoleExecutor({"implement": ["escalate", "success"]})
        self.engine = OrchestrationEngine(self.compiled, self.store, self.executor)
        run_id = self.start()
        self.approve(run_id)
        attempts = self.store.connection.execute("SELECT attempt,status,tier FROM task_attempts WHERE run_id=? AND node_id='implement' ORDER BY attempt", (run_id,)).fetchall()
        self.assertEqual([(1, "ESCALATED", "standard"), (2, "COMPLETED", "high_reasoning")], [tuple(row) for row in attempts])
        transitions = [row[0] for row in self.store.connection.execute("SELECT transition FROM routing_events WHERE run_id=? AND task_id='implement' ORDER BY id", (run_id,))]
        self.assertEqual(["none", "escalate"], transitions)

    def test_repeated_escalation_stops_at_highest_tier(self):
        self.executor=MockRoleExecutor({"implement":["escalate","escalate","success"]})
        self.engine=OrchestrationEngine(self.compiled,self.store,self.executor)
        run_id=self.start(); self.approve(run_id)
        self.assertEqual("INSUFFICIENT_EVIDENCE",self.store.run(run_id)["state"])
        attempts=self.store.connection.execute("SELECT attempt,tier,status FROM task_attempts WHERE run_id=? AND node_id='implement' ORDER BY attempt",(run_id,)).fetchall()
        self.assertEqual([(1,"standard","ESCALATED"),(2,"high_reasoning","INSUFFICIENT_EVIDENCE")],[tuple(row) for row in attempts])


if __name__ == "__main__":
    unittest.main()
