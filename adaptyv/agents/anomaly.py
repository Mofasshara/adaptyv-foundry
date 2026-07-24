from __future__ import annotations

from adaptyv.agents.policy import AnomalyPolicy
from adaptyv.governance.models import AnomalyFinding
from adaptyv.models import AffinityResultSummary, ResultInfo


def _label(s: AffinityResultSummary) -> str:
    return s.sequence.name or s.sequence.aa_string[:8]


class AnomalyDetector:
    """Pure, deterministic. Never calls Claude; never does I/O."""

    def __init__(self, policy: AnomalyPolicy) -> None:
        self._policy = policy

    def detect(self, result: ResultInfo) -> list[AnomalyFinding]:
        affinity = [s for s in result.summary if isinstance(s, AffinityResultSummary)]
        findings: list[AnomalyFinding] = []
        findings.extend(self._all_failed(affinity))
        findings.extend(self._control_out_of_policy(affinity))
        findings.extend(self._kd_out_of_bounds(affinity))
        findings.extend(self._missing_replicates(affinity))
        return findings

    def _all_failed(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        non_control = [s for s in affinity if not s.positive_control]
        if non_control and all(s.kd_mean is None for s in non_control):
            ids = [_label(s) for s in non_control]
            return [AnomalyFinding(
                rule="all_sequences_failed", severity="critical",
                evidence=f"0/{len(non_control)} non-control sequences showed measurable binding (kd_mean unset)",
                affected_ids=ids, policy_version=self._policy.version)]
        return []

    def _control_out_of_policy(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        out = []
        for s in affinity:
            if s.positive_control and s.kd_mean is not None:
                if not (self._policy.positive_control_kd_min <= s.kd_mean <= self._policy.positive_control_kd_max):
                    out.append(AnomalyFinding(
                        rule="control_out_of_policy", severity="critical",
                        evidence=(f"positive control kd_mean={s.kd_mean:.2e} {s.kd_units} outside "
                                 f"policy range [{self._policy.positive_control_kd_min:.2e}, "
                                 f"{self._policy.positive_control_kd_max:.2e}]"),
                        affected_ids=[_label(s)], policy_version=self._policy.version))
        return out

    def _kd_out_of_bounds(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        out = []
        for s in affinity:
            if not s.positive_control and s.kd_mean is not None:
                if not (self._policy.kd_plausible_min <= s.kd_mean <= self._policy.kd_plausible_max):
                    out.append(AnomalyFinding(
                        rule="kd_out_of_bounds", severity="warning",
                        evidence=(f"{_label(s)} kd_mean={s.kd_mean:.2e} {s.kd_units} outside plausible "
                                 f"range [{self._policy.kd_plausible_min:.2e}, {self._policy.kd_plausible_max:.2e}]"),
                        affected_ids=[_label(s)], policy_version=self._policy.version))
        return out

    def _missing_replicates(self, affinity: list[AffinityResultSummary]) -> list[AnomalyFinding]:
        out = []
        for s in affinity:
            if len(s.replicates) < self._policy.min_replicates:
                out.append(AnomalyFinding(
                    rule="missing_replicates", severity="warning",
                    evidence=f"{_label(s)} has {len(s.replicates)} replicate(s), policy requires "
                            f"{self._policy.min_replicates}",
                    affected_ids=[_label(s)], policy_version=self._policy.version))
        return out
