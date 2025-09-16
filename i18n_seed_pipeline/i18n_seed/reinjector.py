from __future__ import annotations
import re, json, logging, random, hashlib, os
from typing import Dict, List, Optional, Tuple, Any

from .utils import is_likely_json_string, sql_escape_single_quotes
from .config import SchemaHints

# Try to import address pools from the amazon profile if present
try:
    from .profiles.amazon import BUILTIN_ADDRESS_POOLS as _BUILTIN_ADDRESS_POOLS  # type: ignore
except Exception:
    try:
        from .profiles.amazon import _BUILTIN_ADDRESS_POOLS as _BUILTIN_ADDRESS_POOLS  # type: ignore
    except Exception:
        _BUILTIN_ADDRESS_POOLS = None

# --- statement splitting that ignores semicolons inside quotes ---
def _iter_insert_blocks(sql_text: str):
    """
    Yields (start, end) spans for each INSERT statement.
    Stops only at a semicolon that is NOT inside a quoted string.
    Handles doubled single quotes '' inside strings.
    """
    pat = re.compile(r"INSERT\s+INTO", re.IGNORECASE)
    pos = 0
    n = len(sql_text)
    while True:
        m = pat.search(sql_text, pos)
        if not m:
            break
        start = m.start()
        i = m.end()
        q = None  # current quote char, if any
        while i < n:
            c = sql_text[i]
            if q:
                if c == q:
                    # doubled single-quote escape
                    if q == "'" and i + 1 < n and sql_text[i + 1] == "'":
                        i += 2
                        continue
                    q = None
                    i += 1
                    continue
                i += 1
                continue
            else:
                if c in ("'", '"'):
                    q = c
                    i += 1
                    continue
                if c == ";":
                    yield (start, i + 1)
                    pos = i + 1
                    break
                i += 1
        else:
            # no semicolon found; yield to end
            yield (start, n)
            break


def _json_lenient_loads(s: str):
    """
    Try strict JSON; if that fails, try Python-literal (handles True/False/None).
    Return dict/list or None if unparseable.
    """
    try:
        return json.loads(s)
    except Exception:
        try:
            import ast
            obj = ast.literal_eval(s)
            if isinstance(obj, (dict, list)):
                return obj
        except Exception:
            pass
    return None


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
    return _split_top_level_commas(paren_group[1:-1])

def _parse_insert(stmt: str):
    s = stmt.lstrip("\ufeff").strip().rstrip(";")
    m1 = re.match(r"INSERT\s+INTO\s+([^\s(]+)\s*\((.*?)\)\s*VALUES\s*(.*)$",
                  s, flags=re.IGNORECASE | re.DOTALL)
    if m1:
        table = m1.group(1); cols_segment = m1.group(2); values_segment = m1.group(3)
        cols = [c.strip().strip('`"[]') for c in _split_top_level_commas(cols_segment)]
        groups = _split_values_groups(values_segment)
        rows = [_parse_values_row(g) for g in groups]
        return table, cols, rows, True

    m2 = re.match(r"INSERT\s+INTO\s+([^\s(]+)\s*VALUES\s*(.*)$",
                  s, flags=re.IGNORECASE | re.DOTALL)
    if m2:
        table = m2.group(1); values_segment = m2.group(2)
        groups = _split_values_groups(values_segment)
        rows = [_parse_values_row(g) for g in groups]
        return table, None, rows, False

    return None, None, None, None

def _strip_sql_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return s

def strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    return s

def _norm_ident(name: str) -> str:
    return name.strip().strip('`"[]')


# ---------- key lookup + translation helpers ----------

def _key_candidates(table_raw: str, row_id: str, row_idx: int, col: str) -> List[str]:
    t_raw = table_raw
    t_norm = _norm_ident(table_raw)
    col_l = col.lower()
    return [
        f"{t_raw}:{row_id}:{col}:",
        f"{t_norm}:{row_id}:{col}:",
        f"{t_raw}:{row_id}:{col_l}:",
        f"{t_norm}:{row_id}:{col_l}:",
        f"{t_raw}:row{row_idx}:{col}:",
        f"{t_norm}:row{row_idx}:{col}:",
        f"{t_raw}:row{row_idx}:{col_l}:",
        f"{t_norm}:row{row_idx}:{col_l}:",
    ]

def _lookup_scalar_translation(cands: List[str], translations: Dict[str, str]) -> Optional[str]:
    for k in cands:
        if k in translations:
            return translations[k]
    return None

def _collect_json_replacements(cands: List[str], translations: Dict[str, str]) -> Dict[str, str]:
    bucket: Dict[str, str] = {}
    for p in cands:
        for k, v in translations.items():
            if k.startswith(p) and k != p:
                bucket[k[len(p):]] = v
    return bucket


# ---------- JSON override utilities (unchanged behavior) ----------

def _json_path_to_keys(jp: str) -> List[str]:
    if not jp or not jp.startswith("$.."):
        return []
    tail = jp[3:]
    return [seg for seg in tail.split(".") if seg]

def _deep_visit(obj: Any, fn):
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            fn(obj, k, v)
            _deep_visit(v, fn)
    elif isinstance(obj, list):
        for it in list(obj):
            _deep_visit(it, fn)


# ---------- alias-aware generic keys ----------

_GENERIC_ALIASES: Dict[str, List[str]] = {
    "currency_code": ["currency_code", "currencyCode", "CurrencyCode"],
    "marketplace_ids": ["marketplace_ids", "marketplaceIds"],
}

def _alias_keys_for(key: str) -> List[str]:
    return _GENERIC_ALIASES.get(key, [key])

def _set_any_depth_key(obj: Any, key: str, new_value: Any) -> int:
    changed = 0
    aliases = set(_alias_keys_for(key))
    def setter(parent, k, v):
        nonlocal changed
        if k in aliases and parent.get(k) != new_value:
            parent[k] = new_value
            changed += 1
    _deep_visit(obj, setter)
    return changed

def _set_value_at_path_any_depth(obj: Any, path_keys: List[str], new_value: Any) -> int:
    changed = 0
    def walk(node: Any, keys: List[str]):
        nonlocal changed
        if not isinstance(node, (dict, list)):
            return
        if isinstance(node, dict):
            if keys:
                if len(keys) == 1:
                    for k in list(node.keys()):
                        if k in _alias_keys_for(keys[0]) and node.get(k) != new_value:
                            node[k] = new_value
                            changed += 1
                else:
                    first = keys[0]
                    if first in node:
                        walk(node.get(first), keys[1:])
            for v in node.values():
                walk(v, keys)
        else:
            for it in node:
                walk(it, keys)
    walk(obj, path_keys)
    return changed

def _replace_array_at_path_any_depth(obj: Any, path_keys: List[str], old_arr: List[Any], new_arr: List[Any]) -> int:
    changed = 0
    def walk(node: Any, keys: List[str]):
        nonlocal changed
        if not isinstance(node, (dict, list)):
            return
        if isinstance(node, dict):
            if keys and keys[0] in node:
                if len(keys) == 1:
                    cur = node.get(keys[0])
                    if isinstance(cur, list) and cur == old_arr:
                        node[keys[0]] = list(new_arr)
                        changed += 1
                else:
                    walk(node.get(keys[0]), keys[1:])
            for v in node.values():
                walk(v, keys)
        else:
            for it in node:
                walk(it, keys)
    walk(obj, path_keys)
    return changed


# ---------- address pools / helpers ----------

def _load_external_pool(locale: str) -> Optional[List[Dict[str, str]]]:
    base = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(base, "assets", "addresses", f"{locale}.json")
    try:
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list) and all(isinstance(x, dict) for x in data):
                    return data
    except Exception:
        pass
    return None

def _address_pool(locale: str) -> List[Dict[str, str]]:
    ext = _load_external_pool(locale)
    if ext:
        return ext
    if _BUILTIN_ADDRESS_POOLS and isinstance(_BUILTIN_ADDRESS_POOLS, dict):
        return _BUILTIN_ADDRESS_POOLS.get(locale, [])
    return []

def _stable_rng(seed_text: str) -> random.Random:
    h = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return random.Random(int(h[:16], 16))

def _choose_address(locale: str, seed_text: str) -> Optional[Dict[str, str]]:
    pool = _address_pool(locale)
    if not pool:
        return None
    rng = _stable_rng(seed_text)
    return dict(rng.choice(pool))

_ADDR_ALIASES = {
    "address_line_1": ["address_line_1", "addressLine1", "line1", "line_1", "address1", "addr1"],
    "city": ["city"],
    "state_or_region": ["state_or_region", "stateOrRegion", "state"],
    "country_code": ["country_code", "countryCode", "country"],
    "postal_code": ["postal_code", "postalCode", "postal", "zip", "zipCode"],
    "name": ["name"],
}

def _looks_like_address_dict(d: Any) -> bool:
    if not isinstance(d, dict):
        return False
    for aliases in _ADDR_ALIASES.values():
        for k in aliases:
            if k in d:
                return True
    return False

def _update_field_by_alias(dst: Dict[str, Any], field: str, value: Any) -> bool:
    changed = False
    for k in _ADDR_ALIASES.get(field, []):
        if k in dst and dst.get(k) != value:
            dst[k] = value
            changed = True
            break
    return changed

def _overlay_address_match_schema(dst: Dict[str, Any], src_camel: Dict[str, str]) -> bool:
    if not _looks_like_address_dict(dst):
        return False
    semantic_src = {
        "address_line_1": src_camel.get("addressLine1"),
        "city": src_camel.get("city"),
        "state_or_region": src_camel.get("stateOrRegion"),
        "postal_code": src_camel.get("postalCode"),
        "country_code": src_camel.get("countryCode"),
        "name": src_camel.get("name"),
    }
    changed = False
    for field, val in semantic_src.items():
        if val is None:
            continue
        if _update_field_by_alias(dst, field, val):
            changed = True
    return changed

def _set_address_field_any_depth(obj: Any, req_key: str, value: Any) -> int:
    def _to_semantic(k: str) -> Optional[str]:
        for sem, aliases in _ADDR_ALIASES.items():
            if k in aliases:
                return sem
        return None

    semantic = _to_semantic(req_key)
    if not semantic:
        count = 0
        def visit(parent, k, v):
            nonlocal count
            if isinstance(v, dict) and _looks_like_address_dict(v) and req_key in v and v.get(req_key) != value:
                v[req_key] = value
                count += 1
        _deep_visit(obj, visit)
        return count

    count = 0
    def visit(parent, k, v):
        nonlocal count
        if not isinstance(v, dict) or not _looks_like_address_dict(v):
            return
        if _update_field_by_alias(v, semantic, value):
            count += 1
    _deep_visit(obj, visit)
    return count

def _apply_random_address_any_depth(obj: Any, target_key: str, locale: str, seed_text: str) -> int:
    changes = 0
    def visit(parent: Any, k: str, v: Any):
        nonlocal changes
        if k == target_key and isinstance(v, dict) and _looks_like_address_dict(v):
            addr = _choose_address(locale, seed_text + "|" + target_key)
            if addr and _overlay_address_match_schema(v, addr):
                changes += 1
    _deep_visit(obj, visit)
    return changes

def _derive_buyer_county_from_seed(locale: str, row_seed: str) -> Optional[str]:
    addr = _choose_address(locale, row_seed + "|shipping_address")
    if not addr:
        return None
    return addr.get("stateOrRegion") or addr.get("city")


# ---------- Reinjection ----------

class SqlReinjector:
    """
    Rebuilds INSERT statements by replacing only translatable columns.

    translations: occurrence_key -> translated SQL-literal (already quoted/escaped)
      plain: "table:pk:col:"        ->  'Bonjour'
      JSON : "table:pk:col:$.title" ->  'Titre'
    """

    def __init__(
        self,
        schema_translatable: Dict[str, set],
        schema_pks: Dict[str, List[str]],
        hints: SchemaHints | None = None,
        schema_columns_order: Dict[str, List[str]] | None = None,
        *,
        json_overrides_by_locale: Dict[str, List[Dict]] | None = None,
        locale: str | None = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.schema_translatable = schema_translatable
        self.schema_pks = schema_pks
        self.hints = hints or SchemaHints()
        self.schema_columns_order = schema_columns_order or {}
        self.json_overrides_by_locale = json_overrides_by_locale or {}
        self.locale = locale or ""
        self.logger = logger or logging.getLogger("i18n-seed")

    def _has_json_overrides_for(self, table_raw: str, column: str) -> bool:
        rules = self.json_overrides_by_locale.get(self.locale, [])
        if not rules:
            return False
        t_norm = _norm_ident(table_raw)
        for r in rules:
            jp = r.get("json_path")
            if jp and not jp.startswith("$.."):
                continue
            t_ok = r.get("table") in (None, "*", t_norm)
            c_ok = r.get("column") in (None, "*", column)
            if t_ok and c_ok:
                return True
        return False

    def _apply_json_overrides(self, table: str, column: str, obj: object, row_seed: str) -> Tuple[object, int]:
        rules = self.json_overrides_by_locale.get(self.locale, [])
        if not rules or not isinstance(obj, (dict, list)):
            return obj, 0

        t_norm = _norm_ident(table)
        changed = 0

        for r in rules:
            jp = (r.get("json_path") or "")
            if jp and not jp.startswith("$.."):
                continue
            t_ok = r.get("table") in (None, "*", t_norm)
            c_ok = r.get("column") in (None, "*", column)
            if not (t_ok and c_ok):
                continue

            path_keys = _json_path_to_keys(jp) if jp else []

            # $..<column>.<...> → adjust when rule redundantly includes the column name
            adjusted_keys = path_keys[:]
            if path_keys and path_keys[0] == column:
                adjusted_keys = path_keys[1:]

            # random address overrides
            if r.get("random_address"):
                if path_keys == [column] and isinstance(obj, dict):
                    addr = _choose_address(self.locale, row_seed + "|" + column)
                    if addr and _overlay_address_match_schema(obj, addr):
                        changed += 1
                    continue
                if len(path_keys) == 1 and isinstance(obj, (dict, list)):
                    target_key = path_keys[0]
                    changed += _apply_random_address_any_depth(obj, target_key, self.locale, row_seed)
                    continue

            # top-level array replacement
            if isinstance(obj, list) and path_keys == [column] and "replace_array_value" in r and "new_array_value" in r:
                if obj == r["replace_array_value"]:
                    obj = list(r["new_array_value"])
                    changed += 1
                continue

            if not adjusted_keys:
                continue

            if "value" in r:
                if len(adjusted_keys) == 1:
                    changed += _set_any_depth_key(obj, adjusted_keys[0], r["value"])
                else:
                    changed += _set_value_at_path_any_depth(obj, adjusted_keys, r["value"])
            elif "replace_array_value" in r and "new_array_value" in r:
                changed += _replace_array_at_path_any_depth(
                    obj, adjusted_keys, r["replace_array_value"], r["new_array_value"]
                )

        return obj, changed

    def _apply_scalar_overrides(self, table: str, column: str, current_unquoted: str, row_seed: str) -> Tuple[Optional[str], bool]:
        rules = self.json_overrides_by_locale.get(self.locale, [])
        t_norm = _norm_ident(table)

        def _norm_enum(s: str) -> str:
            s = s or ""
            s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)
            s = re.sub(r'[_\-]+', ' ', s)
            s = re.sub(r'\s+', ' ', s)
            return s.strip().casefold()

        if rules:
            for r in rules:
                t_ok = r.get("table") in (None, "*", t_norm)
                c_ok = r.get("column") in (None, "*", column)
                if not (t_ok and c_ok):
                    continue
                mv = r.get("map_values")
                if isinstance(mv, dict):
                    if current_unquoted in mv:
                        new_val = str(mv[current_unquoted])
                        if new_val != current_unquoted:
                            return new_val, True
                    mv_norm = { _norm_enum(k): v for k, v in mv.items() }
                    key_norm = _norm_enum(current_unquoted)
                    if key_norm in mv_norm:
                        new_val = str(mv_norm[key_norm])
                        if new_val != current_unquoted:
                            return new_val, True

        if rules:
            for r in rules:
                jp = r.get("json_path")
                t_ok = r.get("table") in (None, "*", t_norm)
                c_ok = r.get("column") in (None, "*", column)
                if not (t_ok and c_ok):
                    continue
                if "value" in r:
                    if jp:
                        keys = _json_path_to_keys(jp)
                        if keys and keys != [column]:
                            continue
                    new_val = str(r["value"])
                    if new_val != current_unquoted:
                        return new_val, True

        if column == "marketplace_id" and rules:
            for r in rules:
                keys = _json_path_to_keys(r.get("json_path") or "")
                if keys == ["marketplace_ids"] and "replace_array_value" in r and "new_array_value" in r:
                    old_arr, new_arr = r["replace_array_value"], r["new_array_value"]
                    if isinstance(old_arr, list) and isinstance(new_arr, list) and len(old_arr) == len(new_arr) == 1:
                        if current_unquoted == str(old_arr[0]):
                            new_val = str(new_arr[0])
                            if new_val != current_unquoted:
                                return new_val, True

        if column == "buyer_county" and self.locale and not self.locale.endswith("_US"):
            derived = _derive_buyer_county_from_seed(self.locale, row_seed)
            if derived and derived != current_unquoted:
                return derived, True

        return None, False

    def _inject_into_json(self, s: str, json_map: Dict[str, str], table_raw: str, col: str, row_seed: str) -> Tuple[str, bool]:
        changed = False
        obj = _json_lenient_loads(s)
        if obj is None:
            # not parseable; leave as-is
            return s, False

        def walk(o, path: str = "$"):
            nonlocal changed
            if isinstance(o, dict):
                for k, v in o.items():
                    p = f"{path}.{k}"
                    if isinstance(v, str) and k in self.hints.json_string_keys and p in json_map:
                        new_v = json_map[p]
                        if new_v != v:
                            o[k] = new_v
                            changed = True
                    else:
                        walk(v, p)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    p = f"{path}[{i}]"
                    if isinstance(v, str) and p in json_map:
                        new_v = json_map[p]
                        if new_v != v:
                            o[i] = new_v
                            changed = True
                    else:
                        walk(v, p)

        if json_map:
            walk(obj)

        obj, ov_changed = self._apply_json_overrides(table_raw, col, obj, row_seed)
        changed = changed or (ov_changed > 0)

        # dump as compact, valid JSON (true/false/null)
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")), changed

    def reinject(self, sql_text: str, translations: Dict[str, str]) -> str:
        pieces: List[str] = []

        blocks = list(_iter_insert_blocks(sql_text))
        if not blocks:
            # nothing special; return original text
            return sql_text

        # keep any header/preamble before the first INSERT
        first_start, _ = blocks[0]
        if first_start > 0:
            pieces.append(sql_text[:first_start])

        for start, end in blocks:
            stmt = sql_text[start:end]
            table_raw, cols_opt, rows, has_cols = _parse_insert(stmt)
            if not table_raw or not rows:
                # parsing failed; keep the original block but ensure exactly one trailing newline
                pieces.append(stmt.strip() + "\n")
                continue

            cols = cols_opt or self.schema_columns_order.get(_norm_ident(table_raw)) or []
            table_key = _norm_ident(table_raw)
            tcols = set(self.schema_translatable.get(table_key, set()))
            pks = self.schema_pks.get(table_key, [])
            pk_idx = [cols.index(pk) for pk in pks if pk in cols]

            rebuilt_rows: List[str] = []

            for row_i, row_group in enumerate(rows, start=1):
                row_vals = row_group

                # stable row id from PKs if present
                if pk_idx:
                    pk_vals = []
                    for i in pk_idx:
                        if i < len(row_vals):
                            pk_vals.append(_strip_sql_quotes(row_vals[i]))
                    row_id = "|".join(pk_vals) if pk_vals else f"row{row_i}"
                else:
                    row_id = f"row{row_i}"

                row_seed = f"{self.locale}|{table_key}|{row_id}"

                new_vals: List[str] = []
                for c_i, raw in enumerate(row_vals):
                    col = cols[c_i] if c_i < len(cols) else ""
                    val = raw.strip()
                    unq = _strip_sql_quotes(val) if val else val

                    if col in tcols:
                        cands = _key_candidates(table_raw, row_id, row_i, col)

                        if is_likely_json_string(unq):
                            bucket = _collect_json_replacements(cands, translations)
                            need_ov = self._has_json_overrides_for(table_raw, col)
                            if bucket or need_ov:
                                json_repl_map = {jp: strip_quotes(v) for jp, v in bucket.items()}
                                try:
                                    new_json, _ = self._inject_into_json(unq, json_repl_map, table_raw, col, row_seed)
                                    new_vals.append("'" + sql_escape_single_quotes(new_json) + "'")
                                except Exception:
                                    new_vals.append(val)
                            else:
                                new_vals.append(val)
                        else:
                            tval = _lookup_scalar_translation(cands, translations)
                            if tval is not None:
                                new_vals.append(tval)
                            else:
                                new_unq, chg = self._apply_scalar_overrides(table_raw, col, _strip_sql_quotes(val), row_seed)
                                if chg:
                                    new_vals.append("'" + sql_escape_single_quotes(new_unq) + "'")
                                else:
                                    new_vals.append(val)
                    else:
                        if is_likely_json_string(unq) and self._has_json_overrides_for(table_raw, col):
                            try:
                                new_json, _ = self._inject_into_json(unq, {}, table_raw, col, row_seed)
                                new_vals.append("'" + sql_escape_single_quotes(new_json) + "'")
                            except Exception:
                                new_vals.append(val)
                        else:
                            new_unq, chg = self._apply_scalar_overrides(table_raw, col, _strip_sql_quotes(val), row_seed)
                            if chg:
                                new_vals.append("'" + sql_escape_single_quotes(new_unq) + "'")
                            else:
                                new_vals.append(val)

            rebuilt_rows.append("(" + ", ".join(new_vals) + ")")

            quoted = ', '.join('"' + c + '"' for c in cols) if cols else ""
            cols_out = f" ({quoted})" if has_cols and cols else ""
            rebuilt_stmt = f"INSERT INTO {table_raw}{cols_out} VALUES " + ", ".join(rebuilt_rows) + ";"

            # exactly one newline after every INSERT, no blank line in between
            pieces.append(rebuilt_stmt + "\n")

        # keep any tail after the last INSERT (footer, etc.)
        last_end = blocks[-1][1]
        if last_end < len(sql_text):
            pieces.append(sql_text[last_end:])

        # squash any accidental blank lines between consecutive INSERTs
        final_sql = "".join(pieces)
        final_sql = re.sub(r"(;)\n\s*\n(?=\s*INSERT\s+INTO)", r"\1\n", final_sql, flags=re.IGNORECASE)

        # ensure file ends with a single newline
        if not final_sql.endswith("\n"):
            final_sql += "\n"
        return final_sql


