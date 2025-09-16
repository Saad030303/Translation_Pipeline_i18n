from .base import DomainProfile
import re

GenericProfile = DomainProfile(
    id="generic",
    placeholder_patterns=[
        re.compile(r'\bhttps?://\S+'),
        re.compile(r'%\([a-zA-Z_][a-zA-Z0-9_]*\)s'),
        re.compile(r'%s'),
        re.compile(r'\{\{.*?\}\}'),
        re.compile(r'\$\{[^}]+\}'),
        re.compile(r'<[^>]+>'),               # tags
        re.compile(r'\b[A-Z0-9\-]{4,}\b'),    # coarse codes
    ],
    json_string_keys={"title","subtitle","caption","label","description","text","message"},
    exact_skip_columns={"id"},
    suffix_skip_columns={"_id","_ids"},
    system_rules=(
        "GENERAL L10N RULES\n"
        "- Preserve placeholders, tags, URLs, and codes exactly.\n"
        "- If not translatable (code/enum), return unchanged.\n"
    ),
    validators=[]
)