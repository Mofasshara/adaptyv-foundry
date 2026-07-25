import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from adaptyv.models import CreateExpRequest, CostEstimateRequest, ExperimentSpec, SequenceInput

SPEC = json.loads(Path("tests/data/openapi.json").read_text())
SPEC_URI = "urn:adaptyv:openapi-spec"
_REGISTRY = Registry().with_resource(SPEC_URI, Resource(contents=SPEC, specification=DRAFT202012))


def _validator(component: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"{SPEC_URI}#/components/schemas/{component}"},
                                registry=_REGISTRY)


def _spec():
    return ExperimentSpec(
        experiment_type="affinity",
        method="bli",
        target_id="44444444-0000-0000-0000-000000000001",
        n_replicates=3,
        sequences={
            "binder-1": SequenceInput(aa_string="MKAA", control=False),
            "control-1": "MKAAQQ",
        },
    )


def test_create_request_sequences_serializes_as_object_not_array():
    body = CreateExpRequest(name="My run", experiment_spec=_spec()).model_dump(exclude_none=True)
    assert isinstance(body["experiment_spec"]["sequences"], dict)
    assert body["experiment_spec"]["sequences"]["binder-1"] == {"aa_string": "MKAA", "control": False}
    assert body["experiment_spec"]["sequences"]["control-1"] == "MKAAQQ"


def test_create_request_body_validates_against_real_openapi_schema():
    body = CreateExpRequest(name="My run", experiment_spec=_spec()).model_dump(exclude_none=True)
    _validator("CreateExpRequest").validate(body)


def test_cost_estimate_request_body_validates_against_real_openapi_schema():
    body = CostEstimateRequest(experiment_spec=_spec()).model_dump(exclude_none=True)
    _validator("CostEstimateRequest").validate(body)
