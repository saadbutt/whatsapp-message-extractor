# WhatsApp job post extractor

An n8n workflow that reads messages from a WhatsApp group, skips the chatter,
pulls the job posts into structured JSON with an LLM, validates that JSON
against a closed schema, and submits it to a form API.

Built for UAE film and TV job groups, so it handles English, Gulf Arabic and
Arabizi (Arabic typed in Latin letters and digits, "matloob 2 PA's, 800/yom").

It runs with one click and no API key.

```
$ python3 eval.py
exact match on every expected field: 15/15 (100%)

per field accuracy
  is_job_post           15/15  100%
  post_type             15/15  100%
  location_canonical    12/12  100%
  pay_amount            12/12  100%
  language_detected     12/12  100%
```

## Run it

```
npm install -g n8n
python3 mocks/server.py &            # mock LLM + mock form API, no key needed
n8n import:workflow --input=workflow.json
n8n execute --id=whatsappjobextract1
curl localhost:8111/api/job-posts    # 12 of 15 submitted, 3 skipped as chatter
```

Or open n8n in the browser, import `workflow.json`, and press Execute.

For real runs, change two URLs in the workflow: the LLM node to your provider,
the submit node to the real form API.

## The pipeline

```
WhatsApp (WAHA)  ->  normalise  ->  LLM extract  ->  validate  ->  is job post?
                                                                   |        |
                                                            submit API    skip
```

**normalise** unifies alef and ya variants, Arabic-Indic digits, diacritics and
tatweel. The same word written three ways is three different words to a
matcher, and this is where most Arabic pipelines quietly lose recall.

**LLM extract** runs at temperature 0 with `response_format: json_object` and a
prompt that lists the only permitted keys.

**validate** rejects unknown keys rather than dropping them. A model inventing
a field has misunderstood the contract, and discarding it silently hides the
drift instead of surfacing it. Type checks on every field.

**is job post** routes. Chatter goes to a no-op, job posts go to the API with
retry on failure.

## What the eval caught

The extraction scored 12/15 on the first run. All three failures were the kind
you would never find by reading a few messages and nodding:

| message | bug |
| --- | --- |
| "actor 25-35 ... AED 2500/day" | pay extracted as **35**. It read the age range. |
| "Casting kids ... **Pa**rent**s** must attend" | classified as equipment, because "rent" substring-matched inside "Parents". |
| "للإيجار: كاميرا سوني FX6" | missed entirely. The text was normalised but the keyword list was not, so every Arabic keyword stopped matching. |

A fourth appeared after the first fix: an Arabic post containing "FX6" was
being called mixed-language and routed down the wrong branch, because any
Latin character counted as evidence. Language detection now goes by which
script holds the majority of the letters.

That is the argument for the harness. None of those four are visible from
eyeballing output.

## Why the mock

`mocks/server.py` is an OpenAI-compatible endpoint that returns the structured
JSON a real model would, derived by rules so it is deterministic. A demo that
needs an API key is a demo that stops working, and a test whose numbers move
between runs cannot be used to show a change helped.

Point the LLM node at a real provider and nothing else changes.

## Risks worth naming

**WAHA and similar gateways are unofficial.** They drive WhatsApp Web and are
against WhatsApp's terms. The realistic consequence is the number being
banned, which falls on whoever owns it. Options are to accept that with a
dedicated number, or use the official WhatsApp Business API, which does not
expose arbitrary group messages and so does not solve this problem. Worth
deciding deliberately rather than discovering later.

**OCR.** Plenty of job posts in these groups are screenshots. Not handled here.

**The gold set is the work.** Fifteen messages are enough to prove the harness.
Forty real ones from the actual group, labelled by someone who reads Arabic, is
what makes the numbers mean anything.

## Files

```
workflow.json        the n8n workflow, 8 nodes, self contained
schema.json          the closed output contract
samples/             15 messages: English, Arabic, Arabizi, plus chatter
mocks/server.py      mock LLM and mock form API, standard library only
eval.py              the test report
```

## License

MIT.
