from dataclasses import dataclass, field
from typing import Callable, Dict, List, Set, Pattern

@dataclass
class DomainProfile:
    id: str
    server_name_contains: List[str] = field(default_factory=list)
    table_name_contains: List[str] = field(default_factory=list)

    placeholder_patterns: List[Pattern] = field(default_factory=list)
    json_string_keys: Set[str] = field(default_factory=set)
    exact_skip_columns: Set[str] = field(default_factory=set)
    suffix_skip_columns: Set[str] = field(default_factory=set)

    system_rules: str = ""     # injected into LLM prompt
    validators: List[Callable[[str, str, str], list]] = field(default_factory=list)

    def matches(self, server_name: str, table_names: Set[str]) -> bool:
        if any(s in (server_name or "") for s in self.server_name_contains):
            return True
        return any(any(s in t for s in self.table_name_contains) for t in table_names)