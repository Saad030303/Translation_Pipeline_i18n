from __future__ import annotations
import argparse, os, json, csv
from collections import defaultdict
from typing import Dict, List, Tuple
from pathlib import Path

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

def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def save_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def unique_preserve_order(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def configure_translator(cfg: TranslateConfig, logger) -> Translator:
    if cfg.llm_provider.lower() == "gemini":
        return GeminiTranslator(cfg.llm_model, qps=cfg.qps, max_retries=cfg.max_retries, backoff_base=cfg.backoff_base, logger=logger)
    raise RuntimeError(f"Unsupported provider {cfg.llm_provider}")

def translate(cfg: TranslateConfig) -> None:
    logger = setup_logger(cfg.log_level)
    logger.info("Loading schema...")
    loader = SchemaLoader(cfg.schema_path)
    trans_cols = loader.translatable_columns()
    pks = loader.primary_keys()
    logger.info(f"Tables with translatable columns: {len(trans_cols)}")

    logger.info("Reading SQL...")
    sql_text = load_text(cfg.input_sql_path)

    logger.info("Extracting translatable items from SQL...")
    extractor = SqlExtractor(trans_cols, pks)
    items = extractor.extract(sql_text)
    logger.info(f"Extracted items: {len(items)}")

    # Build manifest of unique source strings (after locking)
    logger.info("Locking placeholders and building manifest...")
    locked_map: Dict[str, Tuple[str, Dict[str, str]]] = {}
    occurrences_by_src: Dict[str, List[str]] = defaultdict(list) # source -> list of occurrence_keys
    manifest = []
    for it in items:
        locked, mapping = lock_placeholders(it.value)
        locked_map[it.occurrence_key()] = (locked, mapping)
        occurrences_by_src[locked].append(it.occurrence_key())
        manifest.append({"occurrence": it.occurrence_key(), "source": it.value, "locked": locked})

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

    report = {"locales": {}, "total_items": len(items)}
    translator = configure_translator(cfg, logger)

    for locale in cfg.locales:
        logger.info(f"=== Locale {locale} ===")
        if cfg.dry_run:
            # Skip API calls entirely on dry-run
            translated_accum = {s: s for s in unique_sources}  # identity mapping for validations
        else:
            batch_in: List[str] = []
            translated_accum: Dict[str, str] = {}
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
                

        dump_json_path = os.path.join(cfg.output_dir, f"translations_{locale}.json")
        with open(dump_json_path, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "occurrence_key": it.occurrence_key(),
                        "source_en": it.value,
                        "target": translated_accum.get(it.value, it.value),
                    }
                    for it in items
                ],
                f,
                ensure_ascii=False,
                indent=2
            )

        logger.info(f"Exported bilingual dump: {dump_json_path}")

        # batch_in: List[str] = []
        # translated_accum: Dict[str, str] = {}

        # for s in unique_sources:
        #     cached = cache.get(s, locale)
        #     if cached is None:
        #         batch_in.append(s)
        #     else:
        #         translated_accum[s] = cached

        # # batching by chars
        # pos = 0
        # while pos < len(batch_in):
        #     cur = []
        #     cur_chars = 0
        #     while pos < len(batch_in) and (cur_chars + len(batch_in[pos])) <= cfg.batch_chars:
        #         cur.append(batch_in[pos]); cur_chars += len(batch_in[pos]); pos += 1
        #     if not cur:
        #         cur = [batch_in[pos]]; pos += 1

        #     prompt_est = cur_chars + 200
        #     out = translator.translate_batch(cur, locale)
        #     comp_est = sum(len(x) for x in out)
        #     cost.add(prompt_est, comp_est)

        #     for src, tgt in zip(cur, out):
        #         cache.put(src, locale, tgt)
        #         translated_accum[src] = tgt

        # Validation & occurrence mapping
        issues: List[ValidationIssue] = []
        occurrence_to_translated: Dict[str, str] = {}

        for src_locked, occ_keys in occurrences_by_src.items():
            tgt_locked = translated_accum[src_locked]
            issues.extend(check_placeholder_parity(src_locked, tgt_locked, locale))

            for occ_key in occ_keys:
                _, mapping = locked_map[occ_key]
                final_tgt = unlock_placeholders(tgt_locked, mapping)
                src_plain = next(m["source"] for m in manifest if m["occurrence"] == occ_key)
                issues.extend(check_length_ratio(src_plain, final_tgt, locale, cfg.length_ratio_min, cfg.length_ratio_max))
                issues.extend(check_glossary_consistency(final_tgt, locale, glossary))
                occurrence_to_translated[occ_key] = "'" + sql_escape_single_quotes(final_tgt) + "'"

        issues_path = os.path.join(cfg.output_dir, f"validation_{locale}.json")
        save_text(issues_path, json.dumps([issue.__dict__ for issue in issues], ensure_ascii=False, indent=2))
        logger.info(f"Validation issues for {locale}: {len(issues)} (see {issues_path})")

        if not cfg.dry_run:
            reinjector = SqlReinjector(trans_cols, pks)
            localized_sql = reinjector.reinject(sql_text, occurrence_to_translated)
            out_path = os.path.join(cfg.output_dir, f"seed_{locale}.sql")
            save_text(out_path, localized_sql)
            logger.info(f"Wrote {out_path}")

        report["locales"][locale] = {
            "unique_translated": len(translated_accum),
            "issues": len(issues)
        }

    report["cost_chars_total"] = cost.total_chars
    report["cost_est_usd"] = cost.est_cost_usd
    save_text(os.path.join(cfg.output_dir, "run_report.json"), json.dumps(report, ensure_ascii=False, indent=2))

    # logger.info(f"Estimated cost: ${cost.est_cost_usd:.2f} for {cost.total_chars} chars")

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

    args = ap.parse_args()

    cfg = TranslateConfig(
        schema_path=args.schema,
        input_sql_path=args.input_sql,
        output_dir=args.output,
        locales=args.locales,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        cache_path=args.cache,
        qps=args.qps,
        batch_chars=args.batch_chars,
        max_retries=args.max_retries,
        backoff_base=args.backoff_base,
        cost_per_million=args.cost_per_million,
        length_ratio_min=args.length_ratio_min,
        length_ratio_max=args.length_ratio_max,
        log_level=args.log_level,
        dry_run=args.dry_run,
        glossary_path=args.glossary_path,
    )
    translate(cfg)

if __name__ == "__main__":
    main()
