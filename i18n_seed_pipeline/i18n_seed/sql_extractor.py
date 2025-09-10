from __future__ import annotations
import re, json
from typing import Dict, List, Tuple, Any, Optional

from .config import SchemaHints
from .utils import strip_sql_quotes, is_likely_json_string

class ExtractedItem:
    def __init__(self, table: str, pk: Tuple[Any, ...] | None, column: str, value: str, row_idx: int, json_path: Optional[str] = None):
        self.table = table
        self.pk = pk
        self.column = column
        self.value = value
        self.row_idx = row_idx
        self.json_path = json_path  # e.g., $.topic.value

    def occurrence_key(self) -> str:
        pk_str = "|".join(map(str, self.pk)) if self.pk else f"row{self.row_idx}"
        jp = self.json_path or ""
        return f"{self.table}:{pk_str}:{self.column}:{jp}"

# ---------- raw parsers (quote-aware) ----------

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
                # escaped single quote (SQL): ''
                cur.append(s[i + 1])
                i += 1
            i += 1
            continue
        if c in ("'", '"'):
            q = c
            cur.append(c)
            i += 1
            continue
        if c == ",":
            out.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur).strip())
    return out

def _strip_identifier_quotes(name: str) -> str:
    return name.strip().strip('"').strip("`").strip("[").strip("]")

def _parse_columns(cols_segment: str) -> List[str]:
    cols = _split_top_level_commas(cols_segment)
    return [_strip_identifier_quotes(c) for c in cols if c]

def _split_values_groups(values_segment: str) -> List[str]:
    """
    Split VALUES segment into top-level (...) groups.
    Example: "(...),(...),(...)" -> ["(...)", "(...)", "(...)"]
    """
    out = []
    depth = 0
    start = None
    q = None
    i = 0
    while i < len(values_segment):
        c = values_segment[i]
        if q:
            if c == q:
                q = None
            elif c == "'" and q == "'" and i + 1 < len(values_segment) and values_segment[i+1] == "'":
                i += 1  # skip escaped quote
            i += 1
            continue
        if c in ("'", '"'):
            q = c
            i += 1
            continue
        if c == "(":
            if depth == 0:
                start = i
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

def _parse_insert_statement(stmt: str) -> Tuple[str, List[str], List[List[str]]]:
    """
    Parse a single-row or multi-row INSERT:
    INSERT INTO <table> (<cols...>) VALUES (<vals...>),(<vals...>),...;
    Returns: (table, columns, list_of_rows)
    """
    s = stmt.strip().rstrip(";")
    m = re.match(r"INSERT\s+INTO\s+([^\s(]+)\s*\((.*?)\)\s*VALUES\s*(.*)$", s, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        raise ValueError("Not an INSERT INTO statement")

    table = m.group(1)
    cols_segment = m.group(2)
    values_segment = m.group(3)

    cols = _parse_columns(cols_segment)
    groups = _split_values_groups(values_segment)
    if not cols or not groups:
        raise ValueError("Failed to parse columns/values groups")

    rows = [_parse_values_row(g) for g in groups]
    return table, cols, rows

class SqlExtractor:
    def __init__(self, schema_translatable: Dict[str, set], schema_pks: Dict[str, list], hints: SchemaHints | None = None):
        self.schema_translatable = schema_translatable
        self.schema_pks = schema_pks
        self.hints = hints or SchemaHints()

    def _extract_from_json(self, s: str) -> List[Tuple[str, str]]:
        out = []
        try:
            obj = json.loads(s)
        except Exception:
            return out

        def walk(o, path="$"):
            if isinstance(o, dict):
                for k, v in o.items():
                    p = f"{path}.{k}"
                    if isinstance(v, str) and k in self.hints.json_string_keys:
                        out.append((p, v))
                    else:
                        walk(v, p)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")
        walk(obj)
        return out

    def extract(self, sql_text: str) -> List[ExtractedItem]:
        items: List[ExtractedItem] = []
        # Fast scan for INSERT INTO ... ; blocks
        for m in re.finditer(r"INSERT\s+INTO\s+[^\s(]+\s*\(.*?\)\s*VALUES\s*.*?;", sql_text, flags=re.IGNORECASE | re.DOTALL):
            block = m.group(0)
            try:
                table, cols, rows = _parse_insert_statement(block)
            except Exception:
                continue
            if table not in self.schema_translatable:
                continue

            tcols = self.schema_translatable[table]
            pks = self.schema_pks.get(table, [])
            pk_idx = [cols.index(pk) for pk in pks if pk in cols]
            for r_i, row_vals in enumerate(rows, start=1):
                # Build PK tuple (if possible)
                pk_tuple = None
                if pk_idx:
                    pk_vals = []
                    for i in pk_idx:
                        raw = row_vals[i].strip()
                        pk_vals.append(strip_sql_quotes(raw))
                    pk_tuple = tuple(pk_vals)

                for c_i, col in enumerate(cols):
                    if col not in tcols:
                        continue
                    if c_i >= len(row_vals):
                        continue
                    raw = row_vals[c_i].strip()
                    val = strip_sql_quotes(raw)
                    if not val:
                        continue
                    if is_likely_json_string(val):
                        for jpath, txt in self._extract_from_json(val):
                            items.append(ExtractedItem(table, pk_tuple, col, txt, r_i, jpath))
                    else:
                        items.append(ExtractedItem(table, pk_tuple, col, val, r_i))
        return items