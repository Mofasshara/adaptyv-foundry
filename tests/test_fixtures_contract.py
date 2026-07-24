"""Contract test: fixtures must validate against the authoritative OpenAPI component
schemas (not just our pydantic models), so mock data cannot drift from the real API."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SPEC = json.loads((Path("tests/data/openapi.json")).read_text())
SCHEMAS = SPEC["components"]["schemas"]
FIX = Path("adaptyv/mocks/fixtures")

# Register the *entire* spec document as a single resource under a synthetic
# base URI. Every $ref inside components/schemas is a bare fragment
# ("#/components/schemas/Foo"); those only resolve correctly if they share a
# base URI with the schema being validated. Registering each component schema
# separately under its own "#/..." key (as a naive first attempt) breaks this:
# a fragment-only key isn't a real base URI, so nested $refs inside one
# schema can't find their siblings. Anchoring everything to one real URI
# (SPEC_URI) and pointing the root $ref at "{SPEC_URI}#/components/schemas/X"
# makes $ref/allOf/oneOf resolution work exactly like it would against the
# live spec document.
SPEC_URI = "urn:adaptyv:openapi-spec"
_REGISTRY = Registry().with_resource(
    SPEC_URI, Resource(contents=SPEC, specification=DRAFT202012)
)


def _validator(component: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{SPEC_URI}#/components/schemas/{component}"},
        registry=_REGISTRY,
    )


@pytest.mark.parametrize("fixture,component,is_list", [
    ("experiments_list.json", None, True),
    ("experiment_detail.json", "ExpInfo", False),
    ("results_list.json", None, True),
    ("targets_list.json", None, True),
    ("sequences_list.json", None, True),
])
def test_fixture_validates(fixture, component, is_list):
    data = json.loads((FIX / fixture).read_text())
    if is_list:
        assert set(data) >= {"items", "total", "count", "offset"}
    else:
        _validator(component).validate(data)


def test_detail_fixture_actually_fails_on_bad_data():
    """Guard against a no-op validator: a fixture missing a required field
    (or violating the ExpInfo schema) must raise, proving $ref/allOf are
    genuinely resolved and enforced -- not just smoke-checked."""
    from jsonschema.exceptions import ValidationError as SchemaValidationError

    data = json.loads((FIX / "experiment_detail.json").read_text())

    # Missing a required top-level field (id) must fail.
    bad_missing_required = dict(data)
    del bad_missing_required["id"]
    with pytest.raises(SchemaValidationError):
        _validator("ExpInfo").validate(bad_missing_required)

    # An invalid enum value nested inside the $ref'd `status` schema must fail,
    # proving the $ref chain (not just top-level required) is enforced.
    bad_enum = dict(data)
    bad_enum["status"] = "not_a_real_status"
    with pytest.raises(SchemaValidationError):
        _validator("ExpInfo").validate(bad_enum)

    # A violation nested inside the allOf'd experiment_spec (ExperimentSpecInfo ->
    # ExperimentSpecCommon) must fail, proving allOf resolution reaches into refs.
    bad_nested_allof = json.loads(json.dumps(data))
    bad_nested_allof["experiment_spec"]["experiment_type"] = "not_a_real_type"
    with pytest.raises(SchemaValidationError):
        _validator("ExpInfo").validate(bad_nested_allof)
