import os
import time
import json
import logging
import random
from typing import List, Dict, Any, Optional

import requests

from .translator_base import Translator

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT_TEMPLATE = (
    "You are a professional software localization specialist.\n"
    "Translate the following items into {lang_label} (locale={locale}).\n"
    "STRICT RULES:\n"
    "1) Preserve placeholders exactly: __PH0__, __PH1__, {{...}}, {{{{...}}}}, URLs, emails, "
    "<@U123>, <#C123|name>, emoji :smile:, %s, %(name)s, ${{VAR}}, and <tags>.\n"
    "2) Do NOT add/remove/reorder items.\n"
    "3) Output MUST be a JSON array of objects: [{{\"i\": <int>, \"t\": <string>}}]\n"
    "   where \"i\" is the input index and \"t\" is the translated string.\n"
    "INPUT JSON (array of objects: {{\"i\": <int>, \"t\": <string>}}):\n"
    "{payload}\n"
)

PROMPT_SIMPLE_LIST = (
    "You are a professional software localization specialist.\n"
    "Translate the following strings into {lang_label} (locale={locale}).\n"
    "Preserve placeholders exactly and keep the same order.\n"
    "Output MUST be a JSON array of strings only (no extra keys or commentary).\n"
    "INPUT JSON (array of strings):\n"
    "{payload}\n"
)

LANG_LABELS = {
    "pt_BR": "Portuguese (Brazil)",
    "fr_FR": "French (France)",
    "it_IT": "Italian (Italy)",
    "de_DE": "German (Germany)",
    "es_MX": "Spanish (Mexico)",
    "zh_CN": "Chinese (Simplified)",
    "zh_HK": "Chinese (Hong Kong)",
    "zh_TW": "Chinese (Traditional)",
    "ja_JP": "Japanese",
    "ko_KR": "Korean",
    "vi_VN": "Vietnamese",
    "tr_TR": "Turkish",
    "nl_NL": "Dutch",
    "sv_SE": "Swedish",
    "nb_NO": "Norwegian (Bokmal)",
    "da_DK": "Danish",
}

def _strip_code_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        parts = s.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                return p
    return s

def _json_from_text(s: str) -> Any:
    """Parse JSON from model text; tolerant of code fences and pre/post prose."""
    s = _strip_code_fence(s)
    try:
        return json.loads(s)
    except Exception:
        pass
    first = s.find("[")
    last = s.rfind("]")
    if first != -1 and last != -1 and last > first:
        cand = s[first:last + 1].strip()
        return json.loads(cand)

    return json.loads(s)  

def _coerce_index_map(parsed: Any, n_expected: int) -> Optional[Dict[int, str]]:
    """
    Coerce model output into {index -> translation}.

    Accepts any of:
      A) [{"i": 0, "t": "..."}, ...]  (preferred)
      B) [[0, "..."], [1, "..."], ...]
      C) ["...", "...", ...]          (must match n_expected; map by order)
      D) {"translations": <any of A/B/C>}
    Returns None if nothing matches.
    """
    arr = parsed
    if isinstance(arr, dict) and "translations" in arr:
        arr = arr["translations"]

    if isinstance(arr, list) and arr and isinstance(arr[0], dict):
        out: Dict[int, str] = {}
        for o in arr:
            if not isinstance(o, dict):
                continue
            i = o.get("i", o.get("index"))
            t = o.get("t", o.get("text", o.get("translation")))
            if i is None or t is None:
                continue
            try:
                out[int(i)] = str(t)
            except Exception:
                continue
        return out

    if isinstance(arr, list) and arr and isinstance(arr[0], list):
        out = {}
        for pair in arr:
            if len(pair) != 2:
                continue
            i, t = pair
            try:
                out[int(i)] = str(t)
            except Exception:
                continue
        return out

    if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
        if len(arr) == n_expected:
            return {i: arr[i] for i in range(n_expected)}
        return {}

    return None

def _post_gemini(url: str, api_key: str, prompt: str, timeout: int = 120) -> dict:
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "response_mime_type": "application/json"
        }
    }
    resp = requests.post(url, headers=headers, params={"key": api_key}, json=body, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()

def _extract_text_field(data: dict) -> Optional[str]:
    """Best-effort extraction of the primary text field from Gemini response."""
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None

class GeminiTranslator(Translator):
    """
    Index-aware, self-healing translator for Gemini:
      - Sends batches as [{i, t}] and expects same indices back.
      - If items are missing, retries only the missing subset: full -> halves -> singles.
      - Accepts multiple valid response shapes and has a simple-list fallback for tiny batches.
    """

    def __init__(
        self,
        model: str,
        qps: float = 1.0,
        max_retries: int = 5,
        backoff_base: float = 1.5,
        logger: Optional[logging.Logger] = None,
    ):
        self.model = model
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set")
        self.qps = qps
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.logger = logger or logging.getLogger("i18n-seed")
        self._last_call = 0.0

    def _respect_qps(self):
        min_interval = 1.0 / max(self.qps, 0.01)
        dt = time.time() - self._last_call
        if dt < min_interval:
            time.sleep(min_interval - dt)

    def translate_batch(self, src_texts: List[str], target_locale: str) -> List[str]:
        """
        Returns translations in the *same order* as src_texts.
        Self-heals when some items are dropped by retrying only the missing ones.
        """
        idx_to_src: Dict[int, str] = {i: s for i, s in enumerate(src_texts)}
        idx_to_tgt: Dict[int, str] = {}

        self._request_with_heal(idx_to_src, idx_to_tgt, target_locale)

        out = []
        for i in range(len(src_texts)):
            out.append(idx_to_tgt.get(i, src_texts[i]))
        return out

    def _request_with_heal(self, idx_to_src: Dict[int, str], idx_to_tgt: Dict[int, str], locale: str):
        """
        Send a batch; if some indexes are missing/mismatched, re-send only those.
        Progressive refinement: full batch -> halves -> singles.
        """
        pending = dict(idx_to_src)

        missing = self._one_request_and_collect(pending, idx_to_tgt, locale)
        if not missing:
            return

        if len(missing) > 1:
            items = sorted(missing.items())  
            mid = max(1, len(items) // 2)
            left = dict(items[:mid])
            right = dict(items[mid:])

            miss_left = self._one_request_and_collect(left, idx_to_tgt, locale)

            todo_right = dict(right)
            todo_right.update(miss_left)
            miss_right = self._one_request_and_collect(todo_right, idx_to_tgt, locale)
            missing = miss_right

        for i, s in list(missing.items()):
            _ = self._one_request_and_collect({i: s}, idx_to_tgt, locale)

    def _one_request_and_collect(
        self,
        idx_to_src: Dict[int, str],
        idx_to_tgt: Dict[int, str],
        locale: str
    ) -> Dict[int, str]:
        """
        Sends one request for the given subset of items.
        Returns a dict of {idx: src} for items still missing after this attempt.
        """
        if not idx_to_src:
            return {}

        self._respect_qps()

        lang_label = LANG_LABELS.get(locale, locale)
        # Stable order helps the model & our fallback path.
        payload_objs = [{"i": i, "t": s} for i, s in sorted(idx_to_src.items(), key=lambda x: x[0])]
        url = GEMINI_URL_TEMPLATE.format(model=self.model)

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                # Primary attempt: object schema
                try:
                    prompt = PROMPT_TEMPLATE.format(
                        lang_label=lang_label,
                        locale=locale,
                        payload=json.dumps(payload_objs, ensure_ascii=False),
                    )
                except KeyError as e:
                    raise RuntimeError(
                        f"Prompt template has unescaped braces near: {e!r}. "
                        "Double all literal { and } in PROMPT_TEMPLATE."
                    ) from e

                data = _post_gemini(url, self.api_key, prompt)
                self._last_call = time.time()

                text = _extract_text_field(data)
                if not text:
                    # Log a short snippet to help diagnose empty candidates.
                    self.logger.warning(f"Gemini returned no text; raw keys: {list(data.keys())}")

                mapping: Dict[int, str] = {}
                try:
                    parsed = _json_from_text(text or json.dumps(data))
                    mapping = _coerce_index_map(parsed, n_expected=len(idx_to_src)) or {}
                except Exception as parse_err:
                    # Leave mapping empty; we'll hit fallback or retry below.
                    self.logger.warning(f"Gemini JSON parse failed: {parse_err}")

                # Apply whatever we mapped
                for idx, tgt in mapping.items():
                    if idx in idx_to_src:
                        idx_to_tgt[idx] = str(tgt)

                # Compute what's still missing
                missing = {i: s for i, s in idx_to_src.items() if i not in idx_to_tgt}

                # ---- NEW: fallback even if mapping is partially filled ----
                # If *any* items are still missing and the subset is small, try a simple-list fallback
                # just for the missing indices. This covers "returned wrong i" / mis-indexing cases.
                if missing and len(missing) <= 8:
                    missing_sorted = sorted(missing.items(), key=lambda x: x[0])  # [(i, src), ...]
                    simple_payload = [s for _, s in missing_sorted]
                    simple_prompt = PROMPT_SIMPLE_LIST.format(
                        lang_label=lang_label,
                        locale=locale,
                        payload=json.dumps(simple_payload, ensure_ascii=False),
                    )
                    try:
                        data2 = _post_gemini(url, self.api_key, simple_prompt)
                        self._last_call = time.time()
                        text2 = _extract_text_field(data2)
                        parsed2 = _json_from_text(text2 or json.dumps(data2))
                        if isinstance(parsed2, list) and all(isinstance(x, str) for x in parsed2) and len(parsed2) == len(simple_payload):
                            # Map back by order to the correct indices
                            for k, (_, _src) in enumerate(missing_sorted):
                                idx_missing = missing_sorted[k][0]
                                idx_to_tgt[idx_missing] = parsed2[k]
                            # recompute missing after fallback
                            missing = {i: s for i, s in idx_to_src.items() if i not in idx_to_tgt}
                        else:
                            self.logger.warning(
                                f"Fallback simple-list failed; snippet: {(text2 or str(data2))[:200]!r}"
                            )
                    except Exception as parse_err2:
                        self.logger.warning(f"Fallback JSON parse failed: {parse_err2}")

                # Final report for this attempt
                if missing:
                    if not mapping:
                        snippet = (text or json.dumps(data))[:200]
                        self.logger.warning(
                            f"Gemini mapped 0/{len(idx_to_src)}; snippet: {snippet!r}"
                        )
                    else:
                        self.logger.warning(
                            f"Gemini returned {len(idx_to_src) - len(missing)} of {len(idx_to_src)}; "
                            f"missing indices: {sorted(missing.keys())[:10]}{'...' if len(missing) > 10 else ''}"
                        )
                return missing

            except Exception as e:
                last_err = e
                sleep = (self.backoff_base ** attempt) + random.uniform(0, 0.6)
                self.logger.warning(f"Gemini request failed ({e}); retrying in {sleep:.1f}s")
                time.sleep(sleep)

        # After retries, report all items as still missing
        self.logger.error(f"Gemini translation failed after retries: {last_err}")
        return dict(idx_to_src)
