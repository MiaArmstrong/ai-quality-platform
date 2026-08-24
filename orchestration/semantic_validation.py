from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SEMANTIC_VALIDATION_STATUSES = {"VALID", "INVALID", "WARNING"}
SEMANTIC_VALIDATION_SEVERITIES = {"ERROR", "WARNING"}


@dataclass(frozen=True)
class SemanticValidationFinding:
    rule_id: str
    artifact_type: str
    field_paths: tuple[str, ...]
    message: str
    severity: str
    repairable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "artifact_type": self.artifact_type,
            "field_paths": list(self.field_paths),
            "message": self.message,
            "severity": self.severity,
            "repairable": self.repairable,
        }


@dataclass(frozen=True)
class SemanticValidationResult:
    status: str
    findings: tuple[SemanticValidationFinding, ...] = ()

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.rule_id for item in self.findings))

    @property
    def repairable(self) -> bool:
        errors = tuple(item for item in self.findings if item.severity == "ERROR")
        return bool(errors) and all(item.repairable for item in errors)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rule_ids": list(self.rule_ids),
            "repairable": self.repairable,
            "findings": [item.as_dict() for item in self.findings],
        }


class SemanticOutputValidator:
    """Provider-neutral cross-field validation for schema-valid role outputs."""

    ARCHITECT_SUCCESS_WITH_ESCALATION = "architect_escalation_success_conflict/v1"
    ARCHITECT_ESCALATION_UNAVAILABLE = "architect_escalation_unavailable_tier/v1"

    def validate(
        self,
        *,
        role_id: str,
        outcome: str,
        artifacts: Mapping[str, Any],
        escalation_available: bool,
    ) -> SemanticValidationResult:
        findings: list[SemanticValidationFinding] = []
        if role_id == "architect":
            design = artifacts.get("automation_design")
            if isinstance(design, Mapping) and design.get("escalation_requested") is True:
                if outcome == "success":
                    findings.append(SemanticValidationFinding(
                        rule_id=self.ARCHITECT_SUCCESS_WITH_ESCALATION,
                        artifact_type="automation_design",
                        field_paths=("$.outcome", "$.artifacts.automation_design.escalation_requested"),
                        message="A successful non-escalated Architect result cannot request escalation.",
                        severity="ERROR",
                        repairable=True,
                    ))
                if not escalation_available:
                    findings.append(SemanticValidationFinding(
                        rule_id=self.ARCHITECT_ESCALATION_UNAVAILABLE,
                        artifact_type="automation_design",
                        field_paths=("$.artifacts.automation_design.escalation_requested", "$.outcome"),
                        message="Architect requested escalation, but its role contract has no higher escalation tier.",
                        severity="ERROR",
                        repairable=True,
                    ))

        if any(item.severity == "ERROR" for item in findings):
            status = "INVALID"
        elif findings:
            status = "WARNING"
        else:
            status = "VALID"
        return SemanticValidationResult(status=status, findings=tuple(findings))
