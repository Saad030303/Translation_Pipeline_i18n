#!/usr/bin/env python3
"""
Filter entries where source == target != NULL (robust to hidden Unicode).
- Normalizes with NFKC
- Removes zero-width / format controls (Cf), including U+200B..U+200D, U+FEFF
- Trims and collapses whitespace
- Treats the literal "null" (any case) as empty
- Works with JSON array OR NDJSON (one JSON object per line)

Usage:
  python filter_equal_entries.py input.json > equal.json
  cat data.ndjson | python filter_equal_entries.py - > equal.json

Options:
  --source-field name   (default: source_en)
  --target-field name   (default: target)
  --case-insensitive    Compare case-insensitively
  --debug               Print reasons when entries don't match
"""

import argparse, json, sys, unicodedata
from typing import Any, Dict, Iterable, List, Optional

def load_json_flexible(path: str) -> Any:
    """Load a JSON array/dict or NDJSON (one object per line)."""
    text = sys.stdin.read() if path == "-" else open(path, "r", encoding="utf-8").read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try NDJSON
        objs = []
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                objs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"NDJSON parse error on line {i}: {e}") from e
        return objs

def iter_objects(root: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(root, list):
        for x in root:
            if isinstance(x, dict):
                yield x
    elif isinstance(root, dict):
        # allow a dict that contains a list of dicts
        for v in root.values():
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        yield x

def strip_zero_width(s: str) -> str:
    # Remove all Unicode "format" controls (category Cf), e.g. ZWSP, ZWNJ, ZWJ, BOM
    return "".join(ch for ch in s if unicodedata.category(ch) != "Cf")

def clean_text(s: Optional[Any], collapse_ws: bool = True, case_insensitive: bool = False) -> Optional[str]:
    if s is None:
        return None
    if not isinstance(s, str):
        return None
    # Unicode normalize
    s = unicodedata.normalize("NFKC", s)
    # Remove zero-width/format controls
    s = strip_zero_width(s)
    # Trim
    s = s.strip()
    # Collapse whitespace to single spaces (handles NBSP/thin space etc.)
    if collapse_ws:
        # Replace any Unicode whitespace sequence with a single space
        s = " ".join(s.split())
    # Treat literal "null" as empty
    if s.lower() == "null":
        return None
    if case_insensitive:
        s = s.casefold()
    return s if s != "" else None

def main() -> None:
    ap = argparse.ArgumentParser(description="Return entries where source == target != NULL (robust).")
    ap.add_argument("input", help="Path to input JSON/NDJSON file or '-' for stdin")
    ap.add_argument("--source-field", default="source_en")
    ap.add_argument("--target-field", default="target")
    ap.add_argument("--case-insensitive", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    data = load_json_flexible(args.input)
    out: List[Dict[str, Any]] = []

    for obj in iter_objects(data):
        raw_src = obj.get(args.source_field, None)
        raw_tgt = obj.get(args.target_field, None)

        src = clean_text(raw_src, case_insensitive=args.case_insensitive)
        tgt = clean_text(raw_tgt, case_insensitive=args.case_insensitive)

        if src is None or tgt is None:
            if args.debug:
                print(f"[skip] {obj.get('occurrence_key','<no key>')}: empty/NULL source/target", file=sys.stderr)
            continue

        if src == tgt:
            out.append(obj)
        elif args.debug:
            # Helpful diff for tricky cases
            def codepoints(s: str) -> str:
                return " ".join(f"U+{ord(c):04X}" for c in s)
            print(
                f"[mismatch] {obj.get('occurrence_key','<no key>')}: "
                f"src={repr(src)} ({codepoints(src)}) != "
                f"tgt={repr(tgt)} ({codepoints(tgt)})",
                file=sys.stderr,
            )

    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()