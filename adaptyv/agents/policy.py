from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AnomalyPolicy(BaseModel):
    """Versioned, explicit thresholds for anomaly detection — an input, not a
    hardcoded constant, because the OpenAPI result schema carries no
    authoritative 'expected range' for a positive control or a plausible Kd."""
    model_config = ConfigDict(extra="forbid")

    version: str
    positive_control_kd_min: float
    positive_control_kd_max: float
    kd_plausible_min: float
    kd_plausible_max: float
    min_replicates: int


# v0 rationale: Kd is in molar units. Typical antibody/binder affinities span
# ~1pM-1uM; a positive control (a known-good binder) is expected tighter,
# ~10pM-100nM. min_replicates=2 is the minimum for any statistical confidence.
DEFAULT_POLICY = AnomalyPolicy(
    version="v0",
    positive_control_kd_min=1e-11,
    positive_control_kd_max=1e-7,
    kd_plausible_min=1e-12,
    kd_plausible_max=1e-6,
    min_replicates=2,
)
