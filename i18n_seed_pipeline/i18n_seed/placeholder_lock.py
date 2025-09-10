import re
from typing import Tuple, Dict

# Patterns to lock
URL_RE = re.compile(r"https?://\S+")
EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
SLACK_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")           # <@U12345>
SLACK_CHANNEL_RE = re.compile(r"<#[A-Z0-9]+\|[^>]+>")    # <#C123|name>
EMOJI_SHORTCODE_RE = re.compile(r":[a-z0-9_+\-]+:")
CURLY_RE = re.compile(r"\{[^{}]+\}")
DBL_CURLY_RE = re.compile(r"\{\{[^{}]+\}\}")
PERCENT_FMT_RE = re.compile(r"%\([^)]+\)[sd]|%[sd]")
ENV_RE = re.compile(r"\$\{[^}]+\}")
ANGLE_RE = re.compile(r"<[^>\s/][^>]*>")  # keep HTML-like tags and unknown angled tokens
ID_TOKEN_RE = re.compile(r"\b[UC][A-Z0-9]{6,}\b") # Slack-like IDs Uxxxxxx, Cxxxxxx
VAR_RE = re.compile(r":([a-zA-Z_][\w]*)") # :param
# Shreyansh please take a look and tell me how to extend those.

LOCK_ORDER = [
    URL_RE, EMAIL_RE, SLACK_CHANNEL_RE, SLACK_MENTION_RE, EMOJI_SHORTCODE_RE,
    DBL_CURLY_RE, CURLY_RE, PERCENT_FMT_RE, ENV_RE, ANGLE_RE, ID_TOKEN_RE, VAR_RE
]

def lock_placeholders(s: str) -> Tuple[str, Dict[str, str]]:
    """Replaces placeholders with __PH{n}__ tags and returns mapping."""
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
    for pat in LOCK_ORDER:
        locked = pat.sub(_sub_fn, locked)
    return locked, mapping

def unlock_placeholders(s: str, mapping: Dict[str, str]) -> str:
    # Replace longer keys first to avoid prefix collisions
    for k in sorted(mapping.keys(), key=lambda x: -len(x)):
        s = s.replace(k, mapping[k])
    return s
