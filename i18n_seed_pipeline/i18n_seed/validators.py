from __future__ import annotations
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class ValidationIssue:
    kind: str
    detail: str
    source: str
    target: str
    locale: str

def check_placeholder_parity(src_locked: str, tgt_locked: str, locale: str) -> List[ValidationIssue]:
    def tokens(s: str) -> List[str]:
        return [t for t in s.split() if t.startswith("__PH") and t.endswith("__")]
    src = tokens(src_locked)
    tgt = tokens(tgt_locked)
    issues = []
    if sorted(src) != sorted(tgt):
        issues.append(ValidationIssue("placeholder_parity","Locked placeholder tokens mismatch",src_locked,tgt_locked,locale))
    return issues

def check_length_ratio(src: str, tgt: str, locale: str, lo: float, hi: float) -> List[ValidationIssue]:
    issues = []
    if len(src) == 0: 
        return issues
    ratio = len(tgt) / max(len(src), 1)
    if ratio < lo or ratio > hi:
        issues.append(ValidationIssue("length_ratio", f"Length ratio {ratio:.2f} not in [{lo},{hi}]", src, tgt, locale))
    return issues

def check_glossary_consistency(tgt: str, locale: str, glossary: Dict[str, Dict[str, str]] | None) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not glossary:
        return issues
    # glossary format: {term_en: {locale: expected_translation, ...}, ...}
    for term_en, per_locale in glossary.items():
        expected = per_locale.get(locale)
        if expected and term_en.lower() not in ("",):
            # If expected term should appear in target when source had it; we can't see source here easily.
            # So we just warn if expected form is missing in target but substring match is heuristic.
            if expected not in tgt:
                issues.append(ValidationIssue("glossary", f"Expected glossary term not found: '{expected}'", "", tgt, locale))
    return issues
