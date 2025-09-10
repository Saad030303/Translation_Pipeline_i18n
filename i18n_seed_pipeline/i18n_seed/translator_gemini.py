import os, time, json, logging, random, re
from typing import List
import requests

from .translator_base import Translator

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

PROMPT_TEMPLATE = (
    "You are a professional software localization specialist.\n"
    "Translate the following list of strings into {lang_label} (locale={locale}).\n"
    "Strict rules:\n"
    "- Preserve placeholders exactly: tokens like __PH0__, __PH1__, "
    "curly braces {{...}}, double braces {{{{...}}}}, URLs, emails, "
    "Slack mentions <@U123>, channels <#C123|name>, emoji shortcodes :smile:, "
    "percent formats %s, %(name)s, env ${{VAR}}, and <tags>.\n"
    "- Do NOT add or remove lines; keep order.\n"
    "- Return a JSON array of translated strings only; no extra keys or commentary.\n"
    "Text to translate (JSON array):\n"
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

def _coerce_json_array(text: str) -> list:
    """Try hard to turn a Gemini text into a JSON array."""
    if not text:
        raise ValueError("Empty response text")
    s = text.strip()

    # strip fenced code blocks if present
    if s.startswith("```"):
        parts = s.split("```")
        # try to grab the first fenced payload
        for chunk in parts:
            chunk = chunk.strip()
            if chunk.startswith("[") and chunk.endswith("]"):
                s = chunk
                break

    # direct parse if already looks like array
    if s.startswith("["):
        try:
            return json.loads(s)
        except Exception:
            pass

    # try to extract the first top-level JSON array from text
    # (greedy match from first '[' to last ']')
    first = s.find("[")
    last = s.rfind("]")
    if first != -1 and last != -1 and last > first:
        candidate = s[first:last+1].strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # final attempt: sometimes the model returns lines separated by newlines;
    # only use this if every line is JSON-quoted (rare). Otherwise, give up.
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if lines and all((ln.startswith('"') and ln.endswith('"')) for ln in lines):
        try:
            return json.loads("[" + ",".join(lines) + "]")
        except Exception:
            pass

    raise ValueError(f"Could not parse JSON array from Gemini text (first 200 chars): {s[:200]!r}")

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

    def translate_batch(self, src_texts: List[str], target_locale: str) -> List[str]:
        self._respect_qps()
        lang_label = LANG_LABELS.get(target_locale, target_locale)
        payload = json.dumps(src_texts, ensure_ascii=False)
        prompt = PROMPT_TEMPLATE.format(lang_label=lang_label, locale=target_locale, payload=payload)

        url = GEMINI_URL_TEMPLATE.format(model=self.model)
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
            # You can add safetySettings here if your org policy requires
        }

        # retry logic
        last_err = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(url, headers=headers, params={"key": self.api_key}, json=body, timeout=90)
                self._last_call = time.time()
                if resp.status_code != 200:
                    self.logger.warning(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")
                    if resp.status_code in (429, 500, 502, 503, 504):
                        raise RuntimeError(f"Retryable HTTP {resp.status_code}")
                    raise RuntimeError(f"Non-retryable HTTP {resp.status_code}")

                data = resp.json()
                # Try all known spots where text may live
                text = None
                try:
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    # Some responses put JSON directly into a ground 'promptFeedback' or other area; dump a snippet for debugging
                    self.logger.debug(f"Unexpected Gemini structure, keys: {list(data.keys())}")
                    text = None

                if text is None:
                    # If nothing we can parse, log snippet and raise to retry
                    self.logger.warning(f"Gemini returned no text; body snippet: {resp.text[:200]}")
                    raise RuntimeError("Empty text")

                try:
                    arr = _coerce_json_array(text)
                except Exception as e:
                    # Log the raw text snippet for this attempt, then retry
                    self.logger.warning(f"Gemini JSON parse failed: {e}")
                    raise

                if not isinstance(arr, list) or len(arr) != len(src_texts):
                    raise RuntimeError(f"Gemini returned array length {len(arr)} vs expected {len(src_texts)}")

                return [str(x) for x in arr]

            except Exception as e:
                last_err = e
                sleep = (self.backoff_base ** attempt) + random.uniform(0, 0.7)
                self.logger.warning(f"Gemini request failed ({e}); retrying in {sleep:.1f}s")
                time.sleep(sleep)

        raise RuntimeError(f"Gemini translation failed after retries: {last_err}")




# import os, time, json, logging, random
# from typing import List
# import requests

# from .translator_base import Translator

# GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# PROMPT_TEMPLATE = (
#     "You are a professional software localization specialist.\n"
#     "Translate the following list of strings into {lang_label} (locale={locale}).\n"
#     "Strict rules:\n"
#     "- Preserve placeholders exactly: tokens like __PH0__, __PH1__, "
#     "curly braces {{...}}, double braces {{{{...}}}}, URLs, emails, "
#     "Slack mentions <@U123>, channels <#C123|name>, emoji shortcodes :smile:, "
#     "percent formats %s, %(name)s, env ${{VAR}}, and <tags>.\n"
#     "- Do NOT add or remove lines; keep order.\n"
#     "- Return **JSON array** of translated strings only; no extra keys or commentary.\n"
#     "Text to translate (JSON array):\n"
#     "{payload}\n"
# )

# LANG_LABELS = {
#     "pt_BR": "Portuguese (Brazil)",
#     "fr_FR": "French (France)",
#     "it_IT": "Italian (Italy)",
#     "de_DE": "German (Germany)",
#     "es_MX": "Spanish (Mexico)",
#     "zh_CN": "Chinese (Simplified)",
#     "zh_HK": "Chinese (Hong Kong)",
#     "zh_TW": "Chinese (Traditional)",
#     "ja_JP": "Japanese",
#     "ko_KR": "Korean",
#     "vi_VN": "Vietnamese",
#     "tr_TR": "Turkish",
#     "nl_NL": "Dutch",
#     "sv_SE": "Swedish",
#     "nb_NO": "Norwegian (Bokmal)",
#     "da_DK": "Danish",
# }

# class GeminiTranslator(Translator):
#     def __init__(self, model: str, qps: float = 1.0, max_retries: int = 5, backoff_base: float = 1.5, logger: logging.Logger | None = None):
#         self.model = model
#         self.api_key = os.getenv("GEMINI_API_KEY", "")
#         if not self.api_key:
#             raise RuntimeError("GEMINI_API_KEY environment variable is not set")
#         self.qps = qps
#         self.max_retries = max_retries
#         self.backoff_base = backoff_base
#         self.logger = logger or logging.getLogger("i18n-seed")
#         self._last_call = 0.0

#     def _respect_qps(self):
#         import time
#         min_interval = 1.0 / max(self.qps, 0.01)
#         dt = time.time() - self._last_call
#         if dt < min_interval:
#             time.sleep(min_interval - dt)

#     def translate_batch(self, src_texts: List[str], target_locale: str) -> List[str]:
#         self._respect_qps()
#         lang_label = LANG_LABELS.get(target_locale, target_locale)
#         payload = json.dumps(src_texts, ensure_ascii=False)
#         prompt = PROMPT_TEMPLATE.format(lang_label=lang_label, locale=target_locale, payload=payload)

#         url = GEMINI_URL_TEMPLATE.format(model=self.model)
#         headers = {"Content-Type": "application/json"}
#         body = {"contents": [{"parts": [{"text": prompt}]}]}

#         # retry logic
#         for attempt in range(self.max_retries):
#             try:
#                 resp = requests.post(url, headers=headers, params={"key": self.api_key}, json=body, timeout=60)
#                 self._last_call = time.time()
#                 if resp.status_code == 200:
#                     data = resp.json()
#                     try:
#                         text = data["candidates"][0]["content"]["parts"][0]["text"]
#                     except Exception as e:
#                         raise RuntimeError(f"Unexpected Gemini response: {data}") from e

#                     arr = json.loads(text)
#                     if not isinstance(arr, list) or len(arr) != len(src_texts):
#                         raise RuntimeError(f"Gemini returned unexpected array length {len(arr)} vs {len(src_texts)}")
#                     return [str(x) for x in arr]
#                 elif resp.status_code in (429, 500, 502, 503, 504):
#                     # backoff
#                     sleep = (self.backoff_base ** attempt) + random.uniform(0, 0.5)
#                     self.logger.warning(f"Gemini retryable HTTP {resp.status_code}; sleeping {sleep:.1f}s")
#                     time.sleep(sleep)
#                 else:
#                     raise RuntimeError(f"Gemini error {resp.status_code}: {resp.text}")
#             except Exception as e:
#                 sleep = (self.backoff_base ** attempt) + random.uniform(0, 0.5)
#                 self.logger.warning(f"Gemini request failed ({e}); retrying in {sleep:.1f}s")
#                 import time as _t; _t.sleep(sleep)

#         raise RuntimeError("Gemini translation failed after retries")
