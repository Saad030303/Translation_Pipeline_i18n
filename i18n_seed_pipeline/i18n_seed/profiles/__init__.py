# from typing import Set
# from .base import DomainProfile
# from .amazon import AmazonProfile
# from .slack import SlackProfile
# from .generic import GenericProfile

# ALL_PROFILES = [AmazonProfile, SlackProfile, GenericProfile]

# def pick_profile(server_name: str | None, table_names: Set[str]) -> DomainProfile:
#     server_name = server_name or ""
#     for p in ALL_PROFILES:
#         if p.matches(server_name, table_names):
#             return p
#     return GenericProfile

# __all__ = ["DomainProfile", "ALL_PROFILES", "pick_profile",
#            "AmazonProfile", "SlackProfile", "GenericProfile"]

# i18n_seed/profiles/__init__.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Set, List, Callable
import re

@dataclass
class DomainProfile:
    id: str
    # Placeholder regexes to lock before translation (profile-driven)
    placeholder_patterns: List[re.Pattern] = field(default_factory=list)
    # Extra rules injected into the translator’s system prompt (free text)
    system_rules: List[str] = field(default_factory=list)
    # Force-include certain columns as translatable even if names look technical
    force_include_columns: Dict[str, Set[str]] = field(default_factory=dict)
    # JSON keys to consider “translatable” (merged into SchemaHints.json_string_keys)
    json_string_keys: Set[str] = field(default_factory=set)
    # Locale-specific JSON overrides applied at reinjection time
    json_overrides_by_locale: Dict[str, List[dict]] = field(default_factory=dict)
    # Optional additional validators (callables)
    validators: List[Callable] = field(default_factory=list)

# Import concrete profiles
from .amazon import amazon_profile
from .slack import slack_profile

ALL_PROFILES: List[DomainProfile] = [
    amazon_profile(),
    slack_profile(),
    # add more here
]

def pick_profile(server_name: str, table_names: Set[str]) -> DomainProfile:
    # Simple heuristic: choose based on table names or server_name hints
    lnames = {t.lower() for t in table_names}
    if any(t.startswith("catalog_") or t in {"catalog_items", "listings_items", "orders"} for t in lnames):
        return amazon_profile()

    if any(t.startswith("slack_") or t in {"slack_users", "slack_messages"} for t in lnames):
        return slack_profile()

    # fallback to Amazon if seed resembles ecommerce
    if "amazon" in (server_name or "").lower():
        return amazon_profile()

    # last resort: generic-ish Amazon—easy to extend later
    return amazon_profile()