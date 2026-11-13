# Winlog: Product Specification

**Version:** 0.2 (draft)
**Last updated:** 11 November 2026

---

## 1. Overview

Winlog is a personal success diary for professionals. It makes it easy to record work achievements, learnings and feedback as they happen, and turns these records into summaries for performance reviews and appraisal conversations.

Winlog is a responsive web app that works in desktop and mobile browsers.

## 2. Problem

When review time comes, most people struggle to remember what they achieved over the past months. Achievements go unrecorded because writing them down feels like extra work, and existing notes tend to be scattered and unstructured. As a result, people undersell their work in reviews and interviews.

## 3. Goals

- Capturing an entry takes less than a minute.
- Entries can be filtered and grouped by period, category and tags.
- A selection of entries can be turned into a review-ready summary that the user can edit and keep.
- The app stays fully usable when the AI is unavailable.
- Users stay in control of their data: they can edit, export and delete it.

## 4. Non-goals (v1)

- Native mobile apps and push notifications
- Splitting one text into several entries
- Sharing entries or summaries with other users
- Long-term pattern analysis across entries
- Single sign-on (SSO)
- Renaming, merging or deleting tags by hand (tags that no entry uses are hidden instead, see 7.2)

## 5. Target users

Individual professionals who want a lightweight record of their work so they can prepare for performance reviews, appraisal talks and job interviews. Each user works only with their own data.

## 6. Core concepts

| Concept | Description |
|---|---|
| **Entry** | One record of something that happened at work. It is written as free text and has a date, one category, optional tags and an optional result or impact. |
| **Category** | One value from a fixed list: *Achievement*, *Learning*, *Feedback*, *Side project*. Every entry has exactly one category. |
| **Tag** | A label created by the user. An entry can have up to 10 tags. Tag names ignore upper- and lower-case, so `python` and `Python` are the same tag. |
| **Summary** | AI-generated text that describes the entries matching a filter (period, categories, tags). Summaries are saved and can be edited. |

---

## 7. Functional requirements

### 7.1 Accounts

- **FR-A1** Users can register with an email address and a password. Email addresses ignore upper- and lower-case. A password has 10–128 characters and contains at least one uppercase letter, one digit and one special character (any character that is not a letter or a digit). After registering, the user is logged in.
- **FR-A2** Users can log in and log out. A login lasts 7 days by default (configurable) or until the user logs out.
- **FR-A3** Users can only access their own entries, tags and summaries.
- **FR-A4** Repeated failed logins are slowed down. After 10 failed attempts for one email within 15 minutes, further attempts for that email are refused for the rest of that window. Demo logins are limited to 20 per hour from one visitor's IP address. Both limits are configurable.

**Acceptance criteria**
- A user cannot read, change or delete another user's data through the UI or the API.
- Requests without valid authentication are rejected.
- A wrong email and a wrong password give the same error, so login does not reveal whether an account exists.
- Logging out ends only the current login; the user stays logged in on other devices.

### 7.2 Capturing entries

- **FR-E1** A user creates an entry by writing free text. One text always creates exactly one entry.
- **FR-E2** Each entry has:
  - a date (required; the form pre-fills today's date in the user's own time zone, and any date is accepted, including future dates)
  - exactly one category
  - up to 10 tags
  - an optional *Result/Impact* field
- **FR-E3** Users can create new tags while writing an entry. Tag names are trimmed and ignore upper- and lower-case; a tag keeps the spelling it was first created with.
- **FR-E4** Users can edit and delete their entries.

**Acceptance criteria**
- An entry can be saved without using AI suggestions.
- An entry cannot be saved without text, date and category. Text that is empty or only whitespace counts as missing.
- Entry text is at most 2,000 characters, Result/Impact at most 500 characters, and a tag name at most 40 characters.
- Tags that no entry uses any more are hidden from autocomplete and filters. They come back when an entry uses them again.
- Editing or deleting an entry never changes a saved summary.

### 7.3 AI suggestions for category and tags

- **FR-S1** After the user writes the text, the app can request AI suggestions for category and tags.
- **FR-S2** Suggestions pre-fill only the fields the user has not filled in yet; they never override the user's own choices. Nothing is saved until the user confirms.
- **FR-S3** The user can accept, change or discard every suggestion.

**Acceptance criteria**
- If the AI request fails or times out, the user sees a short notice and can fill in the fields manually.
- Suggested tags that do not yet exist are only created when the user saves the entry.
- A suggestion has exactly one category and at most 5 tags. A suggested tag that matches an existing tag, ignoring case, uses that tag's spelling.

### 7.4 Review and summaries

- **FR-R1** Users can filter entries by period (start and end date, both included), categories and tags. Several categories, or several tags, match entries that have any of them. Different filter types combine: an entry must match all of them.
- **FR-R2** Filtered entries are shown grouped by category, newest first within each group.
- **FR-R3** Users can generate an AI summary of the currently filtered entries. A summary needs both a start date and an end date.
- **FR-R4** Summaries are saved together with the filter they were created from.
- **FR-R5** Users can edit, list and delete saved summaries. Editing changes only the summary's text.
- **FR-R6** Users can copy a summary's text to the clipboard.

**Acceptance criteria**
- A summary is only based on entries that match its filter.
- Editing a summary never changes the underlying entries.
- If no entries match the filter, no summary is generated and the user is told why.
- If the matching entries are too large to summarise in one request (more than 50,000 characters by default, configurable), no summary is generated and the user is asked to narrow the filter.
- A summary's text is at most 10,000 characters.

### 7.5 Writing nudge

- **FR-N1** If the user has no entries dated in the last 7 days, a banner on the main page invites them to write one. The last 7 days are today and the 6 days before it, in the user's own time zone.

**Acceptance criteria**
- The banner disappears as soon as an entry dated within the last 7 days exists.
- Entries dated in the future do not count.

### 7.6 Data control

- **FR-D1** Users can export all their entries and summaries in two formats: JSON (complete and machine-readable) and Markdown (readable). Both are generated from the same data. The export contains no email address, password hash, login tokens or usage data.
- **FR-D2** Users can delete their account after confirming with their current password. This permanently removes the user, their entries, tags, summaries, AI usage records and logins.

**Acceptance criteria**
- The export contains every entry (including its category, tags and result) and every summary of the user.
- An account without entries or summaries can still export; the files are then empty.
- After account deletion, the user's credentials no longer work and none of their data remains in the database.
- Account deletion does not lower the day's global AI count, which contains no personal data (see 8).

### 7.7 Demo account

- **FR-X1** The deployed app provides a demo account with sample entries, so visitors can try Winlog without registering.

**Rules**
- Visitors enter with a "Try the demo" button, without a password.
- Visitors can use every feature except deleting the demo account.
- While using the demo, the app tells visitors that the account is shared, that anyone can see and change its data, that AI limits are shared, and that they should not enter personal information.
- The demo data is reset to the sample data whenever the backend starts: on every deploy, and whenever a sleeping server wakes up.

---

## 8. AI behaviour and guardrails

- **AI assists, the user decides.** AI output is never saved without the user's confirmation (suggestions) or explicit action (summaries).
- **No hard dependency.** Every feature except generating suggestions and summaries works without the AI.
- **Usage limits.** AI requests are limited per day:

  | Limit | Default |
  |---|---|
  | Suggestions per user | 10 |
  | Summaries per user | 2 |
  | Total AI requests across all users (global cap) | 100 |

  All limits are configurable through environment variables. A day runs from 00:00 to 24:00 UTC, and all counts start again at 00:00 UTC. When a limit is reached, the user is told which limit it is and can continue without AI until it resets. Every AI call that is attempted counts, including calls that fail or time out. Requests stopped before an AI call (for example because no entries match) do not count. The global cap is counted separately from the per-user counts, so deleting an account does not lower it. The demo account is treated like any other user, so its limits are shared by everyone who uses it.
- **Language.** AI output follows the language of the user's input: suggestions match the entry's language, and a summary is written in the language most of its entries use.
- **Data minimisation.** Only the data a request needs is sent to the AI provider. For suggestions, that is the entry text. For summaries, it is each filtered entry's date, category, text, Result/Impact and tags. User ids and email addresses are never sent.
- **No retention by providers.** Requests are routed only to model endpoints with a zero-data-retention policy. This is enforced on every request and in the provider account's settings.
- **Swappable provider.** The AI is accessed through an adapter. The provider and model are configured through environment variables. A mock provider is used in automated tests and lets the app run locally without an API key.

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| Responsiveness | All screens are usable from a 360px wide mobile viewport up to desktop. |
| Design | The user interface follows the design system in `DESIGN.md` (colours, typography, layout, components, icons and illustrations). Product facts for design work are in `PRODUCT.md`; this specification wins where they differ. |
| Language | The user interface is in English. Entries can be written in any language. |
| Security | Passwords are stored only as hashes. Logins use tokens that the server stores, so they can be revoked, and that expire. Repeated failed logins are slowed down (FR-A4). Secrets and keys come from environment variables and are never committed. All data access is scoped to the authenticated user. |
| Privacy | Users can export and delete their data (see 7.6). AI providers do not retain request data (see 8). |
| Observability | One key user journey, generating a summary (FR-R3), is instrumented with traces, metrics and structured logs that share a trace ID. Telemetry contains no customer data or credentials: no entry text, Result/Impact, tag names, summary text, AI request or response content, passwords, tokens, email addresses, user ids or IP addresses. Locally, the signals are collected, stored and viewable in a UI that starts with Docker Compose. The app works the same when no collector is running. |
| Reliability | The app stays usable if the AI provider is unavailable. |
| Testability | Backend and frontend have automated unit and integration tests, and one command runs them all. AI calls are mocked in tests. |
| Reproducibility | The full system (frontend, backend, database and the local telemetry stack) starts locally with Docker Compose. |

---

## 10. Architecture

### 10.1 Overview

```
Browser (desktop / mobile)
        │
        ▼
React + TypeScript frontend ──── HTTPS / JSON ────► FastAPI backend
                                                     │         │
                                                     ▼         ▼
                                               PostgreSQL   LLM router
                                                            (OpenAI-compatible API)
```

### 10.2 Components

| Component | Technology | Responsibility |
|---|---|---|
| Frontend | React, TypeScript | Responsive UI; all backend calls go through one central API client |
| Backend | Python, FastAPI | REST API, authentication with bearer tokens, business logic, AI adapter, AI usage limits, login attempt limits |
| Database | PostgreSQL | Persistent storage in all environments, with schema migrations |
| AI | LLM router service (OpenRouter planned) | Category and tag suggestions; summaries |
| Containers | Docker, Docker Compose | Local development and integration testing of the full system |
| Observability | OpenTelemetry (Python SDK, OTLP); Grafana's all-in-one otel-lgtm image (OpenTelemetry Collector, Prometheus, Tempo, Loki, Grafana) | The backend's traces, metrics and JSON logs, sent over OTLP when a collector is configured. Locally, collection, storage and the viewer UI run in Docker Compose. Deployed environments send no telemetry yet. |
| CI/CD | GitHub Actions | Runs lint and tests on every push; production deploys only after all CI checks for the commit have passed |
| Hosting | Render (frontend as a static site, backend as a web service, both defined in a Render Blueprint), Neon (PostgreSQL) | Production environment |

### 10.3 API contract

- `openapi.yaml` is the single source of truth for the API.
- It is written before implementation; the backend implements it, and the frontend API client is built against it.
- Changes to the API start with a change to `openapi.yaml`.
- Authentication uses bearer tokens. Login returns a random token that the server stores, so logout and account deletion can revoke it. Clients send it as `Authorization: Bearer <token>`.

### 10.4 Environments

| Environment | Runs on | Database |
|---|---|---|
| Development | Docker Compose (local) | PostgreSQL container, with separate databases for development and tests |
| Test / CI | Docker Compose (CI runner) | PostgreSQL container |
| Production | Render | Neon PostgreSQL |

Configuration (database URL, AI provider and model, limits, secrets) comes from environment variables in every environment.

### 10.5 Conceptual data model

```
User          (id, email, password_hash, created_at)          -- email stored in lower case
Token         (id, user_id, token_hash, created_at, expires_at)
Entry         (id, user_id, date, text, category, result_impact?, created_at, updated_at)
Tag           (id, user_id, name)                             -- unique per user, ignoring case
EntryTag      (entry_id, tag_id)
Summary       (id, user_id, period_start, period_end, filter_categories, filter_tags,
               text, created_at, updated_at)                  -- filter tags stored as names
AiUsage       (user_id, day, request_type, request_count)     -- per-user limits
AiUsageGlobal (day, request_count)                            -- global cap; no personal data
LoginAttempt  (key_hash, window_start, attempt_count)         -- attempt limits; hashed email or IP
```

`category` is a value from a fixed list. Deleting a user deletes all of their rows; `AiUsageGlobal` and `LoginAttempt` contain no readable personal data, and attempt rows are removed once their time window has passed. The final schema is defined in the database migrations.

---

## 11. Roadmap

**Next (optional)**
- Career storytelling: turn selected entries into STAR stories, CV bullet points or LinkedIn text. This uses the same generation endpoint as summaries, with a different output type.
- Guided weekly check-in: a page with two or three prompts, where each answer becomes an entry.

**Later**
- Single sign-on (Google, GitHub)
- Email reminders
- Integration with AI assistants, so entries can be added and searched from an assistant
- Pattern analysis over longer periods

## 12. Known limitations

- After a period of inactivity, the hosted app may take up to about a minute to respond to the first request.
- Demo data is shared by all visitors and is reset whenever the backend starts, so changes made in the demo do not last.
- Someone who knows a user's email address can block that user's logins for up to 15 minutes by failing to log in on purpose (FR-A4).

## 13. Open questions

None at the moment.

Closed:

- Default LLM model (closed 9 November 2026): `anthropic/claude-haiku-5.5`, chosen by a documented comparison (issue #14). The backup model is `deepseek/deepseek-v4.1-flash`: if the default becomes unavailable, too expensive or worse, the model setting is switched to it. It is not an automatic fallback. Details in `docs/decisions/default-model.md`.

## 14. Change log

**0.2, updated 13 November 2026.** §9: new "Observability" row, and the Reproducibility row includes the local telemetry stack. §10.2: new "Observability" row (issue #74). Nothing else changed.

**0.2, updated 13 November 2026.** §9: the Testability row adds that one command runs all unit and integration tests (issue #73). Nothing else changed.

**0.2, updated 11 November 2026.** §9: new "Design" row. The user interface follows `DESIGN.md`, the design system the product owner chose on 11 November 2026 ("Plum & Peach v2"). Nothing else changed.

**0.2, updated 9 November 2026.** §13: the open question about the default LLM model is closed. The default is `anthropic/claude-haiku-5.5`, with `deepseek/deepseek-v4.1-flash` as the backup model (issue #14). Nothing else changed.

**0.2 (1 November 2026).** Updated with the decisions made while grooming the backlog (GitHub issues #2–#46). Section numbers are unchanged, so references such as §7.3 in the issues still point to the right place.
- Accounts: password rule, case-insensitive emails, automatic login after registering, 7-day logins, failed-login limits (new FR-A4), and the current password required for account deletion.
- Entries: date required (pre-filled with the local date), size limits, tag rules, and unused tags hidden.
- Suggestions: fill only empty fields, at most 5 tags.
- Review and summaries: inclusive dates, "any" matching within a filter type, sort order, a required period, a size limit for summary input, and copying a summary (new FR-R6).
- Writing nudge: exact definition of "the last 7 days".
- Data control: export contents, and deletion with password.
- Demo account: entry without a password, no deletion, shared-account notice, and reset on every backend start.
- AI guardrails: UTC days, which calls count, a separate global counter, and the data sent for summaries.
- Architecture: bearer-token authentication, a separate test database, deploys after CI checks pass, and new tables (`Token`, `AiUsageGlobal`, `LoginAttempt`).

**0.1 (1 November 2026).** First draft.
