import json
from typing import Dict, Set
from .config import SchemaHints

class SchemaLoader:
    def __init__(self, schema_path: str, hints: SchemaHints | None = None) -> None:
        self.schema_path = schema_path
        self.hints = hints or SchemaHints()
        self.data = self._load()

    def _load(self) -> dict:
        with open(self.schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def translatable_columns(self) -> Dict[str, Set[str]]:
        out: Dict[str, Set[str]] = {}
        tables = self.data.get("complete_schema", {}).get("tables", {})
        for tname, tinfo in tables.items():
            cols = tinfo.get("columns", {})
            chosen: Set[str] = set()
            for cname, cinfo in cols.items():
                ctype = (cinfo.get("type") or "").upper()
                cn = cname.lower()

                # NEW: exact + suffix skip (no substring matches)
                if cn in {n.lower() for n in self.hints.exact_skip_names}:
                    continue
                if any(cn.endswith(suf.lower()) for suf in self.hints.suffix_skip_names):
                    continue

                # Include text-like columns
                if ctype in self.hints.text_types:
                    chosen.add(cname)

            if chosen:
                out[tname] = chosen
        return out

    def primary_keys(self) -> Dict[str, list]:
        out = {}
        tables = self.data.get("complete_schema", {}).get("tables", {})
        for tname, tinfo in tables.items():
            pks = tinfo.get("primary_keys") or []
            out[tname] = pks
        return out
