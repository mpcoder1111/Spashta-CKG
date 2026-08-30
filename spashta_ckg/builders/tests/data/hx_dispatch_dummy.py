"""Fixture for GENERIC inline HX-Trigger event dispatch (spec/fullstack-coupling-roadmap.md P3).

Bare string -> one event; comma-separated -> one per name; json.dumps(dict-literal) -> one per key;
a computed value -> an unresolved_hx_trigger ambiguity (never a guessed edge). No project helper involved.
"""

import json


def bare_event(resp):
    resp["HX-Trigger"] = "rvRefresh"
    return resp


def comma_events(resp):
    resp["HX-Trigger"] = "saved, closeDialog"
    return resp


def json_events(resp):
    resp["HX-Trigger"] = json.dumps({"showToast": {"level": "info"}, "openDialog": {}})
    return resp


def computed_event(resp, data):
    resp["HX-Trigger"] = json.dumps(data)  # non-literal -> ambiguity, no edge
    return resp
