# Winlog: Product Specification

**Version:** 0.1 (draft)
**Last updated:** 1 November 2026

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

## 5. Target users

Individual professionals who want a lightweight record of their work so they can prepare for performance reviews, appraisal talks and job interviews. Each user works only with their own data.

## 6. Core concepts

| Concept | Description |
|---|---|
| **Entry** | One record of something that happened at work. It is written as free text and has a date, one category, optional tags and an optional result or impact. |
| **Category** | One value from a fixed list: *Achievement*, *Learning*, *Feedback*, *Side project*. Every entry has exactly one category. |
| **Tag** | A label created by the user. An entry can have any number of tags. |
| **Summary** | AI-generated text that describes the entries matching a filter (period, categories, tags). Summaries are saved and can be edited. |

---

## 7. Functional requirements

### 7.1 Accounts

- **FR-A1** Users can register with an email address and a password.
- **FR-A2** Users can log in and log out.
- **FR-A3** Users can only access their own entries, tags and summaries.

**Acceptance criteria**
- A user cannot read, change or delete another user's data through the UI or the API.
- Requests without valid authentication are rejected.

### 7.2 Capturing entries

- **FR-E1** A user creates an entry by writing free text. One text always creates exactly one entry.
- **FR-E2** Each entry has:
  - a date (defaults to today)
  - exactly one category
  - any number of tags
  - an optional *Result/Impact* field
- **FR-E3** Users can create new tags while writing an entry.
- **FR-E4** Users can edit and delete their entries.

**Acceptance criteria**
- An entry can be saved without using AI suggestions.
- An entry cannot be saved without text, date and category.

### 7.3 AI suggestions for category and tags

- **FR-S1** After the user writes the text, the app can request AI suggestions for category and tags.
- **FR-S2** Suggestions pre-fill the form. Nothing is saved until the user confirms.
- **FR-S3** The user can accept, change or discard every suggestion.

**Acceptance criteria**
- If the AI request fails or times out, the user sees a short notice and can fill in the fields manually.
- Suggested tags that do not yet exist are only created when the user saves the entry.

### 7.4 Review and summaries

- **FR-R1** Users can filter entries by period (start and end date), categories and tags.
- **FR-R2** Filtered entries are shown grouped by category.
- **FR-R3** Users can generate an AI summary of the currently filtered entries.
- **FR-R4** Summaries are saved together with the filter they were created from.
- **FR-R5** Users can edit, list and delete saved summaries.

**Acceptance criteria**
- A summary is only based on entries that match its filter.
- Editing a summary never changes the underlying entries.
- If no entries match the filter, no summary is generated and the user is told why.

### 7.5 Writing nudge

- **FR-N1** If the user has no entries in the last 7 days, a banner on the main page invites them to write one.

**Acceptance criteria**
- The banner disappears as soon as an entry dated within the last 7 days exists.

### 7.6 Data control

- **FR-D1** Users can export all their entries and summaries in two formats: JSON (complete and machine-readable) and Markdown (readable). Both are generated from the same data.
- **FR-D2** Users can delete their account. This permanently removes the user, their entries, tags and summaries.

**Acceptance criteria**
- The export contains every entry (including its category, tags and result) and every summary of the user.
- After account deletion, the user's credentials no longer work and none of their data remains in the database.

### 7.7 Demo account

- **FR-X1** The deployed app provides a demo account with sample entries, so visitors can try Winlog without registering.

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

  All limits reset daily and are configurable through environment variables. When a limit is reached, the user is informed and can continue without AI until the limit resets. The demo account is treated like any other user, so its limits are shared by everyone who uses it.
- **Language.** AI output follows the language of the user's input: suggestions match the entry's language, and a summary is written in the language most of its entries use.
- **Data minimisation.** Only the data a request needs is sent to the AI provider: the entry text for suggestions, and the filtered entries for summaries.
- **No retention by providers.** Requests are routed only to model endpoints with a zero-data-retention policy.
- **Swappable provider.** The AI is accessed through an adapter. The provider and model are configured through environment variables, and a mock provider is used in automated tests.

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| Responsiveness | All screens are usable on mobile browsers (narrow viewports) and desktop. |
| Language | The user interface is in English. Entries can be written in any language. |
| Security | Passwords are stored only as hashes. Secrets and keys come from environment variables and are never committed. All data access is scoped to the authenticated user. |
| Privacy | Users can export and delete their data (see 7.6). AI providers do not retain request data (see 8). |
| Reliability | The app stays usable if the AI provider is unavailable. |
| Testability | Backend and frontend have automated tests. AI calls are mocked in tests. |
| Reproducibility | The full system (frontend, backend, database) starts locally with Docker Compose. |

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
| Backend | Python, FastAPI | REST API, authentication, business logic, AI adapter, AI usage limits |
| Database | PostgreSQL | Persistent storage in all environments, with schema migrations |
| AI | LLM router service (OpenRouter planned) | Category and tag suggestions; summaries |
| Containers | Docker, Docker Compose | Local development and integration testing of the full system |
| CI/CD | GitHub Actions | Runs tests on every push; deploys only when all tests pass |
| Hosting | Render (frontend and backend), Neon (PostgreSQL) | Production environment |

### 10.3 API contract

- `openapi.yaml` is the single source of truth for the API.
- It is written before implementation; the backend implements it, and the frontend API client is built against it.
- Changes to the API start with a change to `openapi.yaml`.

### 10.4 Environments

| Environment | Runs on | Database |
|---|---|---|
| Development | Docker Compose (local) | PostgreSQL container |
| Test / CI | Docker Compose (CI runner) | PostgreSQL container |
| Production | Render | Neon PostgreSQL |

Configuration (database URL, AI provider and model, secrets) comes from environment variables in every environment.

### 10.5 Conceptual data model

```
User      (id, email, password_hash, created_at)
Entry     (id, user_id, date, text, category, result_impact?, created_at, updated_at)
Tag       (id, user_id, name)                          -- unique per user
EntryTag  (entry_id, tag_id)
Summary   (id, user_id, period_start, period_end, filter_categories, filter_tags,
           text, created_at, updated_at)
AiUsage   (user_id, day, request_type, request_count)  -- per-user limits; summed for the global cap
```

`category` is a value from a fixed list. The final schema is defined in the database migrations.

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

## 13. Open questions

- Default LLM model
