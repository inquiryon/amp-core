"""v0 contract schema access and validation helpers.

Validation uses ``jsonschema`` when installed (the ``schema`` extra); the
core itself stays dependency-free and degrades to structural spot checks.
"""

from __future__ import annotations

import json
import os
from typing import Optional

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'contracts', 'schemas', 'v0.json')
_cache: Optional[dict] = None


def load_contracts() -> dict:
    global _cache
    if _cache is None:
        with open(_SCHEMA_PATH, encoding='utf-8') as f:
            _cache = json.load(f)
    return _cache


def validate(instance: dict, definition: str) -> list:
    """Validate ``instance`` against a ``$defs`` entry (e.g. ``Policy``).

    Returns a list of error strings; empty means valid. Raises KeyError for
    an unknown definition name.
    """
    contracts = load_contracts()
    subschema = contracts['$defs'][definition]
    try:
        import jsonschema
    except ImportError:
        return _minimal_check(instance, subschema)
    schema = {**subschema, '$defs': contracts['$defs']}
    validator = jsonschema.Draft202012Validator(schema)
    return [f'{"/".join(map(str, e.path)) or "<root>"}: {e.message}'
            for e in validator.iter_errors(instance)]


def _minimal_check(instance, subschema) -> list:
    errors = []
    if subschema.get('type') == 'object' and not isinstance(instance, dict):
        return [f'<root>: expected object, got {type(instance).__name__}']
    for key in subschema.get('required', []):
        if key not in instance:
            errors.append(f'{key}: required property missing')
    return errors
