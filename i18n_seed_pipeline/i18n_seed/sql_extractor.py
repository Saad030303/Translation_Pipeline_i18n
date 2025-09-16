from __future__ import annotations
import re, json
from typing import Dict, List, Tuple, Any, Optional

from .config import SchemaHints
from .utils import strip_sql_quotes, is_likely_json_string


class ExtractedItem:
    def __init__(
        self,
        table: str,
        pk: Tuple[Any, ...] | None,
        column: str,
        value: str,
        row_idx: int,
        json_path: Optional[str] = None,
    ):
        self.table = table
        self.pk = pk
        self.column = column
        self.value = value
        self.row_idx = row_idx
        self.json_path = json_path

    def occurrence_key(self) -> str:
        pk_str = "|".join(map(str, self.pk)) if self.pk else f"row{self.row_idx}"
        jp = self.json_path or ""
        return f"{self.table}:{pk_str}:{self.column}:{jp}"


# ---------- robust SQL statement splitter (quote/comment/dollar aware) ----------

def _split_sql_statements(sql_text: str) -> List[str]:
    """
    Split SQL by semicolons that are OUTSIDE:
      - 'single-quoted strings' (with SQL '' escape)
      - "double-quoted identifiers"
      - -- line comments
      - /* block comments */
      - $tag$ ... $tag$ (PostgreSQL dollar-quoted strings)
    Keeps the ';' with each returned statement.
    """
    out, cur = [], []
    i, n = 0, len(sql_text)
    in_line = in_block = False
    in_dq = False
    dq_tag: Optional[str] = None  # dollar quote tag

    def starts_dollar_tag(pos: int) -> Optional[str]:
        if sql_text[pos] != '$':
            return None
        j = pos + 1
        while j < n and (sql_text[j].isalnum() or sql_text[j] == '_'):
            j += 1
        if j < n and sql_text[j] == '$':
            return sql_text[pos + 1 : j]  # '' for $$ or 'TAG' for $TAG$
        return None

    while i < n:
        c = sql_text[i]
        nxt = sql_text[i + 1] if i + 1 < n else ''

        # line comment
        if not (in_line or in_block or in_dq or dq_tag) and c == '-' and nxt == '-':
            in_line = True
            cur.append(c); cur.append(nxt); i += 2
            while i < n and sql_text[i] not in '\r\n':
                cur.append(sql_text[i]); i += 1
            continue

        # block comment
        if not (in_line or in_block or in_dq or dq_tag) and c == '/' and nxt == '*':
            in_block = True
            cur.append(c); cur.append(nxt); i += 2
            while i < n:
                if sql_text[i] == '*' and i + 1 < n and sql_text[i + 1] == '/':
                    cur.append('*'); cur.append('/'); i += 2; in_block = False; break
                cur.append(sql_text[i]); i += 1
            continue

        if in_line:
            cur.append(c); i += 1
            if c in '\r\n':
                in_line = False
            continue

        if in_block:
            cur.append(c); i += 1
            continue

        # dollar-quoted strings
        if not (in_dq or dq_tag) and c == '$':
            tag = starts_dollar_tag(i)
            if tag is not None:
                # copy opening $tag$
                j = i
                while j < n:
                    cur.append(sql_text[j])
                    if sql_text[j] == '$' and j != i:
                        break
                    j += 1
                i = j + 1
                dq_tag = tag
                continue

        if dq_tag is not None:
            if c == '$' and starts_dollar_tag(i) == dq_tag:
                # copy closing $tag$
                j = i
                while j < n:
                    cur.append(sql_text[j])
                    if sql_text[j] == '$' and j != i:
                        break
                    j += 1
                i = j + 1
                dq_tag = None
                continue
            cur.append(c); i += 1
            continue

        # single-quoted strings
        if c == "'":
            cur.append(c); i += 1
            while i < n:
                cur.append(sql_text[i])
                if sql_text[i] == "'":
                    if i + 1 < n and sql_text[i + 1] == "'":  # escaped ''
                        cur.append("'"); i += 2; continue
                    i += 1
                    break
                i += 1
            continue

        # double-quoted identifiers
        if c == '"':
            in_dq = True
            cur.append(c); i += 1
            while i < n:
                cur.append(sql_text[i])
                if sql_text[i] == '"':
                    in_dq = False; i += 1; break
                i += 1
            continue

        # terminator
        if c == ';' and not in_dq:
            cur.append(';')
            out.append("".join(cur))
            cur = []
            i += 1
            continue

        cur.append(c); i += 1

    tail = "".join(cur).strip()
    if tail:
        out.append("".join(cur))
    return out


# ---------- low-level helpers ----------

def _split_top_level_commas(s: str) -> List[str]:
    out, cur, q, i = [], [], None, 0
    while i < len(s):
        c = s[i]
        if q:
            cur.append(c)
            if c == q:
                q = None
            elif c == "'" and q == "'" and i + 1 < len(s) and s[i + 1] == "'":
                cur.append(s[i + 1]); i += 1
            i += 1; continue
        if c in ("'", '"'):
            q = c; cur.append(c); i += 1; continue
        if c == ",":
            out.append("".join(cur).strip()); cur = []; i += 1; continue
        cur.append(c); i += 1
    out.append("".join(cur).strip()); return out

def _strip_identifier_quotes(name: str) -> str:
    return name.strip().strip('"').strip("`").strip("[").strip("]")

def _split_values_groups(values_segment: str) -> List[str]:
    out = []; depth = 0; start = None; q = None; i = 0
    while i < len(values_segment):
        c = values_segment[i]
        if q:
            if c == q:
                q = None
            elif c == "'" and q == "'" and i + 1 < len(values_segment) and values_segment[i + 1] == "'":
                i += 1
            i += 1; continue
        if c in ("'", '"'):
            q = c; i += 1; continue
        if c == "(":
            if depth == 0: start = i
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(values_segment[start:i + 1]); start = None
        i += 1
    return out

def _parse_values_row(paren_group: str) -> List[str]:
    assert paren_group.startswith("(") and paren_group.endswith(")")
    inner = paren_group[1:-1]
    return _split_top_level_commas(inner)

def _norm_ident(name: str) -> str:
    return name.strip().strip('`"[]')


# -------- main INSERT parser: handles WITH and WITHOUT column list --------
def _parse_insert(stmt: str) -> Tuple[str, Optional[List[str]], List[List[str]]]:
    s = stmt.lstrip("\ufeff").strip().rstrip(";")
    m1 = re.match(r"INSERT\s+INTO\s+([^\s(]+)\s*\((.*?)\)\s*VALUES\s*(.*)$", s, flags=re.IGNORECASE | re.DOTALL)
    if m1:
        table = m1.group(1)
        cols_segment = m1.group(2)
        values_segment = m1.group(3)
        cols = [_strip_identifier_quotes(c) for c in _split_top_level_commas(cols_segment)]
        groups = _split_values_groups(values_segment)
        rows = [_parse_values_row(g) for g in groups]
        return table, cols, rows

    m2 = re.match(r"INSERT\s+INTO\s+([^\s(]+)\s*VALUES\s*(.*)$", s, flags=re.IGNORECASE | re.DOTALL)
    if m2:
        table = m2.group(1)
        values_segment = m2.group(2)
        groups = _split_values_groups(values_segment)
        rows = [_parse_values_row(g) for g in groups]
        return table, None, rows

    raise ValueError("Not an INSERT INTO ... VALUES statement")


class SqlExtractor:
    def __init__(
        self,
        schema_translatable: Dict[str, set],
        schema_pks: Dict[str, list],
        hints: SchemaHints | None = None,
        schema_columns_order: Dict[str, List[str]] | None = None,
    ):
        self.schema_translatable = schema_translatable
        self.schema_pks = schema_pks
        self.hints = hints or SchemaHints()
        self.schema_columns_order = schema_columns_order or {}

    def _extract_from_json(self, s: str, column: str) -> List[Tuple[str, str]]:
        try:
            obj = json.loads(s)
        except Exception:
            return []

        out: List[Tuple[str, str]] = []

        # --- NEW: handle root list for columns that are string-arrays (here: product_types)
        if isinstance(obj, list) and column == "product_types" and all(isinstance(x, str) for x in obj):
            for i, text in enumerate(obj):
                out.append((f"$[{i}]", text))
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

        for stmt in _split_sql_statements(sql_text):
            # remove BOM at the start of this statement (common after file concatenation)
            stmt = stmt.lstrip("\ufeff")
            stmt_norm = stmt.lstrip(" \t\r\n")
            if not stmt_norm.upper().startswith("INSERT"):
                continue
            try:
                table_raw, cols_opt, rows = _parse_insert(stmt)
            except Exception:
                continue

            t_norm = _norm_ident(table_raw)
            if t_norm not in self.schema_translatable:
                continue

            cols = cols_opt or self.schema_columns_order.get(t_norm) or []
            if not cols:
                # Cannot map VALUES(...) without a column order
                continue

            tcols = self.schema_translatable[t_norm]
            pks = self.schema_pks.get(t_norm, [])
            pk_idx = [cols.index(pk) for pk in pks if pk in cols]

            for r_i, row_vals in enumerate(rows, start=1):
                # Build PK tuple if possible
                pk_tuple: Optional[Tuple[Any, ...]] = None
                if pk_idx:
                    pk_vals: List[str] = []
                    for i in pk_idx:
                        if i < len(row_vals):
                            pk_vals.append(strip_sql_quotes(row_vals[i].strip()))
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
                        for jpath, txt in self._extract_from_json(val, col):
                            items.append(ExtractedItem(t_norm, pk_tuple, col, txt, r_i, jpath))
                    else:
                        items.append(ExtractedItem(t_norm, pk_tuple, col, val, r_i))

        return items
