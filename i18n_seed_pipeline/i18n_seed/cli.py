
# # i18n_seed/cli.py
# from __future__ import annotations
# import argparse, os, json
# from collections import defaultdict
# from typing import Dict, List, Tuple

# from .logger import setup_logger
# from .config import TranslateConfig, SchemaHints
# from .schema_loader import SchemaLoader
# from .sql_extractor import SqlExtractor
# from .placeholder_lock import lock_placeholders, unlock_placeholders
# from .translator_gemini import GeminiTranslator
# from .translator_base import Translator
# from .cache import TranslationCache
# from .validators import check_placeholder_parity, check_length_ratio, check_glossary_consistency, ValidationIssue
# from .reinjector import SqlReinjector
# from .cost_tracker import CostTracker
# from .utils import sql_escape_single_quotes

# # optional profiles import for --domain override
# try:
#     from .profiles import ALL_PROFILES
# except Exception:
#     ALL_PROFILES = []

# TITLE_COLUMNS = {"title", "item_name", "product_types", "product_types"}

# # --------- small helpers ---------

# def load_text(path: str) -> str:
#     # read and remove BOMs anywhere (utf-8-sig only strips a leading BOM)
#     with open(path, "r", encoding="utf-8-sig") as f:
#         text = f.read()
#     return text.replace("\ufeff", "")

# def save_text(path: str, text: str) -> None:
#     os.makedirs(os.path.dirname(path), exist_ok=True)
#     with open(path, "w", encoding="utf-8", newline="\n") as f:
#         f.write(text)

# def unique_preserve_order(seq: List[str]) -> List[str]:
#     seen, out = set(), []
#     for s in seq:
#         if s not in seen:
#             seen.add(s); out.append(s)
#     return out

# def configure_translator(cfg: TranslateConfig, logger, domain_rules: str = "") -> Translator:
#     if cfg.llm_provider.lower() == "gemini":
#         rules_text = ""
#         if domain_rules:
#             if isinstance(domain_rules, list):
#                 rules_text = "".join(r + "\n" for r in domain_rules)
#             elif isinstance(domain_rules, str):
#                 rules_text = domain_rules + ("\n" if not domain_rules.endswith("\n") else "")
#         return GeminiTranslator(
#             cfg.llm_model,
#             qps=cfg.qps,
#             max_retries=cfg.max_retries,
#             backoff_base=cfg.backoff_base,
#             logger=logger,
#             domain_rules=rules_text,
#         )
#     raise RuntimeError(f"Unsupported provider {cfg.llm_provider}")

# # --------- enforcement pass for titles / item_name ---------

# def _force_translate_titles_and_item_names(
#     *,
#     locale: str,
#     cfg: TranslateConfig,
#     logger,
#     base_domain_rules: str,
#     items,
#     locked_map: Dict[str, Tuple[str, Dict[str, str]]],
#     occ_to_col: Dict[str, str],
#     translated_accum: Dict[str, str],
#     cost: CostTracker,
#     dump_json_path: str,
# ) -> int:
#     """
#     Reload translations_{locale}.json, find entries whose column is in TITLE_COLUMNS
#     and target == source_en (non-empty), retranslate those locked sources with a
#     stricter prompt, update translated_accum and rewrite the dump json.

#     Returns the number of occurrences fixed.
#     """
#     if not os.path.exists(dump_json_path):
#         return 0

#     try:
#         with open(dump_json_path, "r", encoding="utf-8") as fh:
#             dump = json.load(fh)
#             if not isinstance(dump, list):
#                 return 0
#     except Exception as e:
#         logger.warning(f"Failed to load bilingual dump for enforcement: {e}")
#         return 0

#     # Which occurrences need a second pass?
#     needs_occ: List[str] = []
#     for entry in dump:
#         try:
#             occ = entry.get("occurrence_key")
#             src = entry.get("source_en") or ""
#             tgt = entry.get("target")
#             col = occ_to_col.get(occ, "")
#             if col in TITLE_COLUMNS and src and isinstance(tgt, str) and tgt == src:
#                 needs_occ.append(occ)
#         except Exception:
#             continue

#     if not needs_occ:
#         logger.info("Title enforcement: nothing to fix.")
#         return 0

#     # Unique locked sources to retranslate (only for those occs)
#     locked_to_occs: Dict[str, List[str]] = defaultdict(list)
#     for occ in needs_occ:
#         locked_src, _ = locked_map[occ]
#         locked_to_occs[locked_src].append(occ)

#     locked_unique = unique_preserve_order(list(locked_to_occs.keys()))

#     # Stricter prompt for titles/item_name
#     extra_rules = (
#         "\n# STRICT TITLE POLICY\n"
#         "All inputs in this batch are product titles or catalog item_name values.\n"
#         f"Translate them into {locale}.\n"
#         "Do NOT leave them in English (unless a token is a brand name, model number, SKU, ASIN, or marketplace ID).\n"
#         "Preserve any placeholder tokens exactly.\n"
#         "Return only the translation, no quotes, one line per input."
#     )
#     strict_translator = configure_translator(cfg, logger, domain_rules=base_domain_rules + extra_rules)

#     # Call translator in character-batched chunks (override cache by re-putting results)
#     pos = 0
#     forced_results: Dict[str, str] = {}
#     while pos < len(locked_unique):
#         cur, cur_chars = [], 0
#         while pos < len(locked_unique) and (cur_chars + len(locked_unique[pos])) <= cfg.batch_chars:
#             cur.append(locked_unique[pos]); cur_chars += len(locked_unique[pos]); pos += 1
#         if not cur:
#             cur = [locked_unique[pos]]; pos += 1

#         prompt_est = cur_chars + 200
#         out = strict_translator.translate_batch(cur, locale)
#         comp_est = sum(len(x) for x in out)
#         cost.add(prompt_est, comp_est)

#         for src, tgt in zip(cur, out):
#             forced_results[src] = tgt
#             # Update cache so future runs keep the corrected value
#             try:
#                 cache = TranslationCache(cfg.cache_path)
#                 cache.put(src, locale, tgt)
#             except Exception:
#                 pass

#     # Apply forced results into translated_accum and into the dump entries
#     fixed_count = 0
#     for locked_src, occs in locked_to_occs.items():
#         if locked_src not in forced_results:
#             continue
#         # Update the global map so subsequent steps (validation/reinjection) use the correction
#         translated_accum[locked_src] = forced_results[locked_src]

#         # Update dump occurrences
#         for occ in occs:
#             _, mapping = locked_map[occ]
#             forced_plain = unlock_placeholders(forced_results[locked_src], mapping)
#             # mutate in-memory dump list
#             for entry in dump:
#                 if entry.get("occurrence_key") == occ:
#                     entry["target"] = forced_plain
#                     fixed_count += 1

#     # Rewrite bilingual dump with enforced titles
#     try:
#         with open(dump_json_path, "w", encoding="utf-8") as fh:
#             json.dump(dump, fh, ensure_ascii=False, indent=2)
#         logger.info(f"Title enforcement: fixed {fixed_count} occurrence(s); dump updated.")
#     except Exception as e:
#         logger.warning(f"Failed rewriting enforced dump: {e}")

#     return fixed_count

# # ----------------- main pipeline -----------------

# def translate(cfg: TranslateConfig, domain_override: str | None = None) -> None:
#     logger = setup_logger(cfg.log_level)
#     logger.info("Loading schema...")
#     loader = SchemaLoader(cfg.schema_path)

#     # profile auto-detected by loader; allow a manual override
#     profile = loader.profile_from_schema()
#     if domain_override and domain_override != "auto" and ALL_PROFILES:
#         forced = next((p for p in ALL_PROFILES if p.id == domain_override), None)
#         if forced:
#             loader.profile = forced
#             profile = forced
#             logger.info(f"Domain override: {profile.id}")

#     logger.info(f"Domain profile: {profile.id}")

#     trans_cols = loader.translatable_columns()
#     pks = loader.primary_keys()
#     col_order = loader.columns_order_map()
#     logger.info(f"Tables with translatable columns: {len(trans_cols)}")

#     logger.info("Reading SQL...")
#     sql_text = load_text(cfg.input_sql_path)

#     logger.info("Extracting translatable items from SQL...")
#     extractor = SqlExtractor(trans_cols, pks, hints=loader.schema_hints, schema_columns_order=col_order)
#     items = extractor.extract(sql_text)
#     logger.info(f"Extracted items: {len(items)}")

#     logger.info("Locking placeholders and building manifest...")
#     locked_map: Dict[str, Tuple[str, Dict[str, str]]] = {}
#     occurrences_by_src: Dict[str, List[str]] = defaultdict(list)
#     manifest = []
#     occ_to_source: Dict[str, str] = {}
#     occ_to_col: Dict[str, str] = {}

#     for it in items:
#         locked, mapping = lock_placeholders(it.value, extra_patterns=profile.placeholder_patterns)
#         occ = it.occurrence_key()
#         locked_map[occ] = (locked, mapping)
#         occurrences_by_src[locked].append(occ)
#         manifest.append({"occurrence": occ, "source": it.value, "locked": locked, "column": it.column})
#         occ_to_source[occ] = it.value
#         occ_to_col[occ] = it.column

#     unique_sources = unique_preserve_order([m["locked"] for m in manifest])
#     logger.info(f"Unique source strings: {len(unique_sources)}")

#     cache = TranslationCache(cfg.cache_path)
#     glossary = None
#     if cfg.glossary_path and os.path.exists(cfg.glossary_path):
#         try:
#             import yaml
#             with open(cfg.glossary_path, 'r', encoding='utf-8') as gf:
#                 glossary = yaml.safe_load(gf) or None
#             logger.info(f"Loaded glossary with {len(glossary) if glossary else 0} root terms from {cfg.glossary_path}")
#         except Exception as e:
#             logger.warning(f"Failed to load glossary: {e}")

#     cost = CostTracker(cfg.cost_per_million)
#     os.makedirs(cfg.output_dir, exist_ok=True)

#     save_text(os.path.join(cfg.output_dir, "translation_manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2))

#     # Translator with domain rules
#     translator = configure_translator(cfg, logger, domain_rules=profile.system_rules)

#     report = {"locales": {}, "total_items": len(items)}

#     for locale in cfg.locales:
#         logger.info(f"=== Locale {locale} ===")
#         # Translate unique sources (cache-aware)
#         if cfg.dry_run:
#             translated_accum = {s: s for s in unique_sources}
#         else:
#             batch_in, translated_accum = [], {}
#             for s in unique_sources:
#                 cached = cache.get(s, locale)
#                 if cached is None:
#                     batch_in.append(s)
#                 else:
#                     translated_accum[s] = cached

#             pos = 0
#             while pos < len(batch_in):
#                 cur, cur_chars = [], 0
#                 while pos < len(batch_in) and (cur_chars + len(batch_in[pos])) <= cfg.batch_chars:
#                     cur.append(batch_in[pos]); cur_chars += len(batch_in[pos]); pos += 1
#                 if not cur:
#                     cur = [batch_in[pos]]; pos += 1

#                 prompt_est = cur_chars + 200
#                 out = translator.translate_batch(cur, locale)
#                 comp_est = sum(len(x) for x in out)
#                 cost.add(prompt_est, comp_est)

#                 for src, tgt in zip(cur, out):
#                     cache.put(src, locale, tgt)
#                     translated_accum[src] = tgt

#         # Bilingual dump (UNLOCKED)
#         dump_json_path = os.path.join(cfg.output_dir, f"translations_{locale}.json")
#         dump = []
#         for it in items:
#             occ = it.occurrence_key()
#             locked_src, mapping = locked_map[occ]
#             tgt_locked = translated_accum.get(locked_src, locked_src)
#             tgt_plain = unlock_placeholders(tgt_locked, mapping)
#             dump.append({"occurrence_key": occ, "source_en": it.value, "target": tgt_plain})
#         with open(dump_json_path, "w", encoding="utf-8") as f:
#             json.dump(dump, f, ensure_ascii=False, indent=2)
#         logger.info(f"Exported bilingual dump: {dump_json_path}")

#         # ---- NEW: enforce translation for titles/item_name that remained English ----
#         fixed = 0
#         if not cfg.dry_run:
#             base_rules = profile.system_rules if isinstance(profile.system_rules, str) else "".join((profile.system_rules or []))
#             fixed = _force_translate_titles_and_item_names(
#                 locale=locale,
#                 cfg=cfg,
#                 logger=logger,
#                 base_domain_rules=base_rules or "",
#                 items=items,
#                 locked_map=locked_map,
#                 occ_to_col=occ_to_col,
#                 translated_accum=translated_accum,
#                 cost=cost,
#                 dump_json_path=dump_json_path,
#             )
#         if fixed:
#             logger.info(f"Enforced {fixed} title/item_name translation(s).")

#         # Validation & occurrence mapping (uses possibly-updated translated_accum)
#         issues: List[ValidationIssue] = []
#         occurrence_to_translated: Dict[str, str] = {}

#         for src_locked, occ_keys in occurrences_by_src.items():
#             tgt_locked = translated_accum.get(src_locked, src_locked)
#             issues.extend(check_placeholder_parity(src_locked, tgt_locked, locale))

#             for occ_key in occ_keys:
#                 _, mapping = locked_map[occ_key]
#                 src_plain = occ_to_source[occ_key]
#                 final_tgt = unlock_placeholders(tgt_locked, mapping)

#                 issues.extend(check_length_ratio(src_plain, final_tgt, locale, cfg.length_ratio_min, cfg.length_ratio_max))
#                 # If you want glossary checks back on, uncomment the next line:
#                 # issues.extend(check_glossary_consistency(final_tgt, locale, glossary))

#                 occurrence_to_translated[occ_key] = "'" + sql_escape_single_quotes(final_tgt) + "'"

#         issues_path = os.path.join(cfg.output_dir, f"validation_{locale}.json")
#         with open(issues_path, "w", encoding="utf-8") as f:
#             json.dump([issue.__dict__ for issue in issues], f, ensure_ascii=False, indent=2)
#         logger.info(f"Validation issues for {locale}: {len(issues)} (see {issues_path})")

#         if not cfg.dry_run:
#             reinjector = SqlReinjector(
#                 trans_cols, pks,
#                 hints=loader.schema_hints,
#                 json_overrides_by_locale=profile.json_overrides_by_locale,
#                 locale=locale,
#             )
#             localized_sql = reinjector.reinject(sql_text, occurrence_to_translated)
#             out_path = os.path.join(cfg.output_dir, f"seed_{locale}.sql")
#             save_text(out_path, localized_sql)
#             logger.info(f"Wrote {out_path}")

#         report["locales"][locale] = {
#             "unique_translated": len(translated_accum),
#             "issues": len(issues),
#             "titles_enforced": fixed,
#         }

#     report["cost_chars_total"] = cost.total_chars
#     report["cost_est_usd"] = cost.est_cost_usd
#     save_text(os.path.join(cfg.output_dir, "run_report.json"), json.dumps(report, ensure_ascii=False, indent=2))
#     logger.info(f"Estimated cost: ${cost.est_cost_usd:.2f} for {cost.total_chars} chars")

# def main():
#     ap = argparse.ArgumentParser(prog="i18n-seed", description="Translate SQL seeds to multiple locales")
#     sub = ap.add_subparsers(dest="cmd", required=True)

#     t = sub.add_parser("translate", help="Run translation pipeline")
#     t.add_argument("--schema", required=True)
#     t.add_argument("--input-sql", required=True)
#     t.add_argument("--output", required=True)
#     t.add_argument("--locales", nargs="+", required=True)
#     t.add_argument("--llm-provider", default="gemini")
#     t.add_argument("--llm-model", default="gemini-2.0-flash-001")
#     t.add_argument("--cache", default=".llm_cache.sqlite")
#     t.add_argument("--qps", type=float, default=1.0)
#     t.add_argument("--batch-chars", type=int, default=8000)
#     t.add_argument("--max-retries", type=int, default=5)
#     t.add_argument("--backoff-base", type=float, default=1.5)
#     t.add_argument("--cost-per-million", type=float, default=15.0)
#     t.add_argument("--length-ratio-min", type=float, default=0.45)
#     t.add_argument("--length-ratio-max", type=float, default=2.8)
#     t.add_argument("--log-level", default="INFO")
#     t.add_argument("--glossary", dest="glossary_path", default=None)
#     t.add_argument("--dry-run", action="store_true")
#     t.add_argument("--domain", default="auto", help="auto|amazon|slack|generic")

#     args = ap.parse_args()
#     cfg = TranslateConfig(
#         schema_path=args.schema, input_sql_path=args.input_sql, output_dir=args.output,
#         locales=args.locales, llm_provider=args.llm_provider, llm_model=args.llm_model,
#         cache_path=args.cache, qps=args.qps, batch_chars=args.batch_chars,
#         max_retries=args.max_retries, backoff_base=args.backoff_base,
#         cost_per_million=args.cost_per_million, length_ratio_min=args.length_ratio_min,
#         length_ratio_max=args.length_ratio_max, log_level=args.log_level,
#         dry_run=args.dry_run, glossary_path=args.glossary_path,
#     )
#     translate(cfg, domain_override=args.domain)

# if __name__ == "__main__":
#     main()

# i18n_seed/cli.py
from __future__ import annotations
import argparse, os, json, re
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

from .logger import setup_logger
from .config import TranslateConfig, SchemaHints
from .schema_loader import SchemaLoader
from .sql_extractor import SqlExtractor
from .placeholder_lock import lock_placeholders, unlock_placeholders
from .translator_gemini import GeminiTranslator
from .translator_base import Translator
from .cache import TranslationCache
from .validators import check_placeholder_parity, check_length_ratio, check_glossary_consistency, ValidationIssue
from .reinjector import SqlReinjector
from .cost_tracker import CostTracker
from .utils import sql_escape_single_quotes

# optional profiles import for --domain override
try:
    from .profiles import ALL_PROFILES
except Exception:
    ALL_PROFILES = []

# default columns for the enforcement pass
DEFAULT_TITLE_COLUMNS = {"title", "item_name"}

# --------- small helpers ---------

def load_text(path: str) -> str:
    # read and remove BOMs anywhere (utf-8-sig only strips a leading BOM)
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    return text.replace("\ufeff", "")

def save_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def unique_preserve_order(seq: List[str]) -> List[str]:
    seen, out = set(), []
    for s in seq:
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def configure_translator(cfg: TranslateConfig, logger, domain_rules: str = "") -> Translator:
    if cfg.llm_provider.lower() == "gemini":
        rules_text = ""
        if domain_rules:
            if isinstance(domain_rules, list):
                rules_text = "".join(r + "\n" for r in domain_rules)
            elif isinstance(domain_rules, str):
                rules_text = domain_rules + ("\n" if not domain_rules.endswith("\n") else "")
        return GeminiTranslator(
            cfg.llm_model,
            qps=cfg.qps,
            max_retries=cfg.max_retries,
            backoff_base=cfg.backoff_base,
            logger=logger,
            domain_rules=rules_text,
        )
    raise RuntimeError(f"Unsupported provider {cfg.llm_provider}")

# --------- enforcement pass for titles / item_name ---------

def _parse_table_from_occ(occ: str) -> str:
    # occurrence_key format: table:rowIdOrRowIndex:column:
    # take the first segment as table
    return (occ.split(":", 1)[0] or "").strip()

def _force_translate_titles_and_item_names(
    *,
    locale: str,
    cfg: TranslateConfig,
    logger,
    base_domain_rules: str,
    locked_map: Dict[str, Tuple[str, Dict[str, str]]],
    occ_to_col: Dict[str, str],
    translated_accum: Dict[str, str],
    cost: CostTracker,
    dump_json_path: str,
    enforce_enabled: bool,
    only_cols: Optional[List[str]] = None,
    only_tables: Optional[List[str]] = None,
    occkey_regex: Optional[str] = None,
    max_occurrences: Optional[int] = None,
    extra_prompt_path: Optional[str] = None,
) -> int:
    """
    Reload translations_{locale}.json, find entries whose column matches and target == source_en,
    retranslate those locked sources with a stricter prompt, update translated_accum and rewrite the dump json.

    Returns the number of occurrences fixed.
    """
    if not enforce_enabled:
        logger.info("Title enforcement disabled.")
        return 0
    if not os.path.exists(dump_json_path):
        logger.info("Title enforcement: dump not found, skipping.")
        return 0

    try:
        with open(dump_json_path, "r", encoding="utf-8") as fh:
            dump = json.load(fh)
            if not isinstance(dump, list):
                logger.info("Title enforcement: dump is not a list, skipping.")
                return 0
    except Exception as e:
        logger.warning(f"Failed to load bilingual dump for enforcement: {e}")
        return 0

    # normalize filters
    cols_allowed = set([c.strip() for c in (only_cols or [])]) if only_cols else set(DEFAULT_TITLE_COLUMNS)
    tables_allowed = set([t.strip() for t in (only_tables or [])]) if only_tables else None
    occ_pat = re.compile(occkey_regex) if occkey_regex else None

    # Which occurrences need a second pass?
    needs_occ: List[str] = []
    for entry in dump:
        try:
            occ = entry.get("occurrence_key", "")
            src = (entry.get("source_en") or "").strip()
            tgt = entry.get("target")
            col = occ_to_col.get(occ, "")
            table = _parse_table_from_occ(occ)

            if not src:
                continue
            if not isinstance(tgt, str):
                continue
            if tgt.strip() != src:
                continue  # already translated

            # column filter
            if cols_allowed and col not in cols_allowed:
                continue
            # table filter
            if tables_allowed and table not in tables_allowed:
                continue
            # regex filter on occurrence key
            if occ_pat and not occ_pat.search(occ):
                continue

            needs_occ.append(occ)
        except Exception:
            continue

    if not needs_occ:
        logger.info("Title enforcement: nothing to fix.")
        return 0

    if max_occurrences is not None and max_occurrences >= 0:
        needs_occ = needs_occ[:max_occurrences]

    # Unique locked sources to retranslate (only for those occs)
    locked_to_occs: Dict[str, List[str]] = defaultdict(list)
    for occ in needs_occ:
        locked_src, _ = locked_map.get(occ, ("", {}))
        if locked_src:
            locked_to_occs[locked_src].append(occ)

    locked_unique = unique_preserve_order(list(locked_to_occs.keys()))
    if not locked_unique:
        logger.info("Title enforcement: no locked sources resolved, skipping.")
        return 0

    # Prepare strict prompt (append optional extra rules file)
    user_extra = ""
    if extra_prompt_path:
        try:
            user_extra = "\n" + load_text(extra_prompt_path).strip() + "\n"
            logger.info(f"Title enforcement: using extra prompt from {extra_prompt_path}")
        except Exception as e:
            logger.warning(f"Failed to read --title-enforce-prompt: {e}")

    extra_rules = (
        "\n# STRICT TITLE POLICY\n"
        "All inputs in this batch are product titles or catalog item_name values.\n"
        f"Translate them into {locale}.\n"
        "Do NOT leave them in English (unless the token is a brand name, model number, SKU, ASIN, or marketplace ID).\n"
        "Preserve placeholder tokens exactly.\n"
        "Return only the translation, no quotes, one line per input."
        + user_extra
    )

    strict_translator = configure_translator(cfg, logger, domain_rules=(base_domain_rules or "") + extra_rules)

    # Call translator in character-batched chunks (override cache by re-putting results)
    pos = 0
    forced_results: Dict[str, str] = {}
    while pos < len(locked_unique):
        cur, cur_chars = [], 0
        while pos < len(locked_unique) and (cur_chars + len(locked_unique[pos])) <= cfg.batch_chars:
            cur.append(locked_unique[pos]); cur_chars += len(locked_unique[pos]); pos += 1
        if not cur:
            cur = [locked_unique[pos]]; pos += 1

        prompt_est = cur_chars + 200
        out = strict_translator.translate_batch(cur, locale)
        comp_est = sum(len(x) for x in out)
        cost.add(prompt_est, comp_est)

        # update cache immediately so next runs keep the enforced results
        cache = TranslationCache(cfg.cache_path)
        for src, tgt in zip(cur, out):
            forced_results[src] = tgt
            try:
                cache.put(src, locale, tgt)
            except Exception:
                pass

    # Apply forced results into translated_accum and into the dump entries
    fixed_count = 0
    occ_set = set(needs_occ)
    for locked_src, occs in locked_to_occs.items():
        if locked_src not in forced_results:
            continue
        # Update the global map so subsequent steps (validation/reinjection) use the correction
        translated_accum[locked_src] = forced_results[locked_src]

    # mutate in-memory dump list
    for entry in dump:
        occ = entry.get("occurrence_key")
        if occ in occ_set:
            locked_src, mapping = locked_map[occ]
            new_plain = unlock_placeholders(forced_results.get(locked_src, ""), mapping) if locked_src in forced_results else None
            if new_plain:
                entry["target"] = new_plain
                fixed_count += 1

    # Rewrite bilingual dump with enforced titles
    try:
        with open(dump_json_path, "w", encoding="utf-8") as fh:
            json.dump(dump, fh, ensure_ascii=False, indent=2)
        logger.info(f"Title enforcement: fixed {fixed_count} occurrence(s); dump updated.")
    except Exception as e:
        logger.warning(f"Failed rewriting enforced dump: {e}")

    return fixed_count

# ----------------- main pipeline -----------------

def translate(
    cfg: TranslateConfig,
    domain_override: str | None = None,
    *,
    enforce_titles: bool = False,
    enforce_only_cols: Optional[List[str]] = None,
    enforce_only_tables: Optional[List[str]] = None,
    enforce_occkey_regex: Optional[str] = None,
    enforce_max: Optional[int] = None,
    title_enforce_prompt_path: Optional[str] = None,
) -> None:
    logger = setup_logger(cfg.log_level)
    logger.info("Loading schema...")
    loader = SchemaLoader(cfg.schema_path)

    # profile auto-detected by loader; allow a manual override
    profile = loader.profile_from_schema()
    if domain_override and domain_override != "auto" and ALL_PROFILES:
        forced = next((p for p in ALL_PROFILES if p.id == domain_override), None)
        if forced:
            loader.profile = forced
            profile = forced
            logger.info(f"Domain override: {profile.id}")

    logger.info(f"Domain profile: {profile.id}")

    trans_cols = loader.translatable_columns()
    pks = loader.primary_keys()
    col_order = loader.columns_order_map()
    logger.info(f"Tables with translatable columns: {len(trans_cols)}")

    logger.info("Reading SQL...")
    sql_text = load_text(cfg.input_sql_path)

    logger.info("Extracting translatable items from SQL...")
    extractor = SqlExtractor(trans_cols, pks, hints=loader.schema_hints, schema_columns_order=col_order)
    items = extractor.extract(sql_text)
    logger.info(f"Extracted items: {len(items)}")

    logger.info("Locking placeholders and building manifest...")
    locked_map: Dict[str, Tuple[str, Dict[str, str]]] = {}
    occurrences_by_src: Dict[str, List[str]] = defaultdict(list)
    manifest = []
    occ_to_source: Dict[str, str] = {}
    occ_to_col: Dict[str, str] = {}

    for it in items:
        locked, mapping = lock_placeholders(it.value, extra_patterns=profile.placeholder_patterns)
        occ = it.occurrence_key()
        locked_map[occ] = (locked, mapping)
        occurrences_by_src[locked].append(occ)
        manifest.append({"occurrence": occ, "source": it.value, "locked": locked, "column": it.column})
        occ_to_source[occ] = it.value
        occ_to_col[occ] = it.column

    unique_sources = unique_preserve_order([m["locked"] for m in manifest])
    logger.info(f"Unique source strings: {len(unique_sources)}")

    cache = TranslationCache(cfg.cache_path)
    glossary = None
    if cfg.glossary_path and os.path.exists(cfg.glossary_path):
        try:
            import yaml
            with open(cfg.glossary_path, 'r', encoding='utf-8') as gf:
                glossary = yaml.safe_load(gf) or None
            logger.info(f"Loaded glossary with {len(glossary) if glossary else 0} root terms from {cfg.glossary_path}")
        except Exception as e:
            logger.warning(f"Failed to load glossary: {e}")

    cost = CostTracker(cfg.cost_per_million)
    os.makedirs(cfg.output_dir, exist_ok=True)

    save_text(os.path.join(cfg.output_dir, "translation_manifest.json"), json.dumps(manifest, ensure_ascii=False, indent=2))

    # Translator with domain rules
    translator = configure_translator(cfg, logger, domain_rules=profile.system_rules)

    report = {"locales": {}, "total_items": len(items)}

    for locale in cfg.locales:
        logger.info(f"=== Locale {locale} ===")
        # Translate unique sources (cache-aware)
        if cfg.dry_run:
            translated_accum = {s: s for s in unique_sources}
        else:
            batch_in, translated_accum = [], {}
            for s in unique_sources:
                cached = cache.get(s, locale)
                if cached is None:
                    batch_in.append(s)
                else:
                    translated_accum[s] = cached

            pos = 0
            while pos < len(batch_in):
                cur, cur_chars = [], 0
                while pos < len(batch_in) and (cur_chars + len(batch_in[pos])) <= cfg.batch_chars:
                    cur.append(batch_in[pos]); cur_chars += len(batch_in[pos]); pos += 1
                if not cur:
                    cur = [batch_in[pos]]; pos += 1

                prompt_est = cur_chars + 200
                out = translator.translate_batch(cur, locale)
                comp_est = sum(len(x) for x in out)
                cost.add(prompt_est, comp_est)

                for src, tgt in zip(cur, out):
                    cache.put(src, locale, tgt)
                    translated_accum[src] = tgt

        # Bilingual dump (UNLOCKED)
        dump_json_path = os.path.join(cfg.output_dir, f"translations_{locale}.json")
        dump = []
        for it in items:
            occ = it.occurrence_key()
            locked_src, mapping = locked_map[occ]
            tgt_locked = translated_accum.get(locked_src, locked_src)
            tgt_plain = unlock_placeholders(tgt_locked, mapping)
            dump.append({"occurrence_key": occ, "source_en": it.value, "target": tgt_plain})
        with open(dump_json_path, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2)
        logger.info(f"Exported bilingual dump: {dump_json_path}")

        # ---- NEW: enforce translation for titles/item_name that remained English ----
        base_rules = profile.system_rules if isinstance(profile.system_rules, str) else "".join((profile.system_rules or []))
        fixed = _force_translate_titles_and_item_names(
            locale=locale,
            cfg=cfg,
            logger=logger,
            base_domain_rules=base_rules or "",
            locked_map=locked_map,
            occ_to_col=occ_to_col,
            translated_accum=translated_accum,
            cost=cost,
            dump_json_path=dump_json_path,
            enforce_enabled=enforce_titles,
            only_cols=enforce_only_cols,
            only_tables=enforce_only_tables,
            occkey_regex=enforce_occkey_regex,
            max_occurrences=enforce_max,
            extra_prompt_path=title_enforce_prompt_path,
        )
        if fixed:
            logger.info(f"Enforced {fixed} title/item_name translation(s).")

        # Validation & occurrence mapping (uses possibly-updated translated_accum)
        issues: List[ValidationIssue] = []
        occurrence_to_translated: Dict[str, str] = {}

        for src_locked, occ_keys in occurrences_by_src.items():
            tgt_locked = translated_accum.get(src_locked, src_locked)
            issues.extend(check_placeholder_parity(src_locked, tgt_locked, locale))

            for occ_key in occ_keys:
                _, mapping = locked_map[occ_key]
                src_plain = occ_to_source[occ_key]
                final_tgt = unlock_placeholders(tgt_locked, mapping)

                issues.extend(check_length_ratio(src_plain, final_tgt, locale, cfg.length_ratio_min, cfg.length_ratio_max))
                # If you want glossary checks back on, uncomment:
                # issues.extend(check_glossary_consistency(final_tgt, locale, glossary))

                occurrence_to_translated[occ_key] = "'" + sql_escape_single_quotes(final_tgt) + "'"

        issues_path = os.path.join(cfg.output_dir, f"validation_{locale}.json")
        with open(issues_path, "w", encoding="utf-8") as f:
            json.dump([issue.__dict__ for issue in issues], f, ensure_ascii=False, indent=2)
        logger.info(f"Validation issues for {locale}: {len(issues)} (see {issues_path})")

        if not cfg.dry_run:
            reinjector = SqlReinjector(
                trans_cols, pks,
                hints=loader.schema_hints,
                json_overrides_by_locale=profile.json_overrides_by_locale,
                locale=locale,
            )
            localized_sql = reinjector.reinject(sql_text, occurrence_to_translated)
            out_path = os.path.join(cfg.output_dir, f"seed_{locale}.sql")
            save_text(out_path, localized_sql)
            logger.info(f"Wrote {out_path}")

        report["locales"][locale] = {
            "unique_translated": len(translated_accum),
            "issues": len(issues),
            "titles_enforced": fixed,
        }

    report["cost_chars_total"] = cost.total_chars
    report["cost_est_usd"] = cost.est_cost_usd
    save_text(os.path.join(cfg.output_dir, "run_report.json"), json.dumps(report, ensure_ascii=False, indent=2))
    logger.info(f"Estimated cost: ${cost.est_cost_usd:.2f} for {cost.total_chars} chars")

def main():
    ap = argparse.ArgumentParser(prog="i18n-seed", description="Translate SQL seeds to multiple locales")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("translate", help="Run translation pipeline")
    t.add_argument("--schema", required=True)
    t.add_argument("--input-sql", required=True)
    t.add_argument("--output", required=True)
    t.add_argument("--locales", nargs="+", required=True)
    t.add_argument("--llm-provider", default="gemini")
    t.add_argument("--llm-model", default="gemini-2.0-flash-001")
    t.add_argument("--cache", default=".llm_cache.sqlite")
    t.add_argument("--qps", type=float, default=1.0)
    t.add_argument("--batch-chars", type=int, default=8000)
    t.add_argument("--max-retries", type=int, default=5)
    t.add_argument("--backoff-base", type=float, default=1.5)
    t.add_argument("--cost-per-million", type=float, default=15.0)
    t.add_argument("--length-ratio-min", type=float, default=0.45)
    t.add_argument("--length-ratio-max", type=float, default=2.8)
    t.add_argument("--log-level", default="INFO")
    t.add_argument("--glossary", dest="glossary_path", default=None)
    t.add_argument("--dry-run", action="store_true")
    t.add_argument("--domain", default="auto", help="auto|amazon|slack|generic")

    # ---- NEW: enforcement options ----
    t.add_argument("--enforce-titles", action="store_true",
                   help="Second pass: re-translate any title/item_name where target == source_en.")
    t.add_argument("--enforce-only-cols", nargs="+", default=None,
                   help="Limit enforcement to these column names (default: title, item_name).")
    t.add_argument("--enforce-only-tables", nargs="+", default=None,
                   help="Limit enforcement to these table names.")
    t.add_argument("--enforce-occkey-regex", default=None,
                   help="Regex on occurrence_key to select entries for enforcement.")
    t.add_argument("--enforce-max", type=int, default=None,
                   help="Max number of occurrences to enforce (order preserved).")
    t.add_argument("--title-enforce-prompt", default=None,
                   help="Path to a txt file with extra strict rules appended for the title enforcement pass.")

    args = ap.parse_args()
    cfg = TranslateConfig(
        schema_path=args.schema, input_sql_path=args.input_sql, output_dir=args.output,
        locales=args.locales, llm_provider=args.llm_provider, llm_model=args.llm_model,
        cache_path=args.cache, qps=args.qps, batch_chars=args.batch_chars,
        max_retries=args.max_retries, backoff_base=args.backoff_base,
        cost_per_million=args.cost_per_million, length_ratio_min=args.length_ratio_min,
        length_ratio_max=args.length_ratio_max, log_level=args.log_level,
        dry_run=args.dry_run, glossary_path=args.glossary_path,
    )

    translate(
        cfg,
        domain_override=args.domain,
        enforce_titles=args.enforce_titles,
        enforce_only_cols=args.enforce_only_cols,
        enforce_only_tables=args.enforce_only_tables,
        enforce_occkey_regex=args.enforce_occkey_regex,
        enforce_max=args.enforce_max,
        title_enforce_prompt_path=args.title_enforce_prompt,
    )

if __name__ == "__main__":
    main()
