from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from tools.validate_contracts import ContractError, load_json, load_yaml, validate_registry_data, validate_repository


ROOT = Path(__file__).resolve().parents[1]


class ContractValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_yaml(ROOT / ".agents/agent-registry.yaml")
        cls.workflows = {
            workflow_id: json.loads((ROOT / definition["definition_file"]).read_text(encoding="utf-8"))
            for workflow_id, definition in cls.registry["workflows"].items()
        }

    def validate(self, registry=None, workflows=None):
        return validate_registry_data(
            ROOT,
            copy.deepcopy(registry or self.registry),
            copy.deepcopy(workflows or self.workflows),
        )

    def test_repository_contracts_are_valid(self):
        self.assertEqual([], validate_repository(ROOT))

    def test_missing_referenced_file_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["agents"]["architect"]["role_file"] = ".agents/roles/missing.md"
        self.assertTrue(any("referenced file does not exist" in error for error in self.validate(registry)))

    def test_unknown_registered_role_skill_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["agents"]["architect"]["skills"] = ["missing-skill"]
        self.assertTrue(any("unknown skill" in error for error in self.validate(registry)))

    def test_unknown_skill_dependency_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["skills"]["qa-agent-team"]["dependencies"]["skills"].append("missing-skill")
        self.assertTrue(any("unknown skill dependency" in error for error in self.validate(registry)))

    def test_unknown_standard_dependency_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["skills"]["qa-agent-team"]["dependencies"]["standards"] = ["missing-standard"]
        self.assertTrue(any("unknown standard dependency" in error for error in self.validate(registry)))

    def test_unknown_workflow_role_is_rejected(self):
        workflows = copy.deepcopy(self.workflows)
        workflows["qa"]["nodes"][0]["role_id"] = "missing_role"
        self.assertTrue(any("references unknown role" in error for error in self.validate(workflows=workflows)))

    def test_unknown_role_capability_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["agents"]["architect"]["capability_policy"]["allowed"].append("unknown.action")
        self.assertTrue(any("unknown capability" in error for error in self.validate(registry)))

    def test_conflicting_role_capability_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["agents"]["architect"]["capability_policy"]["denied"].append("repo.read")
        self.assertTrue(any("conflicting capability policies" in error for error in self.validate(registry)))

    def test_gated_capability_requires_valid_gate_type(self):
        registry = copy.deepcopy(self.registry)
        registry["agents"]["knowledge_curator"]["capability_policy"]["gated"][0]["gate_type"] = "unknown_gate"
        self.assertTrue(any("references unknown gate type" in error for error in self.validate(registry)))

    def test_invalid_verdict_enum_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["enums"]["verifier_verdicts"][-1] = "UNKNOWN"
        self.assertTrue(any("verifier verdict enum" in error for error in self.validate(registry)))

    def test_invalid_tier_transition_is_rejected(self):
        registry = copy.deepcopy(self.registry)
        registry["routing_policy"]["allowed_transitions"]["standard"] = ["economy"]
        self.assertTrue(any("standard -> high_reasoning is not allowed" in error for error in self.validate(registry)))

    def test_missing_required_gate_is_rejected(self):
        workflows = copy.deepcopy(self.workflows)
        workflows["automate"]["nodes"] = [
            node for node in workflows["automate"]["nodes"] if node["id"] != "design_gate"
        ]
        self.assertTrue(any("required gate is missing: design_approval" in error for error in self.validate(workflows=workflows)))

    def test_duplicate_workflow_node_id_is_rejected(self):
        workflows = copy.deepcopy(self.workflows)
        workflows["qa"]["nodes"].append(copy.deepcopy(workflows["qa"]["nodes"][0]))
        self.assertTrue(any("duplicate node IDs" in error for error in self.validate(workflows=workflows)))

    def test_duplicate_yaml_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.yaml"
            path.write_text("schema_version: one\nschema_version: two\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                load_yaml(path)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"workflow_id": "one", "workflow_id": "two"}', encoding="utf-8")
            with self.assertRaises(ContractError):
                load_json(path)

    def test_skill_front_matter_requires_exact_delimiters(self):
        for definition in self.registry["skills"].values():
            lines = (ROOT / definition["skill_file"]).read_text(encoding="utf-8").splitlines()
            self.assertEqual("---", lines[0])
            self.assertIn("---", lines[1:])


if __name__ == "__main__":
    unittest.main()
