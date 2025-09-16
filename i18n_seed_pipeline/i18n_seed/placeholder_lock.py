# from __future__ import annotations
# import re
# from typing import Tuple, Dict, List, Pattern

# def _collect_non_overlapping_matches(s: str, patterns: List[Pattern]) -> List[tuple[int, int, str]]:
#     selected: List[tuple[int, int, str]] = []
#     def overlaps(a_start, a_end, b_start, b_end): return not (a_end <= b_start or b_end <= a_start)
#     for pat in patterns:
#         for m in pat.finditer(s):
#             st, en = m.span()
#             if st == en: continue
#             if any(overlaps(st,en,x[0],x[1]) for x in selected): continue
#             selected.append((st,en,m.group(0)))
#     selected.sort(key=lambda t: t[0])
#     return selected

# def lock_placeholders(s: str, extra_patterns: List[Pattern] | None = None) -> Tuple[str, Dict[str, str]]:
#     patterns = list(extra_patterns or [])
#     if not patterns: return s, {}
#     matches = _collect_non_overlapping_matches(s, patterns)
#     out_parts: List[str] = []; mapping: Dict[str, str] = {}
#     cursor = 0; ph_idx = 0
#     for st, en, txt in matches:
#         if cursor < st: out_parts.append(s[cursor:st])
#         key = f"__PH{ph_idx}__"; mapping[key] = txt
#         out_parts.append(key); ph_idx += 1; cursor = en
#     if cursor < len(s): out_parts.append(s[cursor:])
#     return "".join(out_parts), mapping

# def unlock_placeholders(s: str, mapping: Dict[str, str]) -> str:
#     for k in sorted(mapping.keys(), key=lambda x: -len(x)):
#         s = s.replace(k, mapping[k])
#     return s

# # Patterns to lock
# # URL_RE = re.compile(r"https?://\S+")
# # EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
# # SLACK_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")           # <@U12345>
# # SLACK_CHANNEL_RE = re.compile(r"<#[A-Z0-9]+\|[^>]+>")    # <#C123|name>
# # EMOJI_SHORTCODE_RE = re.compile(r":[a-z0-9_+\-]+:")
# # CURLY_RE = re.compile(r"\{[^{}]+\}")
# # DBL_CURLY_RE = re.compile(r"\{\{[^{}]+\}\}")
# # PERCENT_FMT_RE = re.compile(r"%\([^)]+\)[sd]|%[sd]")
# # ENV_RE = re.compile(r"\$\{[^}]+\}")
# # ANGLE_RE = re.compile(r"<[^>\s/][^>]*>")  # keep HTML-like tags and unknown angled tokens
# # ID_TOKEN_RE = re.compile(r"\b[UC][A-Z0-9]{6,}\b") # Slack-like IDs Uxxxxxx, Cxxxxxx
# # VAR_RE = re.compile(r":([a-zA-Z_][\w]*)") # :param
# # # Shreyansh please take a look and tell me how to extend those.

# # LOCK_ORDER = [
# #     URL_RE, EMAIL_RE, SLACK_CHANNEL_RE, SLACK_MENTION_RE, EMOJI_SHORTCODE_RE,
# #     DBL_CURLY_RE, CURLY_RE, PERCENT_FMT_RE, ENV_RE, ANGLE_RE, ID_TOKEN_RE, VAR_RE
# # ]

# i18n_seed/placeholder_lock.py
from __future__ import annotations
import re
from typing import Tuple, Dict, List

def lock_placeholders(s: str, extra_patterns: List[re.Pattern]) -> Tuple[str, Dict[str, str]]:
    """
    Replace substrings matching any of the provided regex patterns with __PH{n}__ tokens.
    Returns (locked_text, mapping).
    """
    mapping: Dict[str, str] = {}
    idx = 0

    def _sub_fn(m):
        nonlocal idx
        original = m.group(0)
        key = f"__PH{idx}__"
        mapping[key] = original
        idx += 1
        return key

    locked = s
    for pat in extra_patterns or []:
        locked = pat.sub(_sub_fn, locked)
    return locked, mapping

def unlock_placeholders(s: str, mapping: Dict[str, str]) -> str:
    # Replace longer keys first to avoid partial collisions
    for k in sorted(mapping.keys(), key=lambda x: -len(x)):
        s = s.replace(k, mapping[k])
    return s