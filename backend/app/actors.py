"""Seeded 'acting as' identities — the maker-checker mechanism without auth
(§11 G1). No login, no passwords: the UI lets the user pick who they're
acting as, and the approval gate enforces approver_id != author_id. Every
mutating action writes the chosen actor into audit_log.
"""
from __future__ import annotations

from typing import Dict, List

ACTORS: List[Dict[str, str]] = [
    {"id": "alice", "display_name": "Alice — Ops Analyst (maker)"},
    {"id": "bob", "display_name": "Bob — Ops Lead (checker)"},
    {"id": "carol", "display_name": "Carol — Ops Analyst (maker)"},
]

_VALID_IDS = {a["id"] for a in ACTORS}


def is_valid_actor(actor_id: str) -> bool:
    return actor_id in _VALID_IDS
