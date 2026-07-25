from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class _R(BaseModel):
    """Base for response models: tolerate unknown/added fields."""
    model_config = ConfigDict(extra="ignore")


class _Req(BaseModel):
    """Base for request models: strict."""
    model_config = ConfigDict(extra="forbid")


class ExperimentStatus(str, Enum):
    DRAFT = "draft"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    CANCELED = "canceled"
    WAITING_FOR_MATERIALS = "waiting_for_materials"
    IN_PRODUCTION = "in_production"
    QUOTE_SENT = "quote_sent"
    IN_QUEUE = "in_queue"
    DATA_ANALYSIS = "data_analysis"
    IN_REVIEW = "in_review"
    DONE = "done"


class ResultsStatus(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    ALL = "all"


class ExperimentType(str, Enum):
    AFFINITY = "affinity"
    SCREENING = "screening"
    THERMOSTABILITY = "thermostability"
    FLUORESCENCE = "fluorescence"
    EXPRESSION = "expression"
    EPITOPE_BINNING = "epitope_binning"
    ENZYME_ACTIVITY = "enzyme_activity"


class Method(str, Enum):
    BLI = "bli"
    SPR = "spr"


class SequenceType(str, Enum):
    SCFV = "ScFv"
    FAB = "FAB"
    SINGLE_CHAIN = "SingleChain"
    IGG = "IgG"


class Page(_R, Generic[T]):
    items: list[T]
    total: int
    count: int
    offset: int


# ---- result cluster ----
class KineticInterval(_R):
    value: float
    ci_low: float | None = None
    ci_high: float | None = None


class AffinityReplicate(_R):
    replicate: int
    binding: str | None = None
    binding_strength: str | None = None
    confidence: str | None = None
    expression: str | None = None
    fit_quality: str | None = None
    kd: float | None = None
    kd_app: KineticInterval | None = None
    koff: float | None = None
    koff_1to1: KineticInterval | None = None
    koff_method: str | None = None
    kon: float | None = None
    kon_1to1: KineticInterval | None = None
    kon_method: str | None = None
    method: str | None = None
    rmse_max_signal_pct: float | None = None


class SequenceEntry(_R):
    aa_string: str
    control: bool | None = None
    metadata: dict[str, Any] | None = None
    name: str | None = None


class SequenceInput(_R):
    aa_string: str
    control: bool | None = None
    metadata: dict[str, Any] | None = None


class TargetReference(_R):
    name: str
    sequence: str | None = None
    supplier_url: str | None = None
    target_catalog_id: str | None = None


class AffinityResult(_R):
    sequence: SequenceEntry
    kd_units: str
    binding_strength: str
    positive_control: bool
    performance: dict[str, Any]
    replicates: list[AffinityReplicate] = Field(default_factory=list)
    binding: str | None = None
    binding_model: list[str] | None = None
    expression: str | None = None
    fit_quality: str | None = None
    method: list[str] | None = None
    place: int | None = None
    target: TargetReference | None = None
    kd_mean: float | None = None
    kd_log_std: float | None = None
    kd_app: KineticInterval | None = None
    kon_mean: float | None = None
    kon_log_std: float | None = None
    kon_1to1: KineticInterval | None = None
    koff_mean: float | None = None
    koff_log_std: float | None = None
    koff_1to1: KineticInterval | None = None
    concentration_value: float | None = None
    concentration_display: str | None = None


class ThermostabilityResult(_R):
    sequence_id: str
    inflection_pts_for_ratio: list[float]
    onset_pts_for_ratio: list[float]
    bli_result_id: str | None = None
    initial_330nm: float | None = None
    sequence: str | None = None
    sequence_name: str | None = None
    tm: float | None = None


class AffinityResultSummary(AffinityResult):
    result_type: Literal["affinity"]


class ThermostabilityResultSummary(ThermostabilityResult):
    result_type: Literal["thermostability"]


ResultSummary = Annotated[
    Union[AffinityResultSummary, ThermostabilityResultSummary],
    Field(discriminator="result_type"),
]


class ResultInfo(_R):
    id: str
    title: str
    experiment_id: str
    result_type: str
    created_at: datetime
    summary: list[ResultSummary]
    metadata: dict[str, Any]
    data_package_url: str | None = None


# ---- experiments ----
class ExperimentSpecInfo(_R):
    experiment_type: ExperimentType
    target: TargetReference | None = None
    # other spec fields (method, replicates, sequences...) tolerated via extra="ignore"


class ExpInfo(_R):
    id: str
    code: str
    status: ExperimentStatus
    results_status: ResultsStatus
    created_at: datetime
    experiment_url: str
    experiment_spec: ExperimentSpecInfo
    name: str | None = None
    costs: dict[str, Any] | None = None
    stripe_quote_id: str | None = None
    stripe_quote_url: str | None = None
    stripe_invoice_url: str | None = None


class ExperimentListItem(_R):
    id: str
    code: str
    status: ExperimentStatus
    results_status: ResultsStatus
    created_at: datetime
    experiment_url: str
    experiment_type: ExperimentType | None = None
    name: str | None = None
    stripe_quote_url: str | None = None
    stripe_invoice_url: str | None = None


# ---- sequences ----
class SequenceExperimentRef(_R):
    experiment_id: str
    experiment_code: str
    experiment_status: str | None = None


class SequenceInfo(_R):
    id: str
    length: int
    is_control: bool
    created_at: datetime
    experiment: SequenceExperimentRef
    aa_string: str | None = None
    name: str | None = None
    metadata: dict[str, Any] | None = None


class SequenceListItem(_R):
    id: str
    length: int
    experiment_id: str
    experiment_code: str
    is_control: bool
    created_at: datetime
    name: str | None = None
    aa_preview: str | None = None


class SequenceAddRequest(_Req):
    experiment_code: str
    sequences: list[SequenceEntry]


class SequenceAddResponse(_R):
    experiment_id: str
    experiment_code: str
    added_count: int
    sequence_ids: list[str]


# ---- targets ----
class TargetInfo(_R):
    id: str
    name: str
    vendor_name: str
    catalog_number: str
    url: str
    uniprot_id: str | None = None
    pricing: dict[str, Any] | None = None
    details: dict[str, Any] | None = None


# ---- create / estimate ----
# Real Foundry API assay matrix (OpenAPI ExperimentSpec description): required
# fields differ by experiment type, and violating them is a 400 listing every
# problem. Enforcing this here means mock mode rejects exactly what live mode
# would reject, instead of silently accepting an invalid spec.
_BINDING_TYPES = frozenset({ExperimentType.AFFINITY, ExperimentType.SCREENING})
_TARGET_REQUIRED = _BINDING_TYPES | {ExperimentType.EPITOPE_BINNING}


class ExperimentSpec(_Req):
    experiment_type: ExperimentType
    sequences: dict[str, str | SequenceInput] = Field(default_factory=dict)
    target_id: str | None = None
    method: Method | None = None
    n_replicates: int | None = None
    antigen_concentrations: list[float] | None = None
    parameters: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _check_assay_matrix(self) -> "ExperimentSpec":
        et = self.experiment_type
        problems: list[str] = []
        if et in _BINDING_TYPES and self.method is None:
            problems.append(f"method is required for {et.value}")
        if et not in _BINDING_TYPES and self.method is not None:
            problems.append(f"method must not be set for {et.value}")
        if et in _TARGET_REQUIRED and self.target_id is None:
            problems.append(f"target_id is required for {et.value}")
        if et not in _TARGET_REQUIRED and self.target_id is not None:
            problems.append(f"target_id must not be set for {et.value}")
        if not self.sequences:
            problems.append("at least one sequence is required")
        if et is ExperimentType.EPITOPE_BINNING:
            n = len(self.sequences)
            if n % 4 != 0 or not (4 <= n <= 28):
                problems.append("epitope_binning requires a multiple of 4 sequences, between 4 and 28")
            if self.n_replicates is not None:
                problems.append("n_replicates must not be set for epitope_binning")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class CreateExpRequest(_Req):
    name: str
    experiment_spec: ExperimentSpec
    skip_draft: bool | None = None
    auto_accept_quote: bool | None = None
    webhook_url: str | None = None


class CreateExpResponse(_R):
    experiment_id: str
    error: str | None = None
    stripe_invoice_id: str | None = None
    stripe_hosted_invoice_url: str | None = None


class CostEstimateRequest(_Req):
    experiment_spec: ExperimentSpec


class AssayCost(_R):
    experiment_type: str
    sequence_count: int
    n_replicates: int
    unit_price_cents: int
    replicate_price_cents: int
    subtotal_cents: int


class CostBreakdown(_R):
    pricing_version: str
    assay: AssayCost
    total_cents: int
    materials: Any | None = None


class CostEstimateResponse(_R):
    breakdown: CostBreakdown | None = None
    incomplete: Any | None = None
    warnings: list[str] | None = None


class ExperimentConfirmationResponse(_R):
    experiment_id: str
    previous_status: ExperimentStatus
    status: ExperimentStatus
    confirmed_at: str
    stripe_invoice_url: str | None = None


class ErrorResponse(_R):
    error: str
    request_id: str


class WhoAmIResponse(_R):
    user_id: str
    organizations: list[dict[str, Any]]
    capabilities: list[str]
    expires_at: datetime | None = None
