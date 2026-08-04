"""The shipped JSON Schema stays structurally in sync with the model.

No jsonschema dependency (the core ships pyyaml only): these are structural
assertions that the schema names exactly the enums and keys the model defines.
Editors do the actual on-save validation.
"""

import json

import yaml

from graphspec import model
from graphspec.parser import NODE_KEYS, EDGE_KEYS, STATE_KEYS, TOP_KEYS

SCHEMA_PATH = "schema/graphspec.schema.json"


def _schema():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_schema_is_valid_json_with_expected_dialect():
    s = _schema()
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert s["properties"]["graphspec"]["const"] == 1


def test_schema_enums_match_model():
    s = _schema()
    defs = s["$defs"]
    assert set(defs["node"]["properties"]["kind"]["enum"]) == model.KINDS
    assert set(defs["substrate"]["enum"]) == model.SUBSTRATES
    assert set(defs["stateField"]["properties"]["type"]["enum"]) == model.STATE_TYPES
    assert set(defs["node"]["properties"]["join"]["enum"]) == model.JOINS
    assert set(defs["node"]["properties"]["effects"]["enum"]) == model.EFFECTS


def test_schema_keys_match_parser_known_keys():
    s = _schema()
    defs = s["$defs"]
    assert set(s["properties"]) == TOP_KEYS
    assert set(defs["node"]["properties"]) == NODE_KEYS
    assert set(defs["edge"]["properties"]) == EDGE_KEYS
    assert set(defs["stateField"]["properties"]) == STATE_KEYS


def test_schema_stays_extensible():
    s = _schema()
    assert s["additionalProperties"] is True
    assert s["$defs"]["node"]["additionalProperties"] is True


def test_reference_example_satisfies_required_structure():
    with open("examples/software-delivery.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    for key in _schema()["required"]:
        assert key in data
