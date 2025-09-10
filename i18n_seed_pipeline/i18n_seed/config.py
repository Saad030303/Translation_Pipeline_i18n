from dataclasses import dataclass, field
from typing import List, Optional, Dict

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
    cost_per_million: float = 15.0  # USD per 1M characters (prompt + completion)
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    glossary_path: Optional[str] = None
    length_ratio_min: float = 0.45
    length_ratio_max: float = 2.8
    log_level: str = "INFO"
    dry_run: bool = False

@dataclass
class SchemaHints:
    json_string_keys: List[str] = field(default_factory=lambda: [
        "text", "value", "title", "subtitle", "label", "message", "description", "topic", "purpose"
    ])

    # Remove the old skip_name_substrings entirely
    # and replace with:
    exact_skip_names: List[str] = field(default_factory=lambda: [
        "id","uuid","locale","timezone","color","hex","hash","token","password",
        "bot_id","api_app_id","team_id","enterprise_id","created_by","updated_by","deleted_by",
        "md5","sha","ts","timestamp","ip_address"  # keep exact 'ip_address' if present
    ])
    suffix_skip_names: List[str] = field(default_factory=lambda: [
        "_id","_url","_email","_hash","_token","_tz","_locale","_color","_timestamp"
    ])

    text_types: List[str] = field(default_factory=lambda: ["VARCHAR","TEXT","CHAR","NVARCHAR","NTEXT","CLOB","JSON"])
