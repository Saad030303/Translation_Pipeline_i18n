# # i18n_seed/translator_gemini.py
# from __future__ import annotations
# import os, time, json, logging, random
# from typing import List, Dict, Any, Tuple
# import requests

# from .translator_base import Translator

# GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# # IMPORTANT: all *literal* braces are doubled to survive .format()
# PROMPT_TEMPLATE = (
#     "You are a professional software localization specialist.\n"
#     "{domain_rules}"
#     "Translate the following items into {lang_label} (locale={locale}).\n"
#     "STRICT RULES:\n"
#     "1) Preserve placeholders exactly: __PH0__, __PH1__, {{}}{{}}-style templates like {{{{{{name}}}}}}, URLs, emails, "
#     "<@U123>, <#C123|name>, emoji :smile:, %s, %(name)s, ${{{{VAR}}}}, and <tags>.\n"
#     "2) Do NOT add/remove/reorder items.\n"
#     "3) If an item is code/enum or otherwise untranslatable, return it unchanged.\n"
#     "4) Output MUST be a JSON array of objects: [{{{{\"i\": 0, \"t\": \"...\"}}}}, {{{{\"i\": 1, \"t\": \"...\"}}}}, ...]\n"
#     "INPUT JSON (array of objects: {{{{\"i\": <int>, \"t\": <string>}}}}):\n"
#     "{payload}\n"
# )

# # PROMPT_TEMPLATE = (
# #     "You are a professional e-commerce localization specialist for Amazon listings.\n"
# #     "\n"
# #     "# GOAL:\n"
# #     "- Translate the input items into native, natural {lang_label} for locale={locale}.\n"
# #     "- Use correct local grammar/word order and common retail phrasing for the locale.\n"
# #     "\n"
# #     "# STRICT OUTPUT FORMAT:\n"
# #     "- Return JSON ONLY: a single array of objects like this: "
# #     "[{{\"i\": <int>, \"t\": <string>}}]\n"
# #     "- Return exactly one object for every input index you receive; do not add, drop, merge, split, renumber, or reorder.\n"
# #     "- Do NOT wrap in code fences. Do NOT add any commentary.\n"
# #     "\n"
# #     "# DOMAIN RULES (MUST FOLLOW):\n"
# #     "1) Translate PRODUCT TYPES written in UPPER_SNAKE_CASE into natural target-language phrases.\n"
# #     "   - Example to french: RUNNING_SHOES -> Chaussures de course (French), SPORT_WATER_BOTTLE -> Bouteille d'eau de sport.\n"
# #     "2) Translate SIZE / GENDER words: \"Men's\", \"Women's\", \"Unisex\", \"Size\", \"Kids'\", \"Boys'\", \"Girls'\".\n"
# #     "   - Keep numbers and units unchanged. Ex fr: \"Men's 9.5\" -> \"Homme 9.5\"; \"Size 10\" -> \"Taille 10\".\n"
# #     "3) Preserve EXACTLY (do not translate or alter):\n"
# #     "   - SKUs / model codes (e.g., EF-FLX-6030-WHT-MP), ASIN/UPC/EAN/ISBN, marketplace IDs (e.g., ATVPDKIKX0DER),\n"
# #     "   - URLs, emails,\n"
# #     "   - Placeholders: %s, %(name)s, {{var}}, __PH0__, __PH1__, and any <tags>,\n"
# #     "   - All numbers and measurement tokens: dimensions/capacities/units (cm, mm, in, \", km, mi, lb, kg, g, L, oz, %, +, –).\n"
# #     "4) If an input is purely a code/ID/enum with no human-language content, return it unchanged.\n"
# #     "5) Be concise and commercial; do not hallucinate new facts; never remove protected tokens.\n"
# #     "\n"
# #     "# INPUT JSON (array of objects: {{\"i\": <int>, \"t\": <string>}}):\n"
# #     "{payload}\n"
# # )

# # Simpler fallback prompt (list-of-strings), also fully escaped
# PROMPT_SIMPLE_LIST = (
#     "Translate into {lang_label} (locale={locale}) the following list of strings.\n"
#     "{domain_rules}"
#     "Rules: preserve placeholders; do not reorder; return a JSON array of strings.\n"
#     "INPUT JSON (array of strings):\n"
#     "{payload}\n"
# )

# LANG_LABELS = {
#     "pt_BR": "Portuguese (Brazil)", "fr_FR": "French (France)", "it_IT": "Italian (Italy)",
#     "de_DE": "German (Germany)", "es_MX": "Spanish (Mexico)", "zh_CN": "Chinese (Simplified)",
#     "zh_HK": "Chinese (Hong Kong)", "zh_TW": "Chinese (Traditional)", "ja_JP": "Japanese",
#     "ko_KR": "Korean", "vi_VN": "Vietnamese", "tr_TR": "Turkish", "nl_NL": "Dutch",
#     "sv_SE": "Swedish", "nb_NO": "Norwegian (Bokmal)", "da_DK": "Danish",
# }

# def _strip_code_fence(s: str) -> str:
#     s = s.strip()
#     if s.startswith("```"):
#         parts = s.split("```")
#         for p in parts:
#             p = p.strip()
#             if p.startswith("[") and p.endswith("]"):
#                 return p
#     return s

# def _json_from_text(s: str) -> Any:
#     s = _strip_code_fence(s)
#     # try direct
#     try:
#         return json.loads(s)
#     except Exception:
#         pass
#     # greedy bracket slice
#     first, last = s.find("["), s.rfind("]")
#     if first != -1 and last != -1 and last > first:
#         cand = s[first:last+1].strip()
#         return json.loads(cand)
#     # let it raise
#     return json.loads(s)

# def _post_gemini(url: str, api_key: str, prompt: str, timeout: int = 90) -> str:
#     headers = {"Content-Type": "application/json"}
#     body = {
#         "contents": [{
#             "role": "user",
#             "parts": [{"text": prompt}]
#         }],
#         "generationConfig": {
#             "temperature": 0,
#             "response_mime_type": "application/json"
#         }
#     }
#     resp = requests.post(url, headers=headers, params={"key": api_key}, json=body, timeout=timeout)
#     if resp.status_code != 200:
#         raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
#     data = resp.json()
#     try:
#         return data["candidates"][0]["content"]["parts"][0]["text"]
#     except Exception:
#         raise RuntimeError(f"Unexpected response: {str(data)[:200]}")

# class GeminiTranslator(Translator):
#     def __init__(
#         self,
#         model: str,
#         qps: float = 1.0,
#         max_retries: int = 5,
#         backoff_base: float = 1.5,
#         logger: logging.Logger | None = None,
#         domain_rules: str = "",
#     ):
#         self.model = model
#         self.api_key = os.getenv("GEMINI_API_KEY", "")
#         if not self.api_key:
#             raise RuntimeError("GEMINI_API_KEY environment variable is not set")
#         self.qps = qps
#         self.max_retries = max_retries
#         self.backoff_base = backoff_base
#         self.logger = logger or logging.getLogger("i18n-seed")
#         self.domain_rules = (domain_rules or "").rstrip() + ("\n" if domain_rules else "")
#         self._last_call = 0.0

#     def _respect_qps(self):
#         min_interval = 1.0 / max(self.qps, 0.01)
#         dt = time.time() - self._last_call
#         if dt < min_interval:
#             time.sleep(min_interval - dt)

#     # ---------------- public API ----------------

#     def translate_batch(self, src_texts: List[str], target_locale: str) -> List[str]:
#         """
#         Returns translations in the *same order* as src_texts.
#         Self-heals when some items are dropped by retrying only the missing ones.
#         Any irrecoverable gaps fall back to identity (source).
#         """
#         idx_to_src = {i: s for i, s in enumerate(src_texts)}
#         idx_to_tgt: Dict[int, str] = {}

#         self._request_with_heal(idx_to_src, idx_to_tgt, target_locale)

#         # Final assembly: identity fallback if anything remains missing
#         out: List[str] = []
#         for i in range(len(src_texts)):
#             out.append(idx_to_tgt.get(i, src_texts[i]))
#         return out

#     # ---------------- internals ----------------

#     def _request_with_heal(self, idx_to_src: Dict[int, str], idx_to_tgt: Dict[int, str], locale: str):
#         pending = dict(idx_to_src)

#         # full batch
#         missing = self._one_request_and_collect(pending, idx_to_tgt, locale)
#         if not missing:
#             return

#         # half batches
#         if len(missing) > 1:
#             items = sorted(missing.items())  # [(i, text), ...]
#             mid = len(items) // 2
#             left = dict(items[:mid])
#             right = dict(items[mid:])
#             miss_left = self._one_request_and_collect(left, idx_to_tgt, locale)
#             todo_right = dict(right); todo_right.update(miss_left)
#             missing = self._one_request_and_collect(todo_right, idx_to_tgt, locale)

#         # singles
#         for i, s in list(missing.items()):
#             _ = self._one_request_and_collect({i: s}, idx_to_tgt, locale)

#     def _format_prompt_objects(self, objs: List[Dict[str, Any]], locale: str) -> str:
#         lang_label = LANG_LABELS.get(locale, locale)
#         prompt = PROMPT_TEMPLATE.format(
#             lang_label=lang_label,
#             locale=locale,
#             domain_rules=self.domain_rules,
#             payload=json.dumps(objs, ensure_ascii=False),
#         )
#         return prompt

#     def _format_prompt_list(self, items: List[str], locale: str) -> str:
#         lang_label = LANG_LABELS.get(locale, locale)
#         prompt = PROMPT_SIMPLE_LIST.format(
#             lang_label=lang_label,
#             locale=locale,
#             domain_rules=self.domain_rules,
#             payload=json.dumps(items, ensure_ascii=False),
#         )
#         return prompt

#     def _collect_from_array(
#         self,
#         arr: Any,
#         asked_indices: List[int],
#         idx_to_tgt: Dict[int, str],
#         idx_to_src: Dict[int, str],
#     ) -> None:
#         """
#         Accepts either:
#           - list of {"i": int, "t": str}
#           - list of strings (positionally aligned to asked_indices)
#         Adds collected items into idx_to_tgt.
#         """
#         if not isinstance(arr, list):
#             raise ValueError("Model did not return a JSON array")

#         # objects path
#         got_any = False
#         for obj in arr:
#             if isinstance(obj, dict) and "i" in obj and "t" in obj:
#                 try:
#                     idx = int(obj["i"])
#                     if idx in asked_indices:
#                         idx_to_tgt[idx] = str(obj["t"])
#                         got_any = True
#                 except Exception:
#                     continue

#         if got_any:
#             return

#         # simple list fallback (positional)
#         if len(arr) == len(asked_indices) and all(not isinstance(x, dict) for x in arr):
#             for pos, idx in enumerate(asked_indices):
#                 try:
#                     idx_to_tgt[idx] = str(arr[pos])
#                 except Exception:
#                     idx_to_tgt[idx] = idx_to_src[idx]
#             return

#         # partial simple list (still try to map what we can)
#         if arr and all(not isinstance(x, dict) for x in arr):
#             upto = min(len(arr), len(asked_indices))
#             for pos in range(upto):
#                 idx = asked_indices[pos]
#                 try:
#                     idx_to_tgt[idx] = str(arr[pos])
#                 except Exception:
#                     idx_to_tgt[idx] = idx_to_src[idx]
#             return

#         # else: nothing mappable

#     def _one_request_and_collect(self, idx_to_src: Dict[int, str], idx_to_tgt: Dict[int, str], locale: str) -> Dict[int, str]:
#         """
#         Sends one request for the given subset of items.
#         Returns a dict of {idx: src} for items still missing after this attempt.
#         """
#         if not idx_to_src:
#             return {}

#         self._respect_qps()

#         # 1) primary request: objects with indices
#         objs = [{"i": i, "t": s} for i, s in sorted(idx_to_src.items())]
#         prompt = self._format_prompt_objects(objs, locale)
#         url = GEMINI_URL_TEMPLATE.format(model=self.model)

#         last_err = None
#         for attempt in range(self.max_retries):
#             try:
#                 text = _post_gemini(url, self.api_key, prompt)
#                 self._last_call = time.time()
#                 arr = _json_from_text(text)
#                 asked_indices = [i for i, _ in sorted(idx_to_src.items())]
#                 before = set(idx_to_tgt.keys())
#                 self._collect_from_array(arr, asked_indices, idx_to_tgt, idx_to_src)

#                 after = set(idx_to_tgt.keys())
#                 missing = {i: s for i, s in idx_to_src.items() if i not in after}
#                 if missing:
#                     self.logger.warning(
#                         f"Gemini returned {len(after - before)} of {len(idx_to_src)} items; "
#                         f"missing indices: {sorted(missing.keys())[:10]}{'...' if len(missing)>10 else ''}"
#                     )
#                 return missing
#             except Exception as e:
#                 last_err = e
#                 sleep = (self.backoff_base ** attempt) + random.uniform(0, 0.6)
#                 self.logger.warning(f"Gemini request failed ({e}); retrying in {sleep:.1f}s")
#                 time.sleep(sleep)

#         # 2) secondary request: simple list (positional)
#         try:
#             items = [s for _, s in sorted(idx_to_src.items())]
#             prompt2 = self._format_prompt_list(items, locale)
#             text = _post_gemini(url, self.api_key, prompt2)
#             self._last_call = time.time()
#             arr = _json_from_text(text)
#             asked_indices = [i for i, _ in sorted(idx_to_src.items())]
#             before = set(idx_to_tgt.keys())
#             self._collect_from_array(arr, asked_indices, idx_to_tgt, idx_to_src)
#             after = set(idx_to_tgt.keys())
#             missing = {i: s for i, s in idx_to_src.items() if i not in after}
#             if missing:
#                 self.logger.warning(
#                     f"Gemini (simple-list) returned {len(after - before)} of {len(idx_to_src)}; "
#                     f"missing indices: {sorted(missing.keys())[:10]}{'...' if len(missing)>10 else ''}"
#                 )
#             # Final hard fallback: identity for any still-missing
#             if missing:
#                 for i, s in missing.items():
#                     idx_to_tgt[i] = s
#                     self.logger.warning(f"Falling back to source text for idx {i} after retries.")
#             return {}
#         except Exception as e:
#             # Hard fail: identity for all in this request
#             self.logger.error(f"Gemini translation failed after retries: {e}")
#             for i, s in idx_to_src.items():
#                 idx_to_tgt[i] = s
#             return {}

# i18n_seed/translator_gemini.py
from __future__ import annotations
import os, time, json, logging, random
from typing import List, Dict, Any
import requests

from .translator_base import Translator

GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Double all literal braces; only {lang_label}, {locale}, {payload}, {domain_rules} are formatting slots.
# PROMPT_TEMPLATE = (
#     "You are a professional software localization specialist.\n"
#     "{domain_rules}"
#     "Translate the following items into {lang_label} (locale={locale}).\n"
#     "STRICT RULES:\n"
#     "- Preserve placeholders exactly: __PH0__, __PH1__, URLs, emails, SKUs, marketplace IDs, %s, %(name)s, ${{VAR}}, and <tags>.\n"
#     "- Do NOT add/remove/reorder items.\n"
#     "- Preserve same text format for example translating RUNNING_SHOES to french should be CHAUSSURES_DE_COURSE\n"
#     "- Output MUST be a JSON array of objects like: [{{\"i\": 0, \"t\": \"...\"}}, {{\"i\": 1, \"t\": \"...\"}}, ...]\n"
#     "INPUT JSON (array of objects with keys {{\"i\"}} and {{\"t\"}}):\n"
#     "{payload}\n"
# )

PROMPT_TEMPLATE = (
    "# You are a professional software localization specialist.\n"
    "# Translate the following english items into {lang_label} (locale={locale}).\n"
    # "{domain_rules}"
    "# STRICT RULES:\n"
    "- Do NOT translate codes/identifiers: AFN, MFN, FBA, FBM, SKUs, marketplace IDs, emails, URLs, %s, "
    "- Preserve placeholders exactly: __PH0__, __PH1__, URLs, emails, SKUs, marketplace IDs, %s, %(name)s, "
    "- MUST TRANSLATE title and item name for example translating `Nike Running Shoes 300` to french should be `Chaussures de course Nike 300`\n"
    "- Translate PRODUCT TYPES for example if french [\"SHOES\"] should be [\"CHAUSSURES\"] preserving the format\n"
    "- MUST TRANSLATE PROJECT TYPE for example translating `SHOES` to french should be CHAUSSURES\n"
    "- Preserve the source text's casing and separators EXACTLY\n"
    "- Do NOT add/remove/reorder items.\n"
    "- Output MUST be a JSON array of objects like: [{{\"i\": 0, \"t\": \"...\"}}, {{\"i\": 1, \"t\": \"...\"}}, ...]\n"
    "INPUT JSON (array of objects with keys {{\"i\"}} and {{\"t\"}}):\n"
    "{payload}\n"
)

# PROMPT_TEMPLATE = (
#     "You are a professional software localization engine.\n"
#     "Translate EACH item faithfully into {lang_label} (locale={locale}).\n"
#     "ABSOLUTE RULES (must follow ALL):\n"
#     "• Output ONLY a JSON array (no text before/after, no code fences).\n"
#     "• Do NOT add, explain, warn, summarize, or insert meta text of any kind.\n"
#     "• Do NOT change item order; preserve each input index \"i\" exactly.\n"
#     "• Preserve placeholders and non-linguistic tokens: __PH0__, __PH1__, URLs, emails, SKUs, marketplace IDs, %s, %(name)s, <tags>.\n"
#     "• Translate retail-facing strings (names, titles, descriptions, product types). Keep brand names and model codes unchanged.\n"
#     "• Keep punctuation and casing from the source unless ungrammatical in target.\n"
#     "• NEVER add phrases like \"refer to the listing for details\", \"does not specify\", \"note:\", \"disclaimer\", etc.\n"
#     "FORMAT:\n"
#     "[{{\"i\": 0, \"t\": \"<translation>\"}}, {{\"i\": 1, \"t\": \"<translation>\"}}, ...]\n"
#     "INPUT (array of objects with keys {{\"i\"}} and {{\"t\"}}) — translate ONLY the \"t\" values:\n"
#     "<PAYLOAD>\n"
#     "{payload}\n"
#     "</PAYLOAD>\n"
# )

PROMPT_SIMPLE_LIST = PROMPT_TEMPLATE

# PROMPT_SIMPLE_LIST = (
#     "{domain_rules}"
#     "Translate into {lang_label} (locale={locale}) the following list of strings.\n"
#     "Rules: preserve placeholders; do not reorder; return a JSON array of strings.\n"
#     "INPUT JSON (array of strings):\n"
#     "{payload}\n"
# )

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
        for p in parts:
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                return p
    return s

def _json_from_text(s: str) -> Any:
    s = _strip_code_fence(s)
    try:
        return json.loads(s)
    except Exception:
        pass
    first, last = s.find("["), s.rfind("]")
    if first != -1 and last != -1 and last > first:
        cand = s[first:last+1].strip()
        return json.loads(cand)
    return json.loads(s)

def _post_gemini(url: str, api_key: str, prompt: str, timeout: int = 90) -> str:
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {"temperature": 0, "response_mime_type": "application/json"}
    }
    resp = requests.post(url, headers=headers, params={"key": api_key}, json=body, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError(f"Unexpected response: {str(data)[:200]}")

class GeminiTranslator(Translator):
    def __init__(self, model: str, qps: float = 1.0, max_retries: int = 5, backoff_base: float = 1.5, logger: logging.Logger | None = None, domain_rules: str = ""):
        self.model = model
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set")
        self.qps = qps
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.logger = logger or logging.getLogger("i18n-seed")
        self.domain_rules = (domain_rules or "").rstrip() + ("\n" if domain_rules else "")
        self._last_call = 0.0

    def _respect_qps(self):
        min_interval = 1.0 / max(self.qps, 0.01)
        dt = time.time() - self._last_call
        if dt < min_interval:
            time.sleep(min_interval - dt)

    def translate_batch(self, src_texts: List[str], target_locale: str) -> List[str]:
        idx_to_src = {i: s for i, s in enumerate(src_texts)}
        idx_to_tgt: Dict[int, str] = {}
        self._request_with_heal(idx_to_src, idx_to_tgt, target_locale)
        return [idx_to_tgt.get(i, src_texts[i]) for i in range(len(src_texts))]

    def _request_with_heal(self, idx_to_src: Dict[int, str], idx_to_tgt: Dict[int, str], locale: str):
        pending = dict(idx_to_src)
        missing = self._one_request_and_collect(pending, idx_to_tgt, locale)
        if not missing: return
        if len(missing) > 1:
            items = sorted(missing.items())
            mid = len(items) // 2
            left = dict(items[:mid]); right = dict(items[mid:])
            miss_left = self._one_request_and_collect(left, idx_to_tgt, locale)
            todo_right = dict(right); todo_right.update(miss_left)
            missing = self._one_request_and_collect(todo_right, idx_to_tgt, locale)
        for i, s in list(missing.items()):
            _ = self._one_request_and_collect({i: s}, idx_to_tgt, locale)

    def _fmt_prompt_objs(self, objs: List[Dict[str, Any]], locale: str) -> str:
        lang_label = LANG_LABELS.get(locale, locale)
        return PROMPT_TEMPLATE.format(
            lang_label=lang_label, locale=locale,
            payload=json.dumps(objs, ensure_ascii=False),
            domain_rules=self.domain_rules
        )

    def _fmt_prompt_list(self, items: List[str], locale: str) -> str:
        lang_label = LANG_LABELS.get(locale, locale)
        return PROMPT_SIMPLE_LIST.format(
            lang_label=lang_label, locale=locale,
            payload=json.dumps(items, ensure_ascii=False),
            domain_rules=self.domain_rules
        )

    def _collect_from_array(self, arr: Any, asked_indices: List[int], idx_to_tgt: Dict[int, str], idx_to_src: Dict[int, str]) -> None:
        if not isinstance(arr, list):
            raise ValueError("Model did not return a JSON array")
        # objects path
        got = False
        for obj in arr:
            if isinstance(obj, dict) and "i" in obj and "t" in obj:
                try:
                    i = int(obj["i"])
                    if i in asked_indices:
                        idx_to_tgt[i] = str(obj["t"])
                        got = True
                except Exception:
                    continue
        if got: return
        # simple positional list
        if len(arr) == len(asked_indices) and all(not isinstance(x, dict) for x in arr):
            for pos, i in enumerate(asked_indices):
                try:
                    idx_to_tgt[i] = str(arr[pos])
                except Exception:
                    idx_to_tgt[i] = idx_to_src[i]
            return
        if arr and all(not isinstance(x, dict) for x in arr):
            upto = min(len(arr), len(asked_indices))
            for pos in range(upto):
                i = asked_indices[pos]
                try:
                    idx_to_tgt[i] = str(arr[pos])
                except Exception:
                    idx_to_tgt[i] = idx_to_src[i]
            return
        # else: nothing mappable

    def _one_request_and_collect(self, idx_to_src: Dict[int, str], idx_to_tgt: Dict[int, str], locale: str) -> Dict[int, str]:
        if not idx_to_src: return {}
        self._respect_qps()
        objs = [{"i": i, "t": s} for i, s in sorted(idx_to_src.items())]
        prompt = self._fmt_prompt_objs(objs, locale)
        url = GEMINI_URL_TEMPLATE.format(model=self.model)

        last_err = None
        for attempt in range(self.max_retries):
            try:
                text = _post_gemini(url, self.api_key, prompt)
                self._last_call = time.time()
                arr = _json_from_text(text)
                asked = [i for i, _ in sorted(idx_to_src.items())]
                before = set(idx_to_tgt.keys())
                self._collect_from_array(arr, asked, idx_to_tgt, idx_to_src)
                after = set(idx_to_tgt.keys())
                missing = {i: s for i, s in idx_to_src.items() if i not in after}
                if missing:
                    self.logger.warning(
                        f"Gemini returned {len(after - before)} of {len(idx_to_src)} items; "
                        f"missing indices: {sorted(missing.keys())[:10]}{'...' if len(missing)>10 else ''}"
                    )
                return missing
            except Exception as e:
                last_err = e
                sleep = (self.backoff_base ** attempt) + random.uniform(0, 0.6)
                self.logger.warning(f"Gemini request failed ({e}); retrying in {sleep:.1f}s")
                time.sleep(sleep)

        # fallback: simple list prompt
        try:
            items = [s for _, s in sorted(idx_to_src.items())]
            prompt2 = self._fmt_prompt_list(items, locale)
            text = _post_gemini(url, self.api_key, prompt2)
            self._last_call = time.time()
            arr = _json_from_text(text)
            asked = [i for i, _ in sorted(idx_to_src.items())]
            before = set(idx_to_tgt.keys())
            self._collect_from_array(arr, asked, idx_to_tgt, idx_to_src)
            after = set(idx_to_tgt.keys())
            missing = {i: s for i, s in idx_to_src.items() if i not in after}
            if missing:
                self.logger.warning(
                    f"Gemini (simple-list) returned {len(after - before)} of {len(idx_to_src)}; "
                    f"missing indices: {sorted(missing.keys())[:10]}{'...' if len(missing)>10 else ''}"
                )
            if missing:
                for i, s in missing.items():
                    idx_to_tgt[i] = s
                    self.logger.warning(f"Falling back to source text for idx {i} after retries.")
            return {}
        except Exception as e:
            self.logger.error(f"Gemini translation failed after retries: {e}")
            for i, s in idx_to_src.items():
                idx_to_tgt[i] = s
            return {}
