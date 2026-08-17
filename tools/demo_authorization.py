"""Print deterministic ALLOW, DENY, and REQUIRE_GATE authorization decisions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestration.authorization import AuthorizationService
from orchestration.compiler import compile_system


def main() -> int:
    compiled = compile_system(ROOT)
    service = AuthorizationService(compiled.registry, compiled.capabilities)
    decisions = [
        service.decide(role_id="architect", capability="repo.read", resource="orchestration/runtime.py"),
        service.decide(role_id="test_executor", capability="repo.write", resource="orchestration/runtime.py"),
        service.decide(role_id="knowledge_curator", capability="wiki.write", resource="github_wiki:Architecture", task_context={"external_system_category": "github_wiki"}),
    ]
    print(json.dumps([decision.as_dict() for decision in decisions], indent=2, sort_keys=True))
    return 0 if [decision.decision for decision in decisions] == ["ALLOW", "DENY", "REQUIRE_GATE"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
