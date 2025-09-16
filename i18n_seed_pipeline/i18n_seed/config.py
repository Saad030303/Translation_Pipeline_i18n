# # from dataclasses import dataclass, field
# # from typing import List, Optional, Dict

# # @dataclass
# # class TranslateConfig:
# #     schema_path: str
# #     input_sql_path: str
# #     output_dir: str
# #     locales: List[str]
# #     llm_provider: str = "gemini"
# #     llm_model: str = "gemini-2.0-flash-001"
# #     cache_path: str = ".llm_cache.sqlite"
# #     qps: float = 1.0
# #     batch_chars: int = 8000
# #     max_retries: int = 5
# #     backoff_base: float = 1.5
# #     cost_per_million: float = 15.0  # USD per 1M characters (prompt + completion)
# #     include_patterns: List[str] = field(default_factory=list)
# #     exclude_patterns: List[str] = field(default_factory=list)
# #     glossary_path: Optional[str] = None
# #     length_ratio_min: float = 0.45
# #     length_ratio_max: float = 2.8
# #     log_level: str = "INFO"
# #     dry_run: bool = False

# # @dataclass
# # class SchemaHints:
# #     json_string_keys: List[str] = field(default_factory=lambda: [
# #         "text", "value", "title", "subtitle", "label", "message", "description", "topic", "purpose"
# #     ])

# #     # Remove the old skip_name_substrings entirely
# #     # and replace with:
# #     exact_skip_names: List[str] = field(default_factory=lambda: [
# #         "id","uuid","locale","timezone","hex","hash","token","password",
# #         "bot_id","api_app_id","team_id","enterprise_id","created_by","updated_by","deleted_by",
# #         "md5","sha","ts","timestamp","ip_address"  # keep exact 'ip_address' if present
# #     ])
# #     suffix_skip_names: List[str] = field(default_factory=lambda: [
# #         "_id","_url","_email","_hash","_token","_tz","_locale","_color","_timestamp"
# #     ])

# #     text_types: List[str] = field(default_factory=lambda: ["VARCHAR","TEXT","CHAR","NVARCHAR","NTEXT","CLOB","JSON"])

# # i18n_seed/config.py
# from dataclasses import dataclass, field
# from typing import List, Optional

# @dataclass
# class TranslateConfig:
#     schema_path: str
#     input_sql_path: str
#     output_dir: str
#     locales: List[str]
#     llm_provider: str = "gemini"
#     llm_model: str = "gemini-2.0-flash-001"
#     cache_path: str = ".llm_cache.sqlite"
#     qps: float = 1.0
#     batch_chars: int = 8000
#     max_retries: int = 5
#     backoff_base: float = 1.5
#     cost_per_million: float = 15.0  # USD per 1M characters (prompt + completion)
#     include_patterns: List[str] = field(default_factory=list)
#     exclude_patterns: List[str] = field(default_factory=list)
#     glossary_path: Optional[str] = None
#     length_ratio_min: float = 0.45
#     length_ratio_max: float = 2.8
#     log_level: str = "INFO"
#     dry_run: bool = False


# @dataclass
# class SchemaHints:
#     """
#     Amazon-friendly defaults:
#     - We DO translate product_type (so it's *not* in exact_skip_names)
#     - We skip obvious IDs/codes/SKUs/marketplace IDs; we also skip seller_name
#       so merchant names stay intact.
#     - Added common Amazon JSON keys (bullets/features) to json_string_keys.
#     - Expanded text_types to catch all text-like columns across engines.
#     """
#     # JSON keys we translate when a column stores JSON
#     json_string_keys: List[str] = field(default_factory=lambda: [
#         # generic UI/text keys
#         "text", "value", "title", "subtitle", "label", "message",
#         "description", "topic", "purpose",
#         # amazon-ish metadata keys
#         "bullet", "bullets", "feature", "features", "short_description", "long_description", "summary"
#     ])

#     # Columns that should NEVER be translated (exact name match, case-insensitive in our loader)
#     # NOTE: Deliberately *not* including 'product_type' so we translate it.
#     exact_skip_names: List[str] = field(default_factory=lambda: [
#         # generic identifiers / security
#         "id","uuid","locale","timezone","hex","hash","token","password",
#         "md5","sha","ts","timestamp","ip_address",
#         # slack/infra-ish identifiers (harmless to keep)
#         "bot_id","api_app_id","team_id","enterprise_id","created_by","updated_by","deleted_by",
#         # amazon commerce specifics we do NOT translate
#         "seller_name",          # keep merchant/brand string literal
#         "sku", "asin", "upc", "ean", "isbn", "isbn10", "isbn13",
#         "marketplace_id", "marketplace_ids",  # redundant with suffix skip but explicit is fine
#         # status-like fields (business logic, not display copy)
#         "status", "order_status", "shipment_status", "fulfillment_channel"
#     ])

#     # If a column name ends with any of these suffixes, we never translate it.
#     suffix_skip_names: List[str] = field(default_factory=lambda: [
#         "_id", "_ids", "_url", "_email", "_hash", "_token", "_tz",
#         "_locale", "_timestamp", "_sku"
#     ])

#     # SQL types treated as human text (case-insensitive in our loader)
#     text_types: List[str] = field(default_factory=lambda: [
#         "VARCHAR","TEXT","CHAR","NVARCHAR","NTEXT","CLOB","JSON",
#         # broaden coverage across engines
#         "ENUM","NVARCHAR2","LONGTEXT","MEDIUMTEXT"
#     ])

# i18n_seed/config.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Set, Optional

@dataclass
class SchemaHints:
    # Column name skip rules
    exact_skip_names: Set[str] = field(default_factory=lambda: {
        "id", "uuid", "created_at", "updated_at", "deleted_at",
        "email", "username", "user_id", "order_id", "sku",
        "marketplace_id", "marketplace_ids"
    })
    suffix_skip_names: Set[str] = field(default_factory=lambda: {
        "_id", "_ids", "_hash", "_sha", "_md5"
    })
    # JSON keys we allow the extractor/reinjector to translate
    json_string_keys: Set[str] = field(default_factory=lambda: {
        "title", "name", "description", "subtitle", "heading", "label",
        "note", "message", "style", "category", "brand", "bullet"
    })
    # Column types considered “text-like”
    text_types: Set[str] = field(default_factory=lambda: {
        "TEXT", "VARCHAR", "NVARCHAR", "CHAR", "CLOB", "JSON"
    })

@dataclass
class TranslateConfig:
    schema_path: str
    input_sql_path: str
    output_dir: str
    locales: List[str]

    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.0-flash-001"
    cache_path: str = ".llm_cache.sqlite"
    qps: float = 1.0
    batch_chars: int = 8000
    max_retries: int = 5
    backoff_base: float = 1.5
    cost_per_million: float = 15.0
    length_ratio_min: float = 0.45
    length_ratio_max: float = 2.8
    log_level: str = "INFO"
    dry_run: bool = False
    glossary_path: Optional[str] = None
