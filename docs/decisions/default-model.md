# Decision: the default LLM model

**Chosen model:** `anthropic/claude-haiku-5.5`

Issue #14 answers the open question in `product-spec.md` §13 with a documented, repeatable
comparison. The product owner closes the question in the spec.

- Date of the comparison run: 2026-11-09 (UTC). All prices, costs and times below are from
  that day.
- Result files: `backend/scripts/model_comparison/results/2026-11-09/`
- Default set in `.env.example`: `AI_MODEL=anthropic/claude-haiku-5.5`

## Product owner decisions (2026-11-09)

1. **Strict zero-data-retention reading.** OpenRouter endpoints with the `safety_retention`
   flag do not count as zero data retention, because the provider may keep prompts its safety
   checks flag (§8).
2. **One paid run** of the comparison with exactly four models: `openai/gpt-5.4-mini`,
   `anthropic/claude-haiku-5.5`, `mistralai/mistral-small-2603` and
   `deepseek/deepseek-v4.1-flash`. No reruns: a candidate's failures are results.

## Candidates

Requirements for a candidate:

- Available through OpenRouter on at least one zero-data-retention endpoint without safety
  retention.
- A small, fast model: suggestions must answer well within 15 s, and the global cap is 100
  requests a day.
- Good at following a JSON-only instruction, and at writing in English and German.

`check` on 2026-11-09 (OpenRouter's public `/models` and `/endpoints/zdr` lists; no AI call).
Prices are USD per million tokens at the highest-priced ZDR endpoint, which is the script's
pessimistic choice.

| Model id | Why it is a candidate | ZDR endpoints (2026-11-09) | Input / output price (2026-11-09) |
|---|---|---|---|
| `openai/gpt-5.4-mini` | OpenAI's small tier; strong instruction following and JSON output. | 2 (Azure), none with safety retention, both support `response_format` | $0.825 / $4.950 |
| `anthropic/claude-haiku-5.5` | Anthropic's small tier; careful summaries that stick to the input. | 6 (Google Vertex, Amazon Bedrock), none with safety retention, all support `response_format` | $0.110 / $0.550 |
| `mistralai/mistral-small-2603` | Mistral Small 4; low price, strong in European languages. | 3 (Mistral), none with safety retention, all support `response_format` | $0.165 / $0.660 |
| `deepseek/deepseek-v4.1-flash` | Added as a spare after two exclusions; low price, 30 ZDR hosts. | 30 (BaseTen, Cohere, DeepInfra, Fireworks, Together and others), none with safety retention, 29 support `response_format` | $0.450 / $1.800 |

Excluded:

- `google/gemini-3.8-flash`: all 4 of its ZDR endpoints (Google Vertex) have safety retention,
  so none counts under the strict reading.
- `qwen/qwen3.8-flash`: no zero-data-retention endpoint.

Not considered: large flagship models (much higher cost per call for short tasks) and
OpenRouter's `:free` variants (rate-limited and not meant for production).

## Test set

`backend/scripts/model_comparison/test_set.json`: 24 made-up entries, 12 in English and 12 in
German, three per category (Achievement, Learning, Feedback, Side project) in each language.
Every entry has an expected category, a date, tags and sometimes a Result/Impact. Four summary
cases: all English entries (12), all German entries (12), mostly English (6 + 2 German) and
mostly German (6 + 2 English). The entries contain no real people, companies or personal
data; a unit test checks for email addresses, phone numbers and links.

## What is measured

Every candidate gets the same test set through the production provider
(`OpenAICompatibleProvider`, issue #13). The prompts, the `provider: {"zdr": true}` routing,
the JSON parsing and the timeouts (15 s for suggestions, 60 s for summaries) are the ones
production uses. Each item gets exactly one call, with no retries: 24 suggestions and 4
summaries per candidate.

| Result | How it is measured |
|---|---|
| Category matches | Suggested category equals the test set's expected category (automatic). |
| Tags in input language | Reviewed per suggestion (rules below). A failed call counts as no. |
| Summary in input language | Reviewed per summary: is it in the language most of its entries use (§8)? |
| Valid JSON on the first try | The answer is a plain JSON object, which is what the provider accepts. A Markdown-fenced answer counts as invalid, as in production (open point from #13). Automatic. |
| Summary quality | Each summary rated 1–5 with the rubric below; the table shows the mean of the four cases. |
| Median response time | Wall-clock time of each `suggest` and `summarise` call, median per operation. |
| Cost per suggestion and per summary | OpenRouter's `usage.cost` for each call, mean per operation. |

## Review rules and summary rubric

**Who reviewed:** the engineer agent (Claude, an AI), not the product owner, on 2026-11-09.
Every rating and a one-line reason are in the `review` fields of the result files, so each one
can be checked against the summary text next to it.

- Tags in input language: yes when every suggested tag is in the entry's language, or is a
  name that does not belong to one language (a product, a technology such as "Kubernetes" or
  "SQL") or a loanword in normal German use (such as "Onboarding").
- Summary in input language: yes when it is written in the case's expected language.
- Quality, rated against the entries of the case:
  - **5**: every statement is backed by the entries, nothing is invented; the important
    entries, numbers and outcomes are there; well structured for a performance review; usable
    with light edits.
  - **4**: correct and useful, with small issues (some repetition, a minor fact missing,
    generic wording).
  - **3**: usable only after clear edits: an important entry or number is missing, the
    structure is weak, or the length does not fit.
  - **2**: a fact is invented or distorted, or several important entries are missing.
  - **1**: unusable: wrong language, mostly invented, empty, or the call failed.

## Results (2026-11-09)

Printed by `report`:

| Model | Category matches | Tags in input language | Summary in input language | Valid JSON first try | Summary quality (1-5) | Median suggestion time | Median summary time | Cost per suggestion | Cost per summary | Max daily cost |
|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 24/24 | 24/24 | 4/4 | 24/24 | 4.8 | 1.2 s | 6.3 s | $0.00008 | $0.00084 | $0.41 |
| deepseek/deepseek-v4.1-flash | 24/24 | 24/24 | 4/4 | 24/24 | 4.8 | 1.4 s | 20.4 s | $0.00016 | $0.00296 | $1.97 |
| mistralai/mistral-small-2603 | 24/24 | 24/24 | 3/4 | 24/24 | 2.2 | 0.9 s | 5.8 s | $0.00004 | $0.00070 | $0.50 |
| openai/gpt-5.4-mini | 21/24 | 20/24 | 0/4 | 21/24 | 1.0 | 1.1 s | 0.2 s | $0.00028 | unknown | $3.04 |

Summary ratings (quality and reason; details in the result files):

| Case | claude-haiku-5.5 | deepseek-v4.1-flash | mistral-small-2603 | gpt-5.4-mini |
|---|---|---|---|---|
| sum-en-all | 5: all 12 entries, facts match | 5: all 12 entries, facts match | 4: facts match, one garbled sentence | 1: failed (HTTP 429) |
| sum-de-all | 5: all 12 entries, facts match | 4: facts match, repetitive "Mögliche Formulierungen" section | 2: invents that the load tests were run (input: prepared) and calls the bug "kritisch"; lists criticism under "Positives Feedback" | 1: failed (HTTP 429) |
| sum-mostly-en | 4: leaves out the side project on purpose (says so) | 5: all 8 entries, German ones translated correctly | 1: written in German; invents a "Python" app | 1: failed (HTTP 429) |
| sum-mostly-de | 5: all 8 entries, facts match | 5: all 8 entries, facts match | 2: invents that the sync "zuvor häufig abgebrochen wurde" | 1: failed (HTTP 429) |

Notes on the results:

- `openai/gpt-5.4-mini` was not fully measured. OpenRouter answered 7 of its 28 calls with
  HTTP 429 (rate limited): 3 suggestions and all 4 summaries. Under the one-run rule these
  count as failures. Its "median summary time" of 0.2 s is the time of those failures, and
  its summary cost is unknown. One of its successful suggestions (en-06) took 16.7 s, longer
  than the 15 s timeout. That is possible because the SDK applies the timeout to each
  connection phase, not to the whole request (open point from #13).
- The only tag outside the input's language was `openai/gpt-5.4-mini`'s "prototipo" (Spanish
  or Italian) for an English entry.
- `deepseek/deepseek-v4.1-flash` uses 1,600 to 3,400 reasoning tokens per summary. That is
  why its summaries take 17 to 34 s and cost about 3.5 times as much as Haiku's.
- `claude-haiku-5.5`'s slowest calls were 3.0 s for a suggestion and 8.2 s for a summary,
  well inside the 15 s and 60 s timeouts. Its longest summary had 2,607 characters (limit
  10,000). All its calls were served by Amazon Bedrock ZDR endpoints.
- Actual cost of the run: $0.0303, both as the sum of OpenRouter's `usage.cost` and as the
  key's usage on `/api/v1/key` after the run. The estimate from `check` was $0.24.

## Decision

**`anthropic/claude-haiku-5.5`** is the default model.

- It is the only candidate with a perfect score on every automatic and reviewed measure that
  the product depends on: 24/24 categories, valid JSON and tags in the input's language, and
  all four summaries in the right language.
- Its summaries share the best quality (4.8) with DeepSeek's, without invented facts. It is
  about 3.5 times cheaper per summary and about 3 times faster (6.3 s against 20.4 s median),
  because it does not spend thousands of reasoning tokens.
- `mistralai/mistral-small-2603` is a little cheaper per call, but it wrote one summary in the
  wrong language and invented facts in two others. That breaks §8 ("AI output follows the
  language of the user's input") and the prompt's "do not invent anything", so it is not
  acceptable. There is no trade-off between a cheaper acceptable model and a better one: the
  best model is also the cheapest acceptable one.
- `openai/gpt-5.4-mini` could not be fully measured because of rate limiting. It is the most
  expensive candidate (about 3.5 times Haiku per suggestion, 7 times its maximum daily cost),
  and it showed both rate limiting on its only ZDR endpoints and a suggestion over the 15 s
  timeout. A complete result could not make it a better default than Haiku.

## Maximum daily cost

At the global cap of 100 AI requests a day (§8), with `anthropic/claude-haiku-5.5`:
**about $0.41 a day** (prices of 2026-11-09).

This is the worst case: every request is the largest possible summary.

- Input: 50,000 characters of entries (§7.4) plus the prompt, at 3 characters per token,
  about 16,800 tokens at $0.110 per million.
- Output: a 10,000-character summary (§7.4), about 3,330 tokens, plus the most reasoning
  tokens seen in the run (679), at $0.550 per million.

A normal day costs far less: in this run a suggestion cost $0.00008 and a summary of 8 to 12
entries $0.00084.

## How to re-run the comparison

Run by hand only; the automated tests and CI never call a real AI API. A paid run needs the
product owner's approval (`AGENTS.md`). In `backend/`, with `AI_API_KEY` set in the
repository's `.env` (never committed), or added by the network proxy:

```
# 1. Free: check the candidates' ids, ZDR endpoints and prices, and the estimated cost.
uv run --env-file ../.env python -m scripts.model_comparison check MODEL [MODEL ...]

# 2. Paid: run the test set on every usable candidate. Writes one JSON file per candidate
#    to scripts/model_comparison/results/<date>/.
uv run --env-file ../.env python -m scripts.model_comparison run MODEL [MODEL ...] --confirm-paid-calls

# 3. Fill in every "review" field in the result files (rules above), and record who reviewed.

# 4. Print the results table and the maximum daily cost.
uv run python -m scripts.model_comparison report scripts/model_comparison/results/<date>
```

`AI_BASE_URL` overrides the OpenRouter URL. `run.json` in the results folder records the
date, the candidates, the excluded models and SHA-256 hashes of the test set and both prompts,
so a later run shows whether the prompts changed. Re-run the comparison when the prompts
change, when the chosen model is retired or a new small model appears, or when prices change
noticeably.
