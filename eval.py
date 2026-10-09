"""Score the extraction over the sample messages.

The job post asks for "a test report on at least 40 real messages". This is
that report, built before anyone asked for it. Fifteen messages here because
real ones have to come from the client's group; the harness does not care how
many there are.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
LLM = "http://127.0.0.1:8111/v1/chat/completions"
PROMPT = "MESSAGE:\n"


def ask(text: str) -> dict:
    request = urllib.request.Request(
        LLM,
        data=json.dumps({"model": "mock", "temperature": 0,
                         "messages": [{"role": "user", "content": PROMPT + text}]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(request, timeout=30).read())
    return json.loads(body["choices"][0]["message"]["content"])


def main() -> int:
    rows = [json.loads(l) for l in (ROOT / "samples" / "messages.jsonl").open(encoding="utf-8")]
    server = subprocess.Popen([sys.executable, str(ROOT / "mocks" / "server.py")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    try:
        exact = 0
        field_hits: dict = {}
        field_total: dict = {}
        print(f"{'id':<5}{'result':<8}{'lang':<9}disagreements")
        print("-" * 62)
        for row in rows:
            got = ask(row["text"])
            bad = {k: (v, got.get(k)) for k, v in row["expect"].items() if got.get(k) != v}
            for key, want in row["expect"].items():
                field_total[key] = field_total.get(key, 0) + 1
                field_hits[key] = field_hits.get(key, 0) + (got.get(key) == want)
            exact += not bad
            mark = "ok" if not bad else "MISS"
            detail = "" if not bad else ", ".join(
                f"{k}: want {w!r} got {g!r}" for k, (w, g) in bad.items())
            print(f"{row['id']:<5}{mark:<8}{got.get('language_detected',''):<9}{detail}")

        print(f"\nexact match on every expected field: {exact}/{len(rows)} "
              f"({exact / len(rows):.0%})\n")
        print("per field accuracy")
        for key in sorted(field_total, key=lambda k: field_hits[k] / field_total[k]):
            hits, total = field_hits[key], field_total[key]
            print(f"  {key:<22}{hits}/{total}  {hits / total:.0%}")
        return 0 if exact == len(rows) else 1
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
