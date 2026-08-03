"""Policy store adapters (OSS-003 work plan item 4).

Storage is an adapter interface — the core never hard-codes infrastructure.
Ships an in-memory store (tests/examples) and a file store (local Community
use). Database-backed stores live in separate packages.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional, Protocol


class PolicyStore(Protocol):
    def get_policy(self, policy_id: str) -> Optional[dict]: ...
    def put_policy(self, policy_id: str, policy: dict) -> None: ...
    def list_policies(self) -> list: ...


class InMemoryPolicyStore:
    def __init__(self):
        self._policies = {}

    def get_policy(self, policy_id: str) -> Optional[dict]:
        return self._policies.get(policy_id)

    def put_policy(self, policy_id: str, policy: dict) -> None:
        self._policies[policy_id] = dict(policy)

    def list_policies(self) -> list:
        return sorted(self._policies)


_SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


class FilePolicyStore:
    """One JSON file per policy under a root directory."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, policy_id: str) -> str:
        if not _SAFE_ID.match(policy_id or ''):
            raise ValueError(f'invalid policy id: {policy_id!r}')
        return os.path.join(self.root, f'{policy_id}.json')

    def get_policy(self, policy_id: str) -> Optional[dict]:
        path = self._path(policy_id)
        if not os.path.isfile(path):
            return None
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None

    def put_policy(self, policy_id: str, policy: dict) -> None:
        path = self._path(policy_id)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(policy, f, indent=2, sort_keys=True)
        os.replace(tmp, path)

    def list_policies(self) -> list:
        return sorted(f[:-5] for f in os.listdir(self.root) if f.endswith('.json'))
