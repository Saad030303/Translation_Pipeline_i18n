import re

def sql_escape_single_quotes(s: str) -> str:
    return s.replace("'", "''")

def strip_sql_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1]
    return s

def is_likely_json_string(s: str) -> bool:
    s = s.strip()
    return (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))

WHITESPACE_RE = re.compile(r"\s+")

def normalize_space(s: str) -> str:
    return WHITESPACE_RE.sub(" ", s).strip()
