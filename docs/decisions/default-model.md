# Decision: the default LLM model

**Status: draft, comparison not run yet.** Issue #14 answers the open question in
`product-spec.md` §13. The comparison needs real, paid AI calls through OpenRouter. On
2026-11-09 no API key was available, openrouter.ai was not reachable from the development
session, and spending was not yet approved. The sections marked *pending* are filled in after
the first run. Until then there is no chosen model and `.env.example` keeps `AI_MODEL` empty.

- Draft written: 2026-11-09
- Candidates checked with `check` (free, no AI call): 2026-11-09
- Comparison run: *pending*

## What is compared

Every candidate gets the same fixed test set through the production provider
(`OpenAICompatibleProvider`, issue #13). The prompts, the `provider: {"zdr": true}` routing,
the JSON parsing and the timeouts (15 s for suggestions, 60 s for summaries) are the ones
production uses. Each item gets exactly one call, with no retries.

For each candidate the results record:

| Result | How it is measured |
|---|---|
| Category matches | Suggested category equals the test set's expected category (automatic). |
| Tags in input language | A reviewer marks each suggestion's tags (see the review rules below). |
| Summary in input language | A reviewer marks each summary: is it in the language most of its entries use (§8)? |
| Valid JSON on the first try | The answer is a plain JSON object, which is what the provider accepts. A Markdown-fenced answer counts as invalid, as in production (open point from #13). Automatic. |
| Summary quality | A reviewer rates each summary 1–5 with the rubric below; the table shows the mean. |
| Median response time | Wall-clock time of each `suggest` and `summarise` call, median per operation. The suggestion median shows how close a model gets to the 15 s timeout; the SDK applies that timeout to each connection phase, not to the whole request (open point from #13). |
| Cost per suggestion and per summary | OpenRouter's `usage.cost` for each call, or the tokens times the highest ZDR endpoint price on the day of the run. Mean per operation. |

## Candidates

Requirements for a candidate:

- Available through OpenRouter on at least one zero-data-retention endpoint that does not
  keep prompts. ZDR endpoints with "safety retention" (the provider may keep prompts that its
  safety checks flag) do not count, because §8 asks for no retention. Models without such an
  endpoint are excluded and listed below with the reason.
- A small, fast model: suggestions must answer well within 15 s, and the global cap is 100
  requests a day.
- Good at following a JSON-only instruction, and at writing in English and German.

Proposed candidates, one per vendor. `check` on 2026-11-09 (OpenRouter's public `/models` and
`/endpoints/zdr` lists; no AI call) confirmed all five ids. Prices are in USD per million
tokens on 2026-11-09, at the highest-priced ZDR endpoint (the script's pessimistic choice).

| Model id | Why it is a candidate | ZDR endpoints on 2026-11-09 | Input / output price (2026-11-09) |
|---|---|---|---|
| `openai/gpt-5.4-mini` | OpenAI's small tier; strong instruction following and JSON output. | 2 (Azure), none with safety retention, both support `response_format` | $0.825 / $4.950 |
| `anthropic/claude-haiku-5.5` | Anthropic's small tier; careful summaries that stick to the input. | 6 (Google Vertex, Amazon Bedrock), none with safety retention, all support `response_format` | $0.110 / $0.550 |
| `mistralai/mistral-small-2603` | Mistral Small 4; low price, strong in European languages. | 3 (Mistral), none with safety retention, all support `response_format` | $0.165 / $0.660 |
| `google/gemini-3.8-flash` | Google's fast tier; strong multilingual output. | Excluded, see below | - |
| `qwen/qwen3.8-flash` | Qwen's fast tier; low price, served by several hosts. | Excluded, see below | - |

Not considered: large flagship models (much higher cost per call for short tasks) and
OpenRouter's `:free` variants (rate-limited and not meant for production).

Excluded (`check`, 2026-11-09):

- `google/gemini-3.8-flash`: all 4 of its ZDR endpoints (Google Vertex) have safety
  retention, so the provider may keep prompts that its safety checks flag. That is not zero
  data retention as §8 asks.
- `qwen/qwen3.8-flash`: no zero-data-retention endpoint.

The estimated cost of one run for the three remaining candidates was $0.18 on 2026-11-09
(about $0.15 for `openai/gpt-5.4-mini`, $0.02 each for the other two), using the token
estimate below and the highest ZDR prices.

## Test set

`backend/scripts/model_comparison/test_set.json`: 24 made-up entries, 12 in English and 12 in
German, three per category (Achievement, Learning, Feedback, Side project) in each language.
Every entry has an expected category, a date, tags and sometimes a Result/Impact. Four summary
cases: all English entries, all German entries, mostly English (6 + 2) and mostly German
(6 + 2). The entries contain no real people, companies or personal data; a unit test checks
for email addresses, phone numbers and links.

One candidate's run is 24 suggestions and 4 summaries. The script estimates it at most
about 10,800 input and 28,000 output tokens (pessimistic: 3 characters per token, and room for
reasoning tokens).

## Review rules and summary rubric

The reviewer fills in the `review` fields of each result file before `report` runs.

- `tags_in_input_language`: `true` when every suggested tag is in the entry's language, or is
  a name that does not belong to one language (a product, a technology such as "Kubernetes" or
  "SQL"). A failed suggestion is recorded as `false`.
- `in_input_language`: `true` when the summary is written in the case's expected language.
- `quality`, rated against the entries of the case:
  - **5**: every statement is backed by the entries, nothing is invented; the important
    entries, numbers and outcomes are there; well structured for a performance review; usable
    with light edits.
  - **4**: correct and useful, with small issues (some repetition, a minor fact missing,
    generic wording).
  - **3**: usable only after clear edits: an important entry or number is missing, the
    structure is weak, or the length does not fit.
  - **2**: a fact is invented or distorted, or several important entries are missing.
  - **1**: unusable: wrong language, mostly invented, empty, or the call failed.

## Results

*Pending.* `report` prints this table, with the date of the run:

| Model | Category matches | Tags in input language | Summary in input language | Valid JSON first try | Summary quality (1-5) | Median suggestion time | Median summary time | Cost per suggestion | Cost per summary | Max daily cost |
|---|---|---|---|---|---|---|---|---|---|---|

## Decision

*Pending:* the chosen model and the reasoning.

## Maximum daily cost

*Pending.* The estimate assumes that all 100 requests of the global daily cap (§8) are the
largest possible summary: 50,000 characters of entries plus the prompt as input and a
10,000-character summary plus the most reasoning tokens seen in the run as output, at
3 characters per token and the highest ZDR endpoint price on the day of the run. `report`
prints it for every candidate.

## How to re-run the comparison

Run by hand only; the automated tests and CI never call a real AI API. In `backend/`, with
`AI_API_KEY` set in the repository's `.env` (never committed):

```
# 1. Free: check the candidates' ids, ZDR endpoints and prices, and the estimated cost.
uv run --env-file ../.env python -m scripts.model_comparison check MODEL [MODEL ...]

# 2. Paid: run the test set on every usable candidate. Writes one JSON file per candidate
#    to scripts/model_comparison/results/<date>/.
uv run --env-file ../.env python -m scripts.model_comparison run MODEL [MODEL ...] --confirm-paid-calls

# 3. Fill in every "review" field in the result files (rules above).

# 4. Print the results table and the maximum daily cost.
uv run python -m scripts.model_comparison report scripts/model_comparison/results/<date>
```

`AI_BASE_URL` overrides the OpenRouter URL. `run.json` in the results folder records the
date, the candidates, the excluded models and SHA-256 hashes of the test set and both prompts,
so a later run shows whether the prompts changed. Re-run the comparison when the prompts
change, when a candidate is retired or a new small model appears, or when prices change
noticeably.
