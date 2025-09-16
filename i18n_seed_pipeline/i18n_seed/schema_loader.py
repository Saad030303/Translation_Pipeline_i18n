# import json
# from typing import Dict, Set, List
# from .config import SchemaHints

# try:
#     from .profiles import pick_profile
# except Exception:
#     pick_profile = None


# def _as_set(x) -> Set[str]:
#     """Robustly coerce lists/tuples/sets/None/str into a set[str]."""
#     if x is None:
#         return set()
#     if isinstance(x, set):
#         return x
#     if isinstance(x, (list, tuple)):
#         return set(x)
#     if isinstance(x, str):
#         return {x}
#     # unknown type: best effort
#     try:
#         return set(x)
#     except Exception:
#         return set()


# class SchemaLoader:
#     def __init__(self, schema_path: str, hints: SchemaHints | None = None) -> None:
#         self.schema_path = schema_path
#         # make sure hints fields we use behave like sets
#         self.schema_hints = hints or SchemaHints()
#         self.schema_hints.exact_skip_names = _as_set(getattr(self.schema_hints, "exact_skip_names", set()))
#         self.schema_hints.suffix_skip_names = _as_set(getattr(self.schema_hints, "suffix_skip_names", set()))
#         self.schema_hints.json_string_keys = _as_set(getattr(self.schema_hints, "json_string_keys", set()))
#         # text_types can remain list/tuple/set; we normalize to a set for fast membership
#         self.schema_hints.text_types = _as_set(getattr(self.schema_hints, "text_types", {"TEXT", "VARCHAR", "NVARCHAR", "CHAR", "CLOB", "JSON"}))

#         self.data = self._load()
#         self.profile = self._pick_and_merge_profile()

#     def _load(self) -> dict:
#         with open(self.schema_path, "r", encoding="utf-8") as f:
#             return json.load(f)

#     def _pick_and_merge_profile(self):
#         server_name = self.data.get("server_name") or self.data.get("mcp_server") or ""
#         table_names = set((self.data.get("complete_schema", {}) or {}).get("tables", {}).keys())

#         # choose profile (fallback to a minimal generic profile if profiles not wired yet)
#         if pick_profile is not None:
#             profile = pick_profile(server_name, table_names)
#         else:
#             class _Generic:
#                 id = "generic"
#                 placeholder_patterns = []
#                 json_string_keys = set()
#                 exact_skip_columns = set()
#                 suffix_skip_columns = set()
#                 system_rules = ""
#                 validators = []
#             profile = _Generic()

#         # MERGE: profile → schema_hints (coerce everything to sets before |=)
#         self.schema_hints.exact_skip_names = _as_set(self.schema_hints.exact_skip_names) | _as_set(
#             getattr(profile, "exact_skip_columns", set())
#         )
#         self.schema_hints.suffix_skip_names = _as_set(self.schema_hints.suffix_skip_names) | _as_set(
#             getattr(profile, "suffix_skip_columns", set())
#         )
#         self.schema_hints.json_string_keys = _as_set(self.schema_hints.json_string_keys) | _as_set(
#             getattr(profile, "json_string_keys", set())
#         )

#         # stash the selected profile for others to read (cli, placeholder locker, translator)
#         self.profile = profile
#         return profile

#     def translatable_columns(self) -> Dict[str, Set[str]]:
#         out: Dict[str, Set[str]] = {}
#         tables = (self.data.get("complete_schema", {}) or {}).get("tables", {}) or {}

#         exact_skips = {n.lower() for n in _as_set(self.schema_hints.exact_skip_names)}
#         suffix_skips = tuple(s.lower() for s in _as_set(self.schema_hints.suffix_skip_names))
#         text_types = {t.upper() for t in _as_set(self.schema_hints.text_types)}

#         for tname, tinfo in tables.items():
#             cols = (tinfo.get("columns", {}) or {})
#             chosen: Set[str] = set()
#             for cname, cinfo in cols.items():
#                 ctype = ((cinfo or {}).get("type") or "").upper()
#                 cn_l = cname.lower()

#                 if cn_l in exact_skips:
#                     continue
#                 if any(cn_l.endswith(suf) for suf in suffix_skips):
#                     continue
#                 if ctype in text_types:
#                     chosen.add(cname)

#             if chosen:
#                 out[tname] = chosen
#         return out

#     def primary_keys(self) -> Dict[str, List[str]]:
#         out: Dict[str, List[str]] = {}
#         tables = (self.data.get("complete_schema", {}) or {}).get("tables", {}) or {}
#         for tname, tinfo in tables.items():
#             out[tname] = list(tinfo.get("primary_keys") or [])
#         return out

#     def columns_order_map(self) -> Dict[str, List[str]]:
#         """
#         Returns the column declaration order for each table from the schema JSON.
#         This is necessary to map VALUES-only INSERTs to the correct columns.
#         """
#         order: Dict[str, List[str]] = {}
#         tables = (self.data.get("complete_schema", {}) or {}).get("tables", {}) or {}
#         for tname, tinfo in tables.items():
#             cols = (tinfo.get("columns", {}) or {})
#             order[tname] = list(cols.keys())  # JSON order preserved
#         return order

# i18n_seed/schema_loader.py
from __future__ import annotations
import json
from typing import Dict, Set, List
from .config import SchemaHints
from .profiles import pick_profile, DomainProfile

def _as_set(x) -> Set[str]:
    if x is None: return set()
    if isinstance(x, set): return x
    if isinstance(x, (list, tuple)): return set(x)
    if isinstance(x, str): return {x}
    try:
        return set(x)
    except Exception:
        return set()

class SchemaLoader:
    def __init__(self, schema_path: str, hints: SchemaHints | None = None) -> None:
        self.schema_path = schema_path
        self.schema_hints = hints or SchemaHints()
        # coerce to sets
        self.schema_hints.exact_skip_names = _as_set(self.schema_hints.exact_skip_names)
        self.schema_hints.suffix_skip_names = _as_set(self.schema_hints.suffix_skip_names)
        self.schema_hints.json_string_keys = _as_set(self.schema_hints.json_string_keys)
        self.schema_hints.text_types = _as_set(self.schema_hints.text_types)

        self.data = self._load()
        self.profile: DomainProfile = self._pick_and_merge_profile()

    def _load(self) -> dict:
        with open(self.schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _pick_and_merge_profile(self) -> DomainProfile:
        server_name = self.data.get("server_name") or self.data.get("mcp_server") or ""
        table_names = set((self.data.get("complete_schema", {}) or {}).get("tables", {}).keys())

        profile = pick_profile(server_name, table_names)

        # merge profile JSON keys into extractor/reinjector hints
        self.schema_hints.json_string_keys |= _as_set(profile.json_string_keys)
        # ensure product_type is NOT skipped
        self.schema_hints.exact_skip_names = _as_set(self.schema_hints.exact_skip_names) - {"product_type"}

        return profile

    def translatable_columns(self) -> Dict[str, Set[str]]:
        out: Dict[str, Set[str]] = {}
        tables = (self.data.get("complete_schema", {}) or {}).get("tables", {}) or {}

        exact_skips = {n.lower() for n in self.schema_hints.exact_skip_names}
        suffix_skips = tuple(s.lower() for s in self.schema_hints.suffix_skip_names)
        text_types = {t.upper() for t in self.schema_hints.text_types}

        for tname, tinfo in tables.items():
            cols = (tinfo.get("columns", {}) or {})
            chosen: Set[str] = set()

            force = self.profile.force_include_columns.get(tname, set())
            for cname, cinfo in cols.items():
                if cname in force:
                    chosen.add(cname)
                    continue

                ctype = ((cinfo or {}).get("type") or "").upper()
                cn_l = cname.lower()

                if cn_l in exact_skips: continue
                if any(cn_l.endswith(suf) for suf in suffix_skips): continue
                if ctype in text_types:
                    chosen.add(cname)

            if chosen:
                out[tname] = chosen
        return out

    def primary_keys(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        tables = (self.data.get("complete_schema", {}) or {}).get("tables", {}) or {}
        for tname, tinfo in tables.items():
            out[tname] = list(tinfo.get("primary_keys") or [])
        return out

    def columns_order_map(self) -> Dict[str, List[str]]:
        order: Dict[str, List[str]] = {}
        tables = (self.data.get("complete_schema", {}) or {}).get("tables", {}) or {}
        for tname, tinfo in tables.items():
            cols = (tinfo.get("columns", {}) or {})
            order[tname] = list(cols.keys())
        return order

    # legacy compatibility for callers
    def profile_from_schema(self) -> DomainProfile:
        return self.profile