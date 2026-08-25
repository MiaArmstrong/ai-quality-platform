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
    REQUIREMENTS_READY_BLOCKED = "requirements_ready_with_blockers/v1"
    REQUIREMENTS_BLOCKED_EMPTY = "requirements_blocked_without_condition/v1"
    REQUIREMENTS_NEEDS_INFO_EMPTY = "requirements_needs_info_without_gap/v1"
    VERIFIER_REFUTED_EMPTY = "verifier_refuted_without_claim/v1"
    VERIFIER_SUPPORTED_CRITICAL = "verifier_supported_with_critical_concern/v1"
    VERIFIER_INSUFFICIENT_EMPTY = "verifier_insufficient_without_gap/v1"
    VERIFIER_CONCERNS_EMPTY = "verifier_concerns_without_concern/v1"

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

        if role_id == "requirements_analyst":
            readiness = artifacts.get("requirements_readiness")
            if isinstance(readiness, Mapping):
                verdict = readiness.get("verdict")
                blocking_gaps = any(item.get("blocks_readiness") is True for item in readiness.get("missing_information", ()) if isinstance(item, Mapping))
                blocking_conflicts = any(item.get("blocks_readiness") is True for item in readiness.get("conflicts", ()) if isinstance(item, Mapping))
                concrete_conditions = any(str(item.get("description", "")).strip() for item in readiness.get("blocking_conditions", ()) if isinstance(item, Mapping))
                blockers = concrete_conditions or blocking_gaps or blocking_conflicts
                if verdict == "READY" and blockers:
                    findings.append(self._finding(self.REQUIREMENTS_READY_BLOCKED, "requirements_readiness", ("$.artifacts.requirements_readiness.verdict", "$.artifacts.requirements_readiness.blocking_conditions"), "READY cannot include a blocking gap, conflict, or condition."))
                if verdict == "BLOCKED" and not blockers:
                    findings.append(self._finding(self.REQUIREMENTS_BLOCKED_EMPTY, "requirements_readiness", ("$.artifacts.requirements_readiness.verdict", "$.artifacts.requirements_readiness.blocking_conditions"), "BLOCKED requires a concrete blocking condition."))
                meaningful_gaps = any(str(item.get("description", "")).strip() for item in readiness.get("missing_information", ()) if isinstance(item, Mapping))
                if verdict == "NEEDS_INFO" and not meaningful_gaps:
                    findings.append(self._finding(self.REQUIREMENTS_NEEDS_INFO_EMPTY, "requirements_readiness", ("$.artifacts.requirements_readiness.verdict", "$.artifacts.requirements_readiness.missing_information"), "NEEDS_INFO requires at least one unresolved information gap."))

        if role_id == "adversarial_verifier":
            review = artifacts.get("verifier_result") or artifacts.get("adversarial_review")
            review_type = "verifier_result" if "verifier_result" in artifacts else "adversarial_review"
            if isinstance(review, Mapping):
                verdict = review.get("verdict")
                claims = review.get("challenged_claims", ())
                if verdict == "REFUTED" and not any(item.get("assessment") == "REFUTED" and str(item.get("claim", "")).strip() for item in claims if isinstance(item, Mapping)):
                    findings.append(self._finding(self.VERIFIER_REFUTED_EMPTY, review_type, (f"$.artifacts.{review_type}.verdict", f"$.artifacts.{review_type}.challenged_claims"), "REFUTED requires a concrete refuted claim."))
                if verdict == "SUPPORTED" and any(item.get("critical") is True for item in review.get("concerns", ()) if isinstance(item, Mapping)):
                    findings.append(self._finding(self.VERIFIER_SUPPORTED_CRITICAL, review_type, (f"$.artifacts.{review_type}.verdict", f"$.artifacts.{review_type}.concerns"), "SUPPORTED cannot contain a critical unresolved concern."))
                if verdict == "INSUFFICIENT_EVIDENCE" and not any(str(item).strip() for item in review.get("evidence_gaps", ())):
                    findings.append(self._finding(self.VERIFIER_INSUFFICIENT_EMPTY, review_type, (f"$.artifacts.{review_type}.verdict", f"$.artifacts.{review_type}.evidence_gaps"), "INSUFFICIENT_EVIDENCE requires a concrete evidence gap."))
                if verdict == "SUPPORTED_WITH_CONCERNS" and not any(str(item.get("description", "")).strip() for item in review.get("concerns", ()) if isinstance(item, Mapping)):
                    findings.append(self._finding(self.VERIFIER_CONCERNS_EMPTY, review_type, (f"$.artifacts.{review_type}.verdict", f"$.artifacts.{review_type}.concerns"), "SUPPORTED_WITH_CONCERNS requires at least one concern."))

        if any(item.severity == "ERROR" for item in findings):
            status = "INVALID"
        elif findings:
            status = "WARNING"
        else:
            status = "VALID"
        return SemanticValidationResult(status=status, findings=tuple(findings))

    @staticmethod
    def _finding(rule_id: str, artifact_type: str, field_paths: tuple[str, ...], message: str) -> SemanticValidationFinding:
        return SemanticValidationFinding(rule_id, artifact_type, field_paths, message, "ERROR", True)
