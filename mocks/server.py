"""Two mock endpoints so the workflow runs end to end with no API key.

  POST /v1/chat/completions   OpenAI-compatible. Returns the structured JSON
                              a real model would return, derived by rules so
                              the demo is deterministic and repeatable.
  POST /api/job-posts         Stands in for the client's form API.
  GET  /api/job-posts         Everything submitted so far, for assertions.

Same idea as the offline stub in brandkit: a demo that needs a key is a demo
that stops working. Point LLM_URL at a real endpoint and nothing else changes.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

SUBMITTED = []

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

CHATTER = ("good morning", "thanks everyone", "shawarma", "hope you all")

LOCATIONS = [
    ("dubai", ["dubai", "دبي", "media city", "studio city"]),
    ("abu_dhabi", ["abu dhabi", "أبوظبي", "ابوظبي"]),
    ("sharjah", ["sharjah", "الشارقة", "الشارقه"]),
    ("ras_al_khaimah", ["rak", "ras al khaimah", "رأس الخيمة"]),
]
KINDS = [
    ("equipment", ["rent", "available for rent", "للإيجار", "inc lenses"]),
    ("venue", ["venue", "warehouse"]),
    ("casting", ["casting", "actor", "actress", "ممثل", "ممثلات", "kids"]),
    ("crew", ["gaffer", "spark", "makeup", "sound recordist", "pa's", "driver",
              "مصور", "سائق", "crew"]),
]


def _any_term(haystack: str, terms) -> bool:
    """Word boundaries, and the terms get the same normalisation the text got.
    Without boundaries "Parents" matched "rent" and a casting call came back
    as an equipment rental. Without normalising the terms, every Arabic
    keyword silently stopped matching once the text was normalised."""
    for term in terms:
        t = _norm(term).lower()
        if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", haystack):
            return True
    return False


def _norm(text: str) -> str:
    text = text.translate(_AR_DIGITS)
    text = re.sub("[أإآ]", "ا", text)   # alef variants
    text = text.replace("ى", "ي")                  # alef maqsura
    text = re.sub("[ً-ْـ]", "", text)         # diacritics, tatweel
    return text


def _language(text: str) -> str:
    """Majority of letters wins.

    An Arabic post naming a camera model is still an Arabic post. Treating any
    Latin character as evidence of mixed language sent those down the wrong
    branch, so "mixed" now needs the minority script to be a real share of the
    text rather than one model number.
    """
    arabic = len(re.findall(r"[\u0600-\u06ff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if arabic and latin and min(arabic, latin) / max(arabic, latin) > 0.25:
        return "mixed"
    if arabic > latin:
        return "ar"
    if re.search(r"\b(matloob|yom|shabab|ba3d|bokra|tasweer|el|l)\b",
                 text.lower()) and re.search(r"\b(fi|l|el)\b", text.lower()):
        return "arabizi"
    return "en"


def _money(text: str):
    """Ranges are stripped first. 'actor 25-35 ... AED 2500/day' read the age
    range as the fee until the eval caught it, which is the whole argument for
    running an eval instead of eyeballing a few messages."""
    low = _norm(text).lower()
    low = re.sub(r"\b\d{1,3}\s*-\s*\d{1,3}\b", " ", low)   # ages, "8-12"
    m = re.search(r"(\d+(?:\.\d+)?)\s*k\b", low)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r"(\d[\d,]{2,})", low)
    return float(m.group(1).replace(",", "")) if m else None


def _unit(text: str):
    low = _norm(text).lower()
    if re.search(r"/day|per day|/yom|لليوم|في اليوم|el yom", low):
        return "per_day"
    if re.search(r"/hour|per hour", low):
        return "per_hour"
    if "total" in low or "budget" in low:
        return "per_project"
    return None


def extract(text: str) -> dict:
    low = _norm(text).lower()
    if any(c in low for c in CHATTER) or len(text) < 25:
        return {"is_job_post": False, "post_type": "other",
                "language_detected": _language(text), "confidence": 0.95}
    kind = next((k for k, words in KINDS if _any_term(low, words)), "other")
    loc = next((c for c, words in LOCATIONS if _any_term(low, words)), None)
    amount = _money(text)
    return {
        "is_job_post": True,
        "post_type": kind,
        "role": None,
        "production_type": "advert" if "advert" in low or "tvc" in low else None,
        "location_canonical": loc,
        "location_raw": None,
        "pay_amount": amount,
        "pay_currency": "AED" if amount else None,
        "pay_unit": _unit(text),
        "shoot_date_raw": None,
        "contact_raw": None,
        "language_detected": _language(text),
        "confidence": 0.82,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/v1/chat/completions"):
            text = body["messages"][-1]["content"]
            marker = "MESSAGE:\n"
            if marker in text:
                text = text.split(marker, 1)[1]
            content = json.dumps(extract(text), ensure_ascii=False)
            return self._send(200, {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "model": body.get("model", "mock"),
            })
        if self.path.startswith("/api/job-posts"):
            SUBMITTED.append(body)
            return self._send(201, {"ok": True, "id": len(SUBMITTED)})
        self._send(404, {"error": "not found"})

    def do_GET(self):
        if self.path.startswith("/api/job-posts"):
            return self._send(200, {"count": len(SUBMITTED), "items": SUBMITTED})
        self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("mock LLM + API on http://127.0.0.1:8111", flush=True)
    HTTPServer(("127.0.0.1", 8111), Handler).serve_forever()
