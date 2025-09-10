import os, time, json, logging, random, re
from typing import List, Dict, Any
import requests

from .translator_base import Translator

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT_TEMPLATE = (
    "You are a professional software localization specialist.\n"
    "Translate the following items into {lang_label} (locale={locale}).\n"
    "STRICT RULES:\n"
    "1) Preserve placeholders exactly: __PH0__, __PH1__, {{...}}, {{{{...}}}}, URLs, emails, "
    "<@U123>, <#C123|name>, emoji :smile:, %s, %(name)s, and <tags>.\n"
    "2) Do NOT add/remove/reorder items.\n"
    "3) Output MUST be a JSON array of objects: [[{{\"i\": <int>, \"t\": <string>}}]]\n"
    "   where \"i\" is the input index and \"t\" is the translated string.\n"
    "INPUT JSON (array of objects: {{\"i\": <int>, \"t\": <string>}}):\n"
    "{payload}\n"
)

LANG_LABELS = {
    "pt_BR": "Portuguese (Brazil)", "fr_FR": "French (France)", "it_IT": "Italian (Italy)",
    "de_DE": "German (Germany)", "es_MX": "Spanish (Mexico)", "zh_CN": "Chinese (Simplified)",
    "zh_HK": "Chinese (Hong Kong)", "zh_TW": "Chinese (Traditional)", "ja_JP": "Japanese",
    "ko_KR": "Korean", "vi_VN": "Vietnamese", "tr_TR": "Turkish", "nl_NL": "Dutch",
    "sv_SE": "Swedish", "nb_NO": "Norwegian (Bokmal)", "da_DK": "Danish",
}

def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        parts = s.split("```")
        # take the first chunk that looks like JSON
        for p in parts:
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                return p
    return s

def _json_from_text(s: str) -> Any:
    s = _strip_code_fence(s)
    # direct parse
    try:
        return json.loads(s)
    except Exception:
        pass
    # greedy bracket extraction
    first = s.find("["); last = s.rfind("]")
    if first != -1 and last != -1 and last > first:
        cand = s[first:last+1].strip()
        return json.loads(cand)
    # if still failing, raise
    return json.loads(s)  # will raise

def _post_gemini(url: str, api_key: str, prompt: str, timeout: int = 90) -> str:
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0,
            "response_mime_type": "application/json"
        }
    }
    resp = requests.post(url, headers=headers, params={"key": api_key}, json=body, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    # standard path
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"Unexpected response: {str(data)[:200]}")

class GeminiTranslator(Translator):
    def __init__(self, model: str, qps: float = 1.0, max_retries: int = 5, backoff_base: float = 1.5, logger: logging.Logger | None = None):
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

    # ---------- public API ----------
    def translate_batch(self, src_texts: List[str], target_locale: str) -> List[str]:
        """
        Returns translations in the *same order* as src_texts.
        Self-heals when some items are dropped by retrying only the missing ones.
        """
        # 1) initial request
        idx_to_src = {i: s for i, s in enumerate(src_texts)}
        idx_to_tgt: Dict[int, str] = {}

        self._request_with_heal(idx_to_src, idx_to_tgt, target_locale)

        # Assemble in order; if any missing (shouldn't happen), fallback to source
        out = []
        for i in range(len(src_texts)):
            out.append(idx_to_tgt.get(i, src_texts[i]))
        return out

    # ---------- internals ----------
    def _request_with_heal(self, idx_to_src: Dict[int, str], idx_to_tgt: Dict[int, str], locale: str):
        """
        Send a batch; if some indexes are missing/mismatched, re-send only those.
        Uses progressive refinement: full batch -> halves -> singles.
        """
        pending = dict(idx_to_src)  # copy

        # First attempt: full batch
        missing = self._one_request_and_collect(pending, idx_to_tgt, locale)
        if not missing:
            return

        # Second attempt: split into halves (binary-ish subdivision)
        if len(missing) > 1:
            items = sorted(missing.items())  # [(i, text), ...]
            mid = len(items) // 2
            left = dict(items[:mid])
            right = dict(items[mid:])
            # left
            miss_left = self._one_request_and_collect(left, idx_to_tgt, locale)
            # right (merge any that remain from left with right before next attempt)
            todo_right = dict(right)
            todo_right.update(miss_left)
            miss_right = self._one_request_and_collect(todo_right, idx_to_tgt, locale)
            missing = miss_right
        # Final attempt: singles
        for i, s in list(missing.items()):
            _ = self._one_request_and_collect({i: s}, idx_to_tgt, locale)

    def _one_request_and_collect(self, idx_to_src: Dict[int, str], idx_to_tgt: Dict[int, str], locale: str) -> Dict[int, str]:
        """
        Sends one request for the given subset of items.
        Returns a dict of {idx: src} for items still missing after this attempt.
        """
        if not idx_to_src:
            return {}

        # Respect QPS
        self._respect_qps()

        lang_label = LANG_LABELS.get(locale, locale)
        payload = [{"i": i, "t": s} for i, s in idx_to_src.items()]
        # Stable order helps models
        payload.sort(key=lambda x: x["i"])

        prompt = PROMPT_TEMPLATE.format(lang_label=lang_label, locale=locale, payload=json.dumps(payload, ensure_ascii=False))

        url = GEMINI_URL_TEMPLATE.format(model=self.model)

        # retry loop per request
        last_err = None
        for attempt in range(self.max_retries):
            try:
                text = _post_gemini(url, self.api_key, prompt)
                self._last_call = time.time()
                arr = _json_from_text(text)
                if not isinstance(arr, list):
                    raise ValueError("Model did not return a JSON array")

                # Collect into dict by index
                returned: Dict[int, str] = {}
                for obj in arr:
                    if isinstance(obj, dict) and "i" in obj and "t" in obj:
                        try:
                            idx = int(obj["i"])
                            returned[idx] = str(obj["t"])
                        except Exception:
                            continue

                # Fill idx_to_tgt for any returned indices we actually asked for
                for i, tgt in returned.items():
                    if i in idx_to_src:
                        idx_to_tgt[i] = tgt

                # Compute missing (asked but not returned)
                missing = {i: s for i, s in idx_to_src.items() if i not in idx_to_tgt}
                if missing:
                    self.logger.warning(
                        f"Gemini returned {len(returned)} of {len(idx_to_src)} items; "
                        f"missing indices: {sorted(missing.keys())[:10]}{'...' if len(missing)>10 else ''}"
                    )
                return missing

            except Exception as e:
                last_err = e
                sleep = (1.5 ** attempt) + random.uniform(0, 0.6)
                self.logger.warning(f"Gemini request failed ({e}); retrying in {sleep:.1f}s")
                time.sleep(sleep)

        # On persistent failure, log and consider all items missing from this request
        self.logger.error(f"Gemini translation failed after retries: {last_err}")
        return dict(idx_to_src)
