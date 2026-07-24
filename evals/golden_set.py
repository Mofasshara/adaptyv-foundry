from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenCase:
    """A real mock-fixture experiment plus what a correct agent run over it
    must produce. Anchored to adaptyv/mocks/fixtures/*.json — not synthetic
    data — so the eval suite regresses against the same demo data a reviewer
    sees."""
    name: str
    experiment_id: str
    expected_critical_rules: frozenset[str]
    expected_fact_keys: frozenset[str]


GOLDEN_SET: list[GoldenCase] = [
    GoldenCase(
        name="healthy_affinity_panel",
        experiment_id="11111111-1111-1111-1111-111111111111",  # EXP-1001
        expected_critical_rules=frozenset(),
        expected_fact_keys=frozenset({"kd_mean_binder-1", "kd_mean_pos-control"}),
    ),
    GoldenCase(
        name="all_sequences_failed",
        experiment_id="33333333-3333-3333-3333-333333333333",  # EXP-1003
        expected_critical_rules=frozenset({"all_sequences_failed"}),
        expected_fact_keys=frozenset(),
    ),
    GoldenCase(
        name="control_out_of_range",
        experiment_id="44444444-4444-4444-4444-444444444444",  # EXP-1004
        expected_critical_rules=frozenset({"control_out_of_policy"}),
        expected_fact_keys=frozenset({"kd_mean_binder-5", "kd_mean_pos-control"}),
    ),
]
