# Winlog backlog

Derived from `product-spec.md` (v0.1). Tasks are listed in a suggested build order. References such as FR-E1 or §8 point to the spec. Where the spec leaves a detail open, the task says so instead of assuming an answer.

## 1. Write the OpenAPI contract
Goal: Create `openapi.yaml` as the single source of truth for the Winlog REST API.
Description: Define every endpoint the spec needs (registration, login/logout, entries, tags, AI suggestions, summary generation and management, export, account deletion, health check) with request/response schemas, a shared error format and the authentication scheme (product-spec.md §7, §10.3). Include error responses for validation failures, missing authentication, AI unavailability or timeout, and reached AI usage limits. Decide and record in the file the details the spec leaves open, at least how authentication works (e.g. bearer token or cookie session) and whether a tag filter matches entries with any or all of the selected tags.

## 2. Set up the backend project skeleton
Goal: A runnable FastAPI app with environment-based configuration, a health endpoint and a test setup.
Description: Create the Python/FastAPI backend project with dependency management, a settings module that reads all configuration (database URL, secrets, AI provider settings, usage limits) from environment variables, and the health-check endpoint. Add a test runner with one passing test and a `.env.example` that lists every variable without real secrets (product-spec.md §9, §10.4).

## 3. Run the backend and PostgreSQL with Docker Compose
Goal: `docker compose up` starts the backend and a PostgreSQL database locally.
Description: Write a Dockerfile for the FastAPI backend and a `docker-compose.yml` with the backend and a PostgreSQL container, connected through environment variables (product-spec.md §10.4). The health endpoint should respond and confirm the database is reachable, and the file should be easy to extend with a frontend service later.

## 4. Create the database schema and migrations
Goal: Migrations create all tables from the conceptual data model.
Description: Choose a database access layer and migration tool for the FastAPI backend, and write the initial migration for User, Entry, Tag, EntryTag, Summary and AiUsage as described in product-spec.md §10.5. Include the fixed category list (Achievement, Learning, Feedback, Side project), tag names unique per user, and cascading deletes from a user to all of their data. Add a test that applies the migrations to an empty database.

## 5. Implement user registration
Goal: Users can register with an email address and a password (FR-A1).
Description: Implement the registration endpoint defined in `openapi.yaml`, storing only a password hash and never the plain password (product-spec.md §9). Validate the email format, reject duplicate emails, and enforce a minimum password rule; the spec does not define one, so choose a simple rule and document it. Cover success and failure cases with tests.

## 6. Implement login, logout and request authentication
Goal: Users can log in and out, and requests without valid authentication are rejected (FR-A2).
Description: Implement the login and logout endpoints and the authentication scheme defined in `openapi.yaml`, plus a reusable backend dependency that identifies the current user and rejects requests without valid credentials. Signing keys or session secrets come from environment variables. Add tests for valid login, wrong password, logout, and requests with missing, invalid or expired credentials.

## 7. Implement tag listing and tag name resolution
Goal: Users can list their own tags, and the backend can turn tag names into tag records.
Description: Implement the endpoint in `openapi.yaml` that returns the authenticated user's tags, used for autocomplete and filters. Write a reusable backend function that takes a list of tag names and returns the user's matching tags, creating any that are missing; decide and document how names are normalised (trimming, case sensitivity), since tags must be unique per user (product-spec.md §10.5). Test that users never see or reuse each other's tags.

## 8. Implement entry creation
Goal: Users can save a new entry with text, date, category, tags and an optional result (FR-E1 to FR-E3).
Description: Implement the create-entry endpoint from `openapi.yaml`: text, date and category are required, the date defaults to today, the category must be one of the four fixed values, and tags are given by name, with missing tags created for the user only at save time. One request always creates exactly one entry, and saving never involves the AI. Test validation errors (missing text, date or category; invalid category) and successful saves with new and existing tags.

## 9. Implement reading, editing and deleting entries
Goal: Users can view, edit and delete their own entries (FR-E4).
Description: Implement the get, update and delete endpoints for a single entry as defined in `openapi.yaml`. Updates can change text, date, category, result and tags (creating new tags by name, as on creation) and apply the same validation as creation. A request for another user's entry must behave as if the entry does not exist; add tests for this.

## 10. Implement entry filtering
Goal: Users can list their entries filtered by period, categories and tags (FR-R1).
Description: Implement the list-entries endpoint with optional start date, end date, categories and tags filters, combined across filter types and using the tag-matching rule defined in `openapi.yaml`. Return only the user's own entries in a defined sort order, each with its category and tags, so the frontend can group them by category (FR-R2). Put the filter query in a reusable function, because summary generation must select exactly the same entries.

## 11. Build the AI adapter interface and mock provider
Goal: A provider-agnostic AI interface, configured by environment variables, with a mock for tests.
Description: Define a backend adapter interface with two operations, suggesting a category and tags for an entry text and summarising a list of entries, plus a factory that selects the provider and model from environment variables (product-spec.md §8). Implement a deterministic mock provider for all automated tests, and define the errors the adapter raises for timeouts and provider failures.

## 12. Implement the OpenAI-compatible AI provider
Goal: The AI adapter can call a real LLM through an OpenAI-compatible API (OpenRouter is planned).
Description: Implement a provider for the backend's AI adapter interface that calls an OpenAI-compatible chat API, with base URL, API key and model from environment variables, a request timeout, and failures mapped to the adapter's error types. Configure requests so they are routed only to endpoints with a zero-data-retention policy, and document how this is enforced (product-spec.md §8). Tests stub the HTTP layer, so no real AI calls happen in CI.

## 13. Decide the default LLM model
Goal: Resolve the spec's open question about the default model (product-spec.md §13).
Description: Compare a few candidate models available through the LLM router on quality of category/tag suggestions and summaries in at least two languages, cost per request, latency, and availability on zero-data-retention endpoints. Record the decision and reasoning in a short decision note or the README, and set the chosen model as the default in `.env.example`.

## 14. Enforce daily AI usage limits
Goal: Per-user and global daily caps on AI requests are enforced (product-spec.md §8).
Description: Using the AiUsage table, count suggestion and summary requests per user per day and block a request that would exceed 10 suggestions per user, 2 summaries per user, or 100 AI requests in total across all users, with each default configurable through environment variables. A blocked request returns the limit-reached error defined in `openapi.yaml`; decide and document the time zone of the daily reset and whether failed AI calls count against a limit. Test the counting under concurrent requests and around the reset boundary.

## 15. Implement the AI suggestions endpoint
Goal: Users can get AI suggestions for category and tags from an entry's text, without anything being saved (FR-S1, FR-S2).
Description: Implement the suggestions endpoint from `openapi.yaml`: check the per-user and global usage limits, send only the entry text to the AI adapter, and return one category from the fixed list plus tag names in the entry's language, saving nothing. Map suggested tag names onto the user's existing tags where they match, and return the defined error on AI failure or timeout. The spec allows only the entry text to be sent to the AI, so confirm with the product owner before adding the user's existing tag names to the prompt.

## 16. Implement summary generation
Goal: Users can generate and save an AI summary of the entries matching a filter (FR-R3, FR-R4).
Description: Implement the generate-summary endpoint: select entries with the same filter logic as the entry list, refuse with a clear message if none match, and otherwise check the summary limit and global cap and send only those entries to the AI adapter, asking for a review-ready summary in the language most of the entries use. Save the result together with its filter (period, categories, tags). Test with the mock provider, including the no-match, limit-reached and AI-failure cases.

## 17. Implement saved summary management
Goal: Users can list, view, edit and delete their saved summaries (FR-R5).
Description: Implement the list, get, update and delete endpoints for summaries defined in `openapi.yaml`. Editing changes only the summary text; the underlying entries and the stored filter stay unchanged. Add tests for editing, deleting, and for users being unable to reach each other's summaries.

## 18. Implement data export in JSON and Markdown
Goal: Users can export all their entries and summaries as JSON and as Markdown (FR-D1).
Description: Build one function that collects all of a user's entries (with category, tags and result) and summaries (with their filters), and render that same data in two formats: complete machine-readable JSON and readable Markdown. Expose both as file downloads through the export endpoint(s) in `openapi.yaml`, and test that each format contains every entry and summary.

## 19. Implement account deletion
Goal: Users can permanently delete their account and all their data (FR-D2).
Description: Implement the delete-account endpoint so it removes the user and all their entries, tags, entry–tag links, summaries and AI usage rows in a single transaction. Afterwards the old credentials and any existing sessions or tokens must stop working; tests should check both and confirm that no rows belonging to the user remain.

## 20. Seed the demo account
Goal: The deployed app has a demo account with sample entries (FR-X1).
Description: Write an idempotent seed script that creates the demo user (credentials from environment variables) with realistic sample entries across all four categories, several tags, dates spread over a few months, and at least one saved summary. The spec does not say whether visitors may edit or delete demo data or the demo account itself, or whether demo data is reset, so get those decisions before implementing.

## 21. Verify data isolation between users
Goal: Prove that no user can read, change or delete another user's data (FR-A3).
Description: Write a backend test suite that creates two users with entries, tags and summaries and checks every endpoint in `openapi.yaml` for cross-user access: reading, listing, updating, deleting, filtering by another user's tags, generating summaries and exporting. Also confirm that every endpoint except registration, login and health check rejects unauthenticated requests.

## 22. Set up the frontend project skeleton
Goal: A runnable React + TypeScript app with routing, a responsive layout and a test setup.
Description: Create the frontend project with client-side routing and placeholder pages (login, register, entries, review, summaries, settings), a responsive app shell that works on narrow mobile and desktop viewports, and a test runner with one passing test. Add a Dockerfile and a frontend service to the Docker Compose file so the full system starts with one command (product-spec.md §9).

## 23. Set up CI with GitHub Actions
Goal: Backend and frontend tests run automatically on every push (product-spec.md §10.2).
Description: Add a GitHub Actions workflow that, on every push, starts the system with Docker Compose (including PostgreSQL), applies database migrations, and runs the backend and frontend test suites with the mock AI provider. The workflow fails if any test fails and needs no real AI keys.

## 24. Build the central API client
Goal: All frontend calls to the backend go through one typed client built against `openapi.yaml`.
Description: Create a single API client module whose types are generated from or written against `openapi.yaml`, with the backend base URL taken from configuration. It attaches authentication, turns error responses (validation, unauthenticated, AI unavailable, limit reached) into typed errors the UI can show, and sends the user to the login page when the session is no longer valid. Add tests with mocked HTTP responses.

## 25. Build the registration, login and logout screens
Goal: Users can register, log in and log out in the UI (FR-A1, FR-A2).
Description: Build the register and login forms with inline validation and server error messages, a logout action in the app shell, and route protection that sends unauthenticated visitors to the login page. Add component tests for the forms and the redirect behaviour.

## 26. Build the entry form
Goal: Users can write and save an entry in under a minute (FR-E1 to FR-E3).
Description: Build a create/edit form with a free-text field, a date picker defaulting to today, a category selector with the four fixed categories, a tag input that autocompletes the user's existing tags and accepts new ones, and an optional Result/Impact field. The form blocks saving without text, date and category, works fully without AI, and keeps the flow short on mobile.

## 27. Add AI suggestions to the entry form
Goal: Users can request AI-suggested category and tags and accept, change or discard each one (FR-S1 to FR-S3).
Description: Add a "Suggest" action to the entry form that sends the current text to the suggestions endpoint and pre-fills category and tags, visibly marked as suggestions the user can edit or remove before saving. Suggested tags that do not exist yet are created only when the entry is saved. If the request fails, times out or hits a usage limit, show a short notice and keep the form usable for manual input.

## 28. Build the entries page with edit and delete
Goal: Users see their entries on the main page and can edit or delete them (FR-E4).
Description: Build the main page listing the user's entries with date, category, tags and result, with actions to open an entry in the edit form and to delete it after confirmation. Make the list readable on narrow screens and show an empty state for new users.

## 29. Add the writing nudge banner
Goal: Invite users to write when they have no entry in the last 7 days (FR-N1).
Description: Show a banner on the main page inviting the user to write an entry when none of their entries is dated within the last 7 days, and hide it as soon as such an entry exists, including right after saving one. Decide whether the check runs in the frontend or through a backend endpoint, and define "last 7 days" precisely (whether today counts, which time zone) so it behaves consistently.

## 30. Build the review page with filters
Goal: Users can filter entries by period, categories and tags and see them grouped by category (FR-R1, FR-R2).
Description: Build a review page with start and end date inputs, a category multi-select and a tag multi-select that query the entry list endpoint, and show the results grouped under each category heading. Show an empty state when nothing matches, and make the filter controls usable on mobile.

## 31. Add summary generation to the review page
Goal: Users can generate an AI summary of the currently filtered entries (FR-R3).
Description: Add a "Generate summary" action to the review page that sends the current filter to the summary endpoint, shows progress, and opens the saved summary when it is ready. When no entries match, explain why no summary was created; when the AI fails or the daily limit is reached, show a short notice while the rest of the page stays usable.

## 32. Build the saved summaries pages
Goal: Users can list, read, edit and delete their saved summaries (FR-R5).
Description: Build a summaries list showing each summary's creation date and filter (period, categories, tags), and a detail view where the text can be edited and saved, or the summary deleted after confirmation. Make it clear in the UI that editing a summary does not change any entries.

## 33. Build the data and account settings page
Goal: Users can export their data and delete their account from the UI (FR-D1, FR-D2).
Description: Build a settings page with buttons to download the JSON and Markdown exports, and a "Delete account" action that requires an explicit confirmation step. After deletion, clear the session and return the user to the start page.

## 34. Add "Try the demo" to the login page
Goal: Visitors can try Winlog with the demo account without registering (FR-X1).
Description: Add a "Try the demo" button on the login page that signs the visitor into the demo account, and show a notice inside the app that this is a shared account whose AI limits are shared by everyone (product-spec.md §8). Apply whatever decision has been made about which actions are allowed on demo data, for example hiding account deletion.

## 35. Check every screen on mobile and desktop
Goal: All screens are usable on narrow mobile viewports and on desktop (product-spec.md §9).
Description: Walk through each screen at a phone-width viewport and a desktop viewport and fix layout problems such as horizontal overflow, small tap targets and hidden actions. Confirm that capturing an entry stays quick on mobile, and add automated viewport checks where practical.

## 36. Add an end-to-end smoke test
Goal: One automated test runs the main user flow against the full system.
Description: Write a browser-based end-to-end test that registers a user, creates an entry, filters on the review page, generates a summary with the mock AI provider, and downloads an export, running against the Docker Compose stack. Add it to the GitHub Actions workflow after the unit tests.

## 37. Deploy to Render and Neon
Goal: The app runs in production on Render (frontend and backend) with a Neon PostgreSQL database.
Description: Create the Neon database and the Render services for backend and frontend, and set all configuration through environment variables (database URL, secrets, AI provider, model and key, usage limits, demo credentials). Make database migrations and the demo seed run as part of a deploy, and document the setup and the cold-start limitation (product-spec.md §12) in the README.

## 38. Deploy only when tests pass
Goal: Production deploys happen automatically, and only after all tests pass (product-spec.md §10.2).
Description: Extend the GitHub Actions workflow so that pushes to the main branch trigger a Render deploy only after every test job has succeeded, and make sure Render cannot deploy a commit on its own before CI has passed. Keep deploy credentials in GitHub secrets.

## 39. Write the project README
Goal: A newcomer can understand, run and test Winlog from the README alone.
Description: Expand `README.md` with a short product description, an architecture overview, how to start the full system with Docker Compose, the environment variables (pointing to `.env.example`), how to run the tests, and how the AI usage limits and mock provider work. Link to `product-spec.md` and `openapi.yaml`, and add the live URL and demo instructions once the app is deployed.
