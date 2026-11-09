"""The AI adapter, the provider factory and the mock provider (issue #12, product-spec.md §8).

No test here calls a real AI API: the only provider is the mock.
"""

import datetime as dt
import inspect
import logging
import uuid
from types import SimpleNamespace
from typing import get_args

import pytest

from app.ai import (
    AIError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
    MockProvider,
    Suggestion,
    SummaryEntry,
    create_ai_provider,
    get_ai_provider,
)
from app.ai.adapter import CATEGORIES, MAX_SUMMARY_CHARACTERS
from app.ai.factory import PROVIDERS
from app.entries import Entry
from app.health import check_database
from app.main import create_app
from app.settings import AIProviderName, Settings, SettingsError, load_settings

DATABASE_URL = "postgresql://winlog:unit@localhost:5432/winlog"


def summary_entry(**changes) -> SummaryEntry:
    values = {
        "date": dt.date(2026, 3, 2),
        "category": "Achievement",
        "text": "Shipped the billing migration",
        "result_impact": "Invoices went out on time",
        "tags": ("billing",),
    }
    return SummaryEntry(**(values | changes))


@pytest.fixture
def mock() -> MockProvider:
    return MockProvider()


@pytest.fixture
def ai_env(no_env_file, monkeypatch):
    """Every required variable except AI_PROVIDER."""
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")


# --- Interface ---


def test_ai_suggest_returns_one_of_the_four_categories_and_tag_names(mock):
    suggestion = mock.suggest("Shipped the billing migration")

    assert isinstance(suggestion, Suggestion)
    assert suggestion.category in {"Achievement", "Learning", "Feedback", "Side project"}
    assert isinstance(suggestion.tags, list)
    assert all(isinstance(tag, str) for tag in suggestion.tags)


def test_ai_categories_are_the_four_of_the_contract(contract):
    validator = contract("Category")

    assert set(CATEGORIES) == {"Achievement", "Learning", "Feedback", "Side project"}
    for category in CATEGORIES:
        validator.validate(category)


def test_ai_suggestion_matches_the_contract(contract, mock):
    suggestion = mock.suggest("Learned Rust")

    contract("Suggestion").validate({"category": suggestion.category, "tags": suggestion.tags})


def test_ai_summarise_returns_a_summary_text(mock):
    summary = mock.summarise([summary_entry(), summary_entry(date=dt.date(2026, 3, 9))])

    assert isinstance(summary, str)
    assert summary.strip()


def test_ai_summarise_receives_only_date_category_text_result_impact_and_tags():
    fields = {name for name in SummaryEntry.__dataclass_fields__}

    assert fields == {"date", "category", "text", "result_impact", "tags"}
    # slots: a SummaryEntry cannot carry any other attribute, such as a user or entry id.
    with pytest.raises((AttributeError, TypeError)):
        summary_entry().user_id = uuid.uuid4()


def test_ai_summary_entry_from_entry_leaves_the_ids_behind():
    entry_id = uuid.uuid4()
    now = dt.datetime(2026, 3, 2, 12, tzinfo=dt.UTC)
    entry = Entry(
        id=entry_id,
        date=dt.date(2026, 3, 2),
        text="Shipped the billing migration",
        category="Achievement",
        tags=["billing", "Q1"],
        result_impact=None,
        created_at=now,
        updated_at=now,
    )

    item = SummaryEntry.from_entry(entry)

    assert item == SummaryEntry(
        date=dt.date(2026, 3, 2),
        category="Achievement",
        text="Shipped the billing migration",
        result_impact=None,
        tags=("billing", "Q1"),
    )
    assert str(entry_id) not in repr(item)


def test_ai_summarise_rejects_anything_but_summary_entries(mock):
    now = dt.datetime(2026, 3, 2, 12, tzinfo=dt.UTC)
    entry = Entry(
        id=uuid.uuid4(),
        date=dt.date(2026, 3, 2),
        text="Shipped the billing migration",
        category="Achievement",
        tags=[],
        result_impact=None,
        created_at=now,
        updated_at=now,
    )
    with_user = {"user_id": str(uuid.uuid4()), "email": "a@example.com", "text": "Hi"}

    for item in (entry, with_user):
        with pytest.raises(TypeError):
            mock.summarise([item])

    assert mock.summarise_calls == []


def test_ai_provider_receives_exactly_the_summary_entries(mock):
    entries = [summary_entry(), summary_entry(text="Mentored a new hire", tags=())]

    mock.summarise(entries)

    assert mock.summarise_calls == [tuple(entries)]
    assert all(type(item) is SummaryEntry for item in mock.summarise_calls[0])


def test_ai_summarise_without_entries_makes_no_call(mock):
    with pytest.raises(ValueError):
        mock.summarise([])

    assert mock.summarise_calls == []


def test_ai_suggest_rejects_text_that_is_not_a_string(mock):
    with pytest.raises(TypeError):
        mock.suggest(None)


def test_ai_interface_is_sync_like_the_rest_of_the_backend():
    # Issue #4 chose a sync backend; the adapter matches it.
    for operation in (AIProvider.suggest, AIProvider.summarise):
        assert not inspect.iscoroutinefunction(operation)
    assert isinstance(MockProvider().suggest("Learned Rust"), Suggestion)


def test_ai_has_a_timeout_error_and_a_provider_failure_error():
    assert issubclass(AITimeoutError, AIError)
    assert issubclass(AIProviderError, AIError)
    assert not issubclass(AITimeoutError, AIProviderError)
    assert not issubclass(AIProviderError, AITimeoutError)


# --- Provider selection ---


def test_ai_factory_returns_the_mock_for_mock(settings):
    assert isinstance(create_ai_provider(settings), MockProvider)


def test_ai_app_creates_the_provider_at_startup(settings):
    app = create_app(settings)

    assert isinstance(app.state.ai_provider, MockProvider)
    assert get_ai_provider(SimpleNamespace(app=app)) is app.state.ai_provider


def test_ai_provider_variable_comes_from_the_environment(ai_env, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")

    assert load_settings().ai_provider == "mock"


def test_ai_missing_provider_variable_stops_the_app(ai_env):
    with pytest.raises(SettingsError, match="AI_PROVIDER is required but not set"):
        load_settings()
    with pytest.raises(SettingsError, match="AI_PROVIDER is required but not set"):
        create_app()


@pytest.mark.parametrize("value", ["", "openai", "Mock", " mock", "none"])
def test_ai_unknown_provider_stops_the_app_naming_the_variable_and_allowed_values(
    ai_env, monkeypatch, value
):
    monkeypatch.setenv("AI_PROVIDER", value)

    with pytest.raises(SettingsError) as error:
        create_app()

    assert "AI_PROVIDER is invalid" in str(error.value)
    assert "'mock'" in str(error.value)


def test_ai_factory_rejects_an_unknown_provider_naming_the_variable_and_allowed_values():
    settings = Settings.model_construct(ai_provider="other")

    with pytest.raises(SettingsError) as error:
        create_ai_provider(settings)

    assert "AI_PROVIDER is invalid" in str(error.value)
    assert "'mock'" in str(error.value)


def test_ai_allowed_providers_are_the_mock_and_the_openai_compatible_one():
    # Issue #13 added the OpenAI-compatible provider to both lists.
    assert set(get_args(AIProviderName)) == {"mock", "openai-compatible"}
    assert set(PROVIDERS) == set(get_args(AIProviderName))


def test_ai_app_runs_with_the_mock_and_no_api_key(ai_env, monkeypatch):
    import os

    for name in list(os.environ):
        if "KEY" in name.upper() or name.upper().startswith(("OPENAI", "OPENROUTER", "AI_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("AI_PROVIDER", "mock")

    from fastapi.testclient import TestClient

    app = create_app()
    app.dependency_overrides[check_database] = lambda: True
    provider = app.state.ai_provider

    assert TestClient(app).get("/health").status_code == 200
    assert provider.suggest("Learned Rust").category in CATEGORIES
    assert provider.summarise([summary_entry()]).startswith("Mock summary")


# --- Mock provider ---


def test_ai_mock_suggest_is_deterministic(mock):
    first = mock.suggest("Shipped the billing migration")

    assert mock.suggest("Shipped the billing migration") == first
    assert MockProvider().suggest("Shipped the billing migration") == first


def test_ai_mock_suggest_is_the_same_in_every_run(mock):
    # Fixed values: the category comes from SHA-256, not from Python's per-run hash().
    assert mock.suggest("Shipped the billing migration") == Suggestion("Achievement", ["Mock tag"])
    assert mock.suggest("Learned Rust") == Suggestion("Feedback", ["Mock tag"])
    assert mock.suggest("x") == Suggestion("Learning", ["Mock tag"])


def test_ai_mock_summarise_is_deterministic(mock):
    entries = [summary_entry(date=dt.date(2026, 3, 9)), summary_entry(date=dt.date(2026, 1, 5))]

    first = mock.summarise(entries)

    assert mock.summarise(entries) == first
    assert MockProvider().summarise(entries) == first
    assert first == "Mock summary of 2 entries from 2026-01-05 to 2026-03-09."
    assert mock.summarise([summary_entry()]) == (
        "Mock summary of 1 entry from 2026-03-02 to 2026-03-02."
    )


def test_ai_mock_default_output_is_obviously_fake(mock):
    assert mock.summarise([summary_entry()]).startswith("Mock summary")
    assert mock.suggest("Shipped the billing migration").tags == ["Mock tag"]


def test_ai_mock_returns_a_configured_suggestion(mock):
    mock.return_suggestion(Suggestion(category="Side project", tags=["Rust", "CLI"]))

    assert mock.suggest("anything") == Suggestion(category="Side project", tags=["Rust", "CLI"])
    assert mock.suggest("something else") == Suggestion("Side project", ["Rust", "CLI"])


def test_ai_mock_returns_a_configured_summary(mock):
    mock.return_summary("A strong quarter.")

    assert mock.summarise([summary_entry()]) == "A strong quarter."


def test_ai_mock_reset_goes_back_to_the_default(mock):
    default = mock.suggest("Learned Rust")
    mock.return_suggestion(Suggestion("Learning", []))
    mock.return_summary("A strong quarter.")
    mock.raise_timeout()

    mock.reset()

    assert mock.suggest("Learned Rust") == default
    assert mock.summarise([summary_entry()]).startswith("Mock summary")


def test_ai_mock_raises_the_timeout_error(mock):
    mock.raise_timeout()

    with pytest.raises(AITimeoutError):
        mock.suggest("Learned Rust")
    with pytest.raises(AITimeoutError):
        mock.summarise([summary_entry()])


def test_ai_mock_raises_the_provider_failure_error(mock):
    mock.raise_provider_error()

    with pytest.raises(AIProviderError):
        mock.suggest("Learned Rust")
    with pytest.raises(AIProviderError):
        mock.summarise([summary_entry()])


def test_ai_mock_records_the_calls_it_received(mock):
    mock.raise_timeout()
    with pytest.raises(AITimeoutError):
        mock.suggest("Learned Rust")

    assert mock.suggest_calls == ["Learned Rust"]


def test_ai_suggested_tag_names_are_normalised(mock):
    mock.return_suggestion(Suggestion("Learning", ["  machine   learning ", "Rust"]))

    assert mock.suggest("Learned Rust").tags == ["machine learning", "Rust"]


# --- Invalid output ---


@pytest.mark.parametrize(
    "suggestion",
    [
        Suggestion(category="Other", tags=[]),
        Suggestion(category="achievement", tags=[]),
        Suggestion(category=None, tags=[]),
        Suggestion(category="Learning", tags="Rust"),
        Suggestion(category="Learning", tags=None),
        Suggestion(category="Learning", tags=["Rust", 3]),
        Suggestion(category="Learning", tags=["   "]),
        Suggestion(category="Learning", tags=[""]),
        Suggestion(category="Learning", tags=["bad\x00tag"]),
        Suggestion(category="Learning", tags=["\ud800"]),
    ],
)
def test_ai_invalid_suggestion_raises_the_provider_failure_error(mock, suggestion):
    mock.return_suggestion(suggestion)

    with pytest.raises(AIProviderError):
        mock.suggest("Learned Rust")


@pytest.mark.parametrize("summary", ["", "   \n\t", None, 42, ["text"], "bad\x00summary", "\ud800"])
def test_ai_invalid_summary_raises_the_provider_failure_error(mock, summary):
    mock.return_summary(summary)

    with pytest.raises(AIProviderError):
        mock.summarise([summary_entry()])


def test_ai_summary_limit_is_the_specs_10000_characters():
    # product-spec.md §7.4: "A summary's text is at most 10,000 characters."
    assert MAX_SUMMARY_CHARACTERS == 10_000


# Characters, not bytes: "ä" is 2 bytes in UTF-8, "語" 3 and "😀" 4, but each is 1 character.
@pytest.mark.parametrize("char", ["a", "ä", "語", "😀"])
def test_ai_summary_of_exactly_10000_characters_is_accepted(mock, char):
    summary = char * MAX_SUMMARY_CHARACTERS
    mock.return_summary(summary)

    assert mock.summarise([summary_entry()]) == summary


@pytest.mark.parametrize("char", ["a", "ä", "語", "😀"])
def test_ai_summary_over_10000_characters_raises_the_provider_failure_error(mock, char):
    """Product owner decision on #17: an unusable answer, not one to shorten."""
    mock.return_summary(char * (MAX_SUMMARY_CHARACTERS + 1))

    with pytest.raises(AIProviderError, match="longer than 10,000 characters"):
        mock.summarise([summary_entry()])


def test_ai_summary_length_check_applies_to_every_provider():
    """The check is in the adapter, so a provider cannot skip it."""

    class _LongProvider(AIProvider):
        name = "long"

        def _suggest(self, text: str) -> Suggestion:
            raise NotImplementedError

        def _summarise(self, entries: tuple[SummaryEntry, ...]) -> str:
            return "x" * (MAX_SUMMARY_CHARACTERS + 1)

    with pytest.raises(AIProviderError):
        _LongProvider().summarise([summary_entry()])


class _BrokenProvider(AIProvider):
    """A provider that returns the wrong type or fails with an unexpected exception."""

    name = "broken"

    def __init__(self, suggestion: object = None, error: Exception | None = None) -> None:
        self.suggestion = suggestion
        self.error = error

    def _suggest(self, text: str) -> Suggestion:
        if self.error:
            raise self.error
        return self.suggestion

    def _summarise(self, entries: tuple[SummaryEntry, ...]) -> str:
        if self.error:
            raise self.error
        return "A summary."


def test_ai_output_that_is_not_a_suggestion_raises_the_provider_failure_error():
    provider = _BrokenProvider(suggestion={"category": "Learning", "tags": []})

    with pytest.raises(AIProviderError):
        provider.suggest("Learned Rust")


def test_ai_unexpected_provider_exception_becomes_the_provider_failure_error():
    cause = RuntimeError("connection reset")
    provider = _BrokenProvider(error=cause)

    with pytest.raises(AIProviderError) as suggest_error:
        provider.suggest("Learned Rust")
    with pytest.raises(AIProviderError) as summarise_error:
        provider.summarise([summary_entry()])

    assert suggest_error.value.__cause__ is cause
    assert summarise_error.value.__cause__ is cause


def test_ai_timeout_from_a_provider_stays_a_timeout():
    provider = _BrokenProvider(error=AITimeoutError("The AI provider did not answer in time."))

    with pytest.raises(AITimeoutError):
        provider.suggest("Learned Rust")


# --- Privacy ---

ENTRY_TEXT = "Negotiated the Zephyrquartz contract renewal"
RESULT_IMPACT = "Saved Xylobank 40 percent"
TAG_NAMES = ("Quokkaproject", "Tangerinewave")
SUMMARY_TEXT = "Mock summary: the Wobblefrost quarter went well"
SUGGESTED_TAGS = ["Glimmerlake", "Fennelroad"]
PRIVATE = [ENTRY_TEXT, RESULT_IMPACT, *TAG_NAMES, SUMMARY_TEXT, *SUGGESTED_TAGS]


def _private_entries() -> list[SummaryEntry]:
    return [
        summary_entry(text=ENTRY_TEXT, result_impact=RESULT_IMPACT, tags=TAG_NAMES),
        summary_entry(text=ENTRY_TEXT + " again", result_impact=None, tags=TAG_NAMES[:1]),
    ]


def test_ai_adapter_and_mock_never_log_entry_text_tag_names_or_summary_text(mock, caplog):
    caplog.set_level(logging.DEBUG)
    errors: list[AIError] = []

    # Default output, configured output, both errors and invalid output.
    mock.suggest(ENTRY_TEXT)
    mock.summarise(_private_entries())
    mock.return_suggestion(Suggestion("Achievement", SUGGESTED_TAGS))
    mock.return_summary(SUMMARY_TEXT)
    assert mock.suggest(ENTRY_TEXT).tags == SUGGESTED_TAGS
    assert mock.summarise(_private_entries()) == SUMMARY_TEXT
    for configure in (mock.raise_timeout, mock.raise_provider_error):
        configure()
        for call in (lambda: mock.suggest(ENTRY_TEXT), lambda: mock.summarise(_private_entries())):
            with pytest.raises(AIError) as error:
                call()
            errors.append(error.value)
    mock.reset()
    mock.return_suggestion(Suggestion(ENTRY_TEXT, SUGGESTED_TAGS))
    mock.return_summary(SUMMARY_TEXT + "\x00")
    for call in (lambda: mock.suggest(ENTRY_TEXT), lambda: mock.summarise(_private_entries())):
        with pytest.raises(AIProviderError) as error:
            call()
        errors.append(error.value)
    # A summary over the length limit (issue #17).
    mock.return_summary(SUMMARY_TEXT * (MAX_SUMMARY_CHARACTERS // len(SUMMARY_TEXT) + 1))
    with pytest.raises(AIProviderError) as error:
        mock.summarise(_private_entries())
    errors.append(error.value)

    ai_records = [record for record in caplog.records if record.name.startswith("app.ai")]
    assert len(ai_records) == 11  # the adapter does log each call, but only metadata
    for text in PRIVATE:
        assert text not in caplog.text
        for error in errors:
            assert text not in str(error)
            assert text not in repr(error)
