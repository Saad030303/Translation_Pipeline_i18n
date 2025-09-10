from __future__ import annotations
import re, json
from typing import Dict, List, Optional

from .utils import is_likely_json_string, sql_escape_single_quotes
from .config import SchemaHints

def _split_top_level_commas(s: str) -> List[str]:
    out, cur = [], []
    q = None  # quote char
    i = 0
    while i < len(s):
        c = s[i]
        if q:
            cur.append(c)
            if c == q:
                q = None
            elif c == "'" and q == "'" and i + 1 < len(s) and s[i + 1] == "'":
                # escaped single quote: ''
                cur.append(s[i + 1]); i += 1
            i += 1
            continue
        if c in ("'", '"'):
            q = c; cur.append(c); i += 1; continue
        if c == ",":
            out.append("".join(cur).strip()); cur = []; i += 1; continue
        cur.append(c); i += 1
    out.append("".join(cur).strip())
    return out

def _strip_identifier_quotes(name: str) -> str:
    return name.strip().strip('"').strip("`").strip("[").strip("]")

def _parse_columns(cols_segment: str) -> List[str]:
    cols = _split_top_level_commas(cols_segment)
    return [_strip_identifier_quotes(c) for c in cols if c]

def _split_values_groups(values_segment: str) -> List[str]:
    """Split VALUES into top-level (...) groups."""
    out: List[str] = []
    depth = 0; start = None; q = None; i = 0
    while i < len(values_segment):
        c = values_segment[i]
        if q:
            if c == q:
                q = None
            elif c == "'" and q == "'" and i + 1 < len(values_segment) and values_segment[i+1] == "'":
                i += 1  # skip escaped
            i += 1; continue
        if c in ("'", '"'):
            q = c; i += 1; continue
        if c == "(":
            if depth == 0: start = i
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(values_segment[start:i+1])
                start = None
        i += 1
    return out

def _parse_values_row(paren_group: str) -> List[str]:
    assert paren_group.startswith("(") and paren_group.endswith(")")
    inner = paren_group[1:-1]
    return _split_top_level_commas(inner)

def _strip_sql_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return s

def strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    return s

class SqlReinjector:
    """
    Rebuild INSERT statements by replacing only translatable columns' values
    with localized equivalents.

    translations: occurrence_key -> translated SQL literal (ALREADY quoted/escaped)
      e.g. plain: "slack_apps:app_001:description:" ->  'Application de démonstration'
           JSON : "slack_apps:app_001:metadata:$.title" -> 'Titre localisé'
    """
    def __init__(self, schema_translatable: Dict[str, set], schema_pks: Dict[str, List[str]], hints: SchemaHints | None = None):
        self.schema_translatable = schema_translatable
        self.schema_pks = schema_pks
        self.hints = hints or SchemaHints()

    def _inject_into_json(self, s: str, json_map: Dict[str, str]) -> str:
        obj = json.loads(s)
        def walk(o, path: str = "$"):
            if isinstance(o, dict):
                for k, v in o.items():
                    p = f"{path}.{k}"
                    if isinstance(v, str) and k in self.hints.json_string_keys:
                        if p in json_map:
                            o[k] = json_map[p]
                    else:
                        walk(v, p)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")
        walk(obj)
        return json.dumps(obj, ensure_ascii=False)

    def reinject(self, sql_text: str, translations: Dict[str, str]) -> str:
        pieces: List[str] = []
        pos = 0
        # Scan all INSERT blocks
        for m in re.finditer(r"INSERT\s+INTO\s+([^\s(]+)\s*\((.*?)\)\s*VALUES\s*(.*?);", sql_text, flags=re.IGNORECASE | re.DOTALL):
            start, end = m.span()
            # keep the text before this INSERT
            if start > pos:
                pieces.append(sql_text[pos:start])

            table = m.group(1)
            cols_segment = m.group(2)
            values_segment = m.group(3)

            # If table has no translatable columns, keep block unchanged
            if table not in self.schema_translatable:
                pieces.append(sql_text[start:end])
                pos = end
                continue

            cols = _parse_columns(cols_segment)
            groups = _split_values_groups(values_segment)
            if not cols or not groups:
                pieces.append(sql_text[start:end])
                pos = end
                continue

            tcols = self.schema_translatable[table]
            pks = self.schema_pks.get(table, [])
            pk_idx = [cols.index(pk) for pk in pks if pk in cols]

            rebuilt_rows: List[str] = []
            for row_idx, g in enumerate(groups, start=1):
                row_vals = _parse_values_row(g)

                # Build row id (PK joined by |) or rowN
                if pk_idx:
                    pk_vals = []
                    for i in pk_idx:
                        if i < len(row_vals):
                            pk_vals.append(_strip_sql_quotes(row_vals[i]))
                    row_id = "|".join(pk_vals)
                else:
                    row_id = f"row{row_idx}"

                new_vals: List[str] = []
                for c_i, raw in enumerate(row_vals):
                    col = cols[c_i] if c_i < len(cols) else ""
                    val = raw.strip()

                    if col in tcols:
                        base_key = f"{table}:{row_id}:{col}:"
                        # Unquoted content for JSON detection
                        unq = _strip_sql_quotes(val)

                        if is_likely_json_string(unq):
                            # Collect json-path replacements for this base key
                            bucket = {k[len(base_key):]: v
                                      for k, v in translations.items()
                                      if k.startswith(base_key) and k != base_key}
                            if bucket:
                                json_repl_map = {jp: strip_quotes(v) for jp, v in bucket.items()}
                                new_json = self._inject_into_json(unq, json_repl_map)
                                new_vals.append("'" + sql_escape_single_quotes(new_json) + "'")
                            else:
                                new_vals.append(val)
                        else:
                            # Plain string: use the translated literal if present
                            new_vals.append(translations.get(base_key, val))
                    else:
                        new_vals.append(val)

                rebuilt_rows.append("(" + ", ".join(new_vals) + ")")

            # Rebuild INSERT
            cols_out = ", ".join([f'"{c}"' for c in cols])
            rebuilt = f'INSERT INTO {table} ({cols_out}) VALUES ' + ", ".join(rebuilt_rows) + ";"
            pieces.append(rebuilt)

            pos = end

        # Append any trailing text after the last INSERT
        pieces.append(sql_text[pos:])
        return "".join(pieces)
