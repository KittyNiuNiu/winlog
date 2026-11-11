# Product

<!-- impeccable:product-schema 1 -->

The full requirements are in `docs/product-spec.md`; that file wins where the two differ. This record keeps the product facts that design work needs.

## Platform

web

## Users

Individual professionals who want a lightweight record of their work, so they can prepare for performance reviews, appraisal talks and job interviews. Each user sees only their own data.

Two situations, confirmed by the product owner (2026-11-11):

- **Capturing, on the phone:** right after something happens at work, in a spare minute between tasks.
- **Reviewing, on a laptop:** before a review meeting, filtering past entries and turning them into a summary to edit.

Every screen works on both, from 360px wide up to desktop (spec §9).

## Product Purpose

Make it easy to record work achievements, learnings and feedback as they happen, and turn them into editable summaries for performance reviews. Without a record, people forget what they achieved and undersell their work.

Success (spec §3): capturing an entry takes less than a minute; entries can be filtered by period, category and tags; a selection becomes a review-ready summary the user can edit and keep.

## Positioning

Review-ready in minutes (product owner, 2026-11-11). Quick capture is the means; the payoff is an editable, review-ready summary of the right entries, filtered by period, category and tags. A notes app collects notes but leaves the user to turn months of them into something they can bring to a review.

## Operating Context

- Entries are short free text written soon after the event, in any language, with a date, one of four categories (Achievement, Learning, Feedback, Side project), up to 10 tags and an optional Result/Impact.
- Users may not write every day. The product must not pressure them to (product owner, 2026-11-11).
- Summaries are prepared before performance reviews, appraisal talks and interviews, then edited by the user.
- A shared demo account lets visitors try the app without registering.

## Capabilities and Constraints

- Accounts with email and password; logins last 7 days.
- Entries: create, edit, delete, filter by period, category and tags.
- AI, through one adapter: optional suggestions while writing an entry, and summary generation. Daily limits per user and overall. AI output follows the language of the input.
- AI stays helpful but in the background (product owner, 2026-11-11): writing works fully without it, suggestions appear only when asked for, AI text is clearly a draft the user can edit, and limits or outages are explained calmly. The app stays fully usable when the AI is unavailable (spec §3).
- Export of all data as JSON or Markdown; account deletion.
- Interface text is in English. No native apps, push notifications, sharing or SSO in v1 (spec §4).
- Stack: React and TypeScript with Vite, plain CSS or CSS modules, no UI component library (`AGENTS.md`, #23).

## Brand Commitments

- Name: Winlog.
- Feel: warm but focused (product owner, 2026-11-11). No streaks, progress pressure or "you missed a day" messages.

## Evidence on Hand

None. There are no users, testimonials, customer logos or usage numbers yet. Design work must not invent any.

## Product Principles

1. Capturing comes first: the shortest path in the app is from opening it to a saved entry.
2. The summary is the payoff: reviewing and summarising get the care that turns entries into something review-ready.
3. Calm, not pushy: no streaks, no guilt, no pressure to write every day.
4. AI assists, never blocks: everything works without it, and AI text is always the user's to edit.
5. The user owns their data: it is private, exportable and deletable.

## Accessibility & Inclusion

Basic care, with no formal standard (product owner, 2026-11-11): readable contrast, labels on every form field, visible keyboard focus. Tap targets of at least 44px on phones (#36). Entries can be written in any language.
