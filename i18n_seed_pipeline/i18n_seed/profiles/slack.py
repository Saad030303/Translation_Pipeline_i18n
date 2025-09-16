# from .base import DomainProfile
# import re

# def _slack_validators():
#     def slack_tokens(src: str, tgt: str, locale: str):
#         import re
#         issues = []
#         for pat in [r'<@U[A-Z0-9]+>', r'<#[A-Z0-9]+\|[^>]+>', r':[a-z0-9_+-]+:', r'```.+?```', r'`[^`]+`']:
#             for m in re.findall(pat, src, flags=re.DOTALL):
#                 if m not in tgt:
#                     issues.append(dict(kind="slack_parity", detail=f"Missing Slack token `{m}`", source=src, target=tgt, locale=locale))
#         return issues
#     return [slack_tokens]

# SlackProfile = DomainProfile(
#     id="slack",
#     server_name_contains=["slack"],
#     table_name_contains=["slack_"],
#     placeholder_patterns=[
#         re.compile(r'<@U[A-Z0-9]+>'),
#         re.compile(r'<#[A-Z0-9]+\|[^>]+>'),
#         re.compile(r':[a-z0-9_+-]+:'),
#         re.compile(r'```.+?```', re.DOTALL),
#         re.compile(r'`[^`]+`'),
#         re.compile(r'\bhttps?://\S+'),
#         re.compile(r'%\([a-zA-Z_][a-zA-Z0-9_]*\)s'),
#         re.compile(r'%s'),
#         re.compile(r'\{\{.*?\}\}'),
#     ],
#     json_string_keys={"title","status_text","real_name","display_name","topic","purpose","description","text","subtitle","label"},
#     exact_skip_columns={"id","team_id","bot_id","api_app_id","is_bot","is_admin","is_owner"},
#     suffix_skip_columns={"_id","_ids","_ts"},
#     system_rules=(
#         "DOMAIN: SLACK UI CONTENT\n"
#         "- Preserve Slack mrkdwn tokens exactly: <@U…>, <#C…|…>, :emoji:, `code`, ```blocks```.\n"
#         "- Preserve URLs and any %(name)s/%s placeholders.\n"
#         "- App names look like product names—translate only generic words.\n"
#     ),
#     validators=_slack_validators()
# )

# i18n_seed/profiles/slack.py
from __future__ import annotations
import re
from . import DomainProfile

def slack_profile() -> DomainProfile:
    SLACK_MENTION_RE = re.compile(r"<@[A-Z0-9]+>")         # <@U12345>
    SLACK_CHANNEL_RE = re.compile(r"<#[A-Z0-9]+\|[^>]+>")  # <#C123|name>
    EMOJI_SHORTCODE_RE = re.compile(r":[a-z0-9_+\-]+:")

    return DomainProfile(
        id="slack",
        placeholder_patterns=[
            SLACK_CHANNEL_RE,
            SLACK_MENTION_RE,
            EMOJI_SHORTCODE_RE,
        ],
        system_rules=[
            "Do not translate Slack IDs or emoji shortcodes.",
            "Preserve mentions (<@U...>) and channels (<#C...|...>)."
        ],
        json_string_keys={
            "text", "title", "name", "description", "subtitle", "note"
        },
    )
