"""The OpenAI-compatible AI provider (issue #13, product-spec.md §8).

No test here calls a real AI API: every provider gets an httpx mock transport through the
SDK's `http_client`, which answers with stubbed responses and records the requests.
"""

import datetime as dt
import json
import logging
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest

from app.ai import (
    AIError,
    AIProviderError,
    AITimeoutError,
    OpenAICompatibleProvider,
    Suggestion,
    SummaryEntry,
    create_ai_provider,
)
from app.ai.openai_compatible import SUGGEST_PROMPT, SUMMARISE_PROMPT
from app.entries import Entry
from app.main import create_app
from app.settings import Settings, SettingsError, load_settings

BASE_URL = "https://ai.example.test/api/v1"
API_KEY = "sk-or-v1-Kq9TestOnlyKeyThatMustNeverBeLogged"
MODEL = "vendor/test-model"
DATABASE_URL = "postgresql://winlog:unit@localhost:5432/winlog"

Handler = Callable[[httpx2.Request], httpx2.Response]


class StubAI:
    """An httpx mock transport that answers each request and records it."""

    def __init__(self, answer: Handler) -> None:
        self.answer = answer
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.answer(request)

    @property
    def bodies(self) -> list[dict]:
        return [json.loads(request.content) for request in self.requests]


def completion(content: object, status: int = 200) -> Handler:
    """A Chat Completions answer whose message has this content."""
    body = {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1_700_000_000,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
    }
    return lambda request: httpx2.Response(status, json=body)


def suggestion_answer(category: object = "Learning", tags: object = ("Rust",)) -> Handler:
    tags = list(tags) if isinstance(tags, tuple) else tags
    return completion(json.dumps({"category": category, "tags": tags}))


def raises(error: type[httpx2.TransportError]) -> Handler:
    def answer(request: httpx2.Request) -> httpx2.Response:
        raise error("stubbed transport error", request=request)

    return answer


def status(code: int) -> Handler:
    return lambda request: httpx2.Response(
        code, json={"error": {"message": "stubbed provider error", "code": code}}
    )


def provider(stub: StubAI, **changes) -> OpenAICompatibleProvider:
    values = {
        "base_url": BASE_URL,
        "api_key": API_KEY,
        "model": MODEL,
        "suggestion_timeout_seconds": 15,
        "summary_timeout_seconds": 60,
    }
    return OpenAICompatibleProvider(
        **(values | changes), http_client=httpx2.Client(transport=httpx2.MockTransport(stub))
    )


def summary_entry(**changes) -> SummaryEntry:
    values = {
        "date": dt.date(2026, 3, 2),
        "category": "Achievement",
        "text": "Shipped the billing migration",
        "result_impact": "Invoices went out on time",
        "tags": ("billing",),
    }
    return SummaryEntry(**(values | changes))


def openai_settings(**changes) -> Settings:
    values = {
        "database_url": DATABASE_URL,
        "cors_allowed_origins": ["http://localhost:5173"],
        "ai_provider": "openai-compatible",
        "ai_base_url": BASE_URL,
        "ai_api_key": API_KEY,
        "ai_model": MODEL,
    }
    return Settings(_env_file=None, **(values | changes))


@pytest.fixture
def ai_env(no_env_file, monkeypatch):
    """A valid configuration for the OpenAI-compatible provider."""
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "openai-compatible")
    monkeypatch.setenv("AI_BASE_URL", BASE_URL)
    monkeypatch.setenv("AI_API_KEY", API_KEY)
    monkeypatch.setenv("AI_MODEL", MODEL)


# --- Configuration ---


def test_ai_openai_settings_come_from_the_environment(ai_env, monkeypatch):
    monkeypatch.setenv("AI_SUGGESTION_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("AI_SUMMARY_TIMEOUT_SECONDS", "90")

    settings = load_settings()

    assert settings.ai_provider == "openai-compatible"
    assert settings.ai_base_url == BASE_URL
    assert settings.ai_api_key is not None
    assert settings.ai_api_key.get_secret_value() == API_KEY
    assert settings.ai_model == MODEL
    assert settings.ai_suggestion_timeout_seconds == 7
    assert settings.ai_summary_timeout_seconds == 90


def test_ai_openai_timeouts_default_to_15_and_60_seconds(ai_env):
    settings = load_settings()

    assert settings.ai_suggestion_timeout_seconds == 15
    assert settings.ai_summary_timeout_seconds == 60


@pytest.mark.parametrize("name", ["AI_SUGGESTION_TIMEOUT_SECONDS", "AI_SUMMARY_TIMEOUT_SECONDS"])
@pytest.mark.parametrize("value", ["0", "-1", "601", "1.5", "soon"])
def test_ai_openai_invalid_timeouts_are_rejected(ai_env, monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(SettingsError, match=f"{name} is invalid"):
        load_settings()


def test_ai_openai_api_key_is_masked_as_a_secret(ai_env, caplog):
    settings = load_settings()

    logging.getLogger("test").warning("settings: %s / %r", settings, settings)

    assert API_KEY not in str(settings)
    assert API_KEY not in repr(settings)
    assert API_KEY not in caplog.text


@pytest.mark.parametrize("name", ["AI_BASE_URL", "AI_API_KEY", "AI_MODEL"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_ai_openai_missing_variable_stops_the_app_naming_it(ai_env, monkeypatch, name, value):
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)

    with pytest.raises(SettingsError) as error:
        create_app()

    message = str(error.value)
    assert f"{name} is required when AI_PROVIDER is 'openai-compatible' but not set" in message
    others = {"AI_BASE_URL", "AI_API_KEY", "AI_MODEL"} - {name}
    assert not any(other in message for other in others)
    assert API_KEY not in message


def test_ai_openai_all_missing_variables_are_named_at_once(ai_env, monkeypatch):
    for name in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL"):
        monkeypatch.delenv(name)

    with pytest.raises(SettingsError) as error:
        load_settings()

    for name in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL"):
        assert f"{name} is required when AI_PROVIDER is 'openai-compatible'" in str(error.value)


@pytest.mark.parametrize("value", ["openrouter.ai/api/v1", "ftp://ai.example.test"])
def test_ai_openai_invalid_base_url_is_rejected(ai_env, monkeypatch, value):
    monkeypatch.setenv("AI_BASE_URL", value)

    with pytest.raises(SettingsError, match="AI_BASE_URL is invalid"):
        load_settings()


def test_ai_openai_variables_are_not_needed_for_the_mock(ai_env, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    for name in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL"):
        monkeypatch.delenv(name)

    assert load_settings().ai_provider == "mock"


def test_ai_openai_factory_and_app_create_the_provider(ai_env):
    assert isinstance(create_ai_provider(openai_settings()), OpenAICompatibleProvider)
    assert isinstance(create_app().state.ai_provider, OpenAICompatibleProvider)


def test_ai_openai_factory_rejects_settings_without_the_variables():
    settings = Settings.model_construct(
        ai_provider="openai-compatible", ai_base_url=None, ai_api_key=None, ai_model=None
    )

    with pytest.raises(SettingsError) as error:
        create_ai_provider(settings)

    for name in ("AI_BASE_URL", "AI_API_KEY", "AI_MODEL"):
        assert f"{name} is required" in str(error.value)


def test_ai_openai_variables_are_documented_in_env_example():
    env_example = (Path(__file__).resolve().parents[3] / ".env.example").read_text()

    assert "openai-compatible" in env_example
    for line in (
        "AI_BASE_URL=",
        "AI_API_KEY=\n",
        "AI_MODEL=\n",
        "AI_SUGGESTION_TIMEOUT_SECONDS=15\n",
        "AI_SUMMARY_TIMEOUT_SECONDS=60\n",
    ):
        assert f"\n{line}" in env_example


# --- Calls ---


def test_ai_openai_uses_chat_completions_with_the_base_url_key_and_model():
    stub = StubAI(suggestion_answer())

    provider(stub).suggest("Learned Rust")

    [request] = stub.requests
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert stub.bodies[0]["model"] == MODEL


def test_ai_openai_provider_from_settings_uses_the_settings():
    stub = StubAI(completion("A summary."))
    settings = openai_settings(
        ai_base_url="https://other.example.test/v1/",
        ai_model="other/model",
        ai_summary_timeout_seconds=42,
    )

    OpenAICompatibleProvider.from_settings(
        settings, http_client=httpx2.Client(transport=httpx2.MockTransport(stub))
    ).summarise([summary_entry()])

    [request] = stub.requests
    assert str(request.url) == "https://other.example.test/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert stub.bodies[0]["model"] == "other/model"
    assert request.extensions["timeout"]["read"] == 42


def test_ai_openai_retries_are_off():
    client = provider(StubAI(suggestion_answer()))._client

    assert client.max_retries == 0


@pytest.mark.parametrize(
    "answer",
    [status(429), status(500), status(503), raises(httpx2.ConnectError)],
    ids=["429", "500", "503", "network"],
)
def test_ai_openai_makes_no_retry_after_a_failure(answer):
    stub = StubAI(answer)
    ai = provider(stub)

    with pytest.raises(AIProviderError):
        ai.suggest("Learned Rust")
    with pytest.raises(AIProviderError):
        ai.summarise([summary_entry()])

    assert len(stub.requests) == 2  # one request for each call


def test_ai_openai_makes_no_retry_after_a_timeout():
    stub = StubAI(raises(httpx2.ReadTimeout))

    with pytest.raises(AITimeoutError):
        provider(stub).suggest("Learned Rust")

    assert len(stub.requests) == 1


def test_ai_openai_every_request_asks_for_zero_data_retention_endpoints():
    suggest_stub = StubAI(suggestion_answer())
    summary_stub = StubAI(completion("A summary."))

    provider(suggest_stub).suggest("Learned Rust")
    provider(summary_stub).summarise([summary_entry()])

    assert suggest_stub.bodies[0]["provider"] == {"zdr": True}
    assert summary_stub.bodies[0]["provider"] == {"zdr": True}


def test_ai_openai_suggest_sends_only_the_entry_text():
    stub = StubAI(suggestion_answer())
    text = "Gave a talk on Rust at the team meeting"

    provider(stub).suggest(text)

    [body] = stub.bodies
    assert set(body) == {"model", "messages", "response_format", "provider"}
    assert body["messages"] == [
        {"role": "system", "content": SUGGEST_PROMPT},
        {"role": "user", "content": text},
    ]
    # The fixed prompt is the only other text; it carries no user data.
    assert text not in SUGGEST_PROMPT


def test_ai_openai_summarise_sends_only_the_allowed_fields():
    entry_id = uuid.uuid4()
    entry = Entry(
        id=entry_id,
        date=dt.date(2026, 3, 4),
        category="Feedback",
        text="My manager praised the incident review",
        result_impact=None,
        tags=["Incidents", "Kudos"],
        created_at=dt.datetime(2026, 3, 4, 9, 30, tzinfo=dt.UTC),
        updated_at=dt.datetime(2026, 3, 4, 9, 30, tzinfo=dt.UTC),
    )
    entries = [
        SummaryEntry.from_entry(entry),
        summary_entry(),
    ]
    stub = StubAI(completion("A summary."))

    provider(stub).summarise(entries)

    [body] = stub.bodies
    assert set(body) == {"model", "messages", "provider"}
    system, user = body["messages"]
    assert system == {"role": "system", "content": SUMMARISE_PROMPT}
    assert user["role"] == "user"
    assert json.loads(user["content"]) == [
        {
            "date": "2026-03-04",
            "category": "Feedback",
            "text": "My manager praised the incident review",
            "result_impact": None,
            "tags": ["Incidents", "Kudos"],
        },
        {
            "date": "2026-03-02",
            "category": "Achievement",
            "text": "Shipped the billing migration",
            "result_impact": "Invoices went out on time",
            "tags": ["billing"],
        },
    ]
    # Exactly these fields: no entry ids, and no user ids or emails, which an entry never has.
    assert str(entry_id) not in stub.requests[0].content.decode()


def test_ai_openai_summarise_sends_text_in_any_language_unchanged():
    stub = StubAI(completion("Eine Zusammenfassung."))
    entries = [summary_entry(text="Größere Datenbank migriert", tags=("Datenbank",))]

    provider(stub).summarise(entries)

    entries_sent = json.loads(stub.bodies[0]["messages"][1]["content"])
    assert entries_sent[0]["text"] == "Größere Datenbank migriert"
    assert entries_sent[0]["tags"] == ["Datenbank"]


def test_ai_openai_uses_the_timeout_of_each_operation():
    suggest_stub = StubAI(suggestion_answer())
    summary_stub = StubAI(completion("A summary."))

    provider(suggest_stub).suggest("Learned Rust")
    provider(summary_stub).summarise([summary_entry()])

    assert suggest_stub.requests[0].extensions["timeout"] == {
        "connect": 15,
        "read": 15,
        "write": 15,
        "pool": 15,
    }
    assert summary_stub.requests[0].extensions["timeout"] == {
        "connect": 60,
        "read": 60,
        "write": 60,
        "pool": 60,
    }


# --- Prompts and output ---


def test_ai_openai_suggest_prompt_asks_for_one_category_unchanged_and_tags_in_the_entry_language():
    for category in ("Achievement", "Learning", "Feedback", "Side project"):
        assert f'"{category}"' in SUGGEST_PROMPT
    assert "exactly one of" in SUGGEST_PROMPT
    assert "exactly as shown here, in English, whatever language the entry" in SUGGEST_PROMPT
    assert "tag names in the language of the entry text" in SUGGEST_PROMPT


def test_ai_openai_suggest_asks_for_a_json_answer():
    stub = StubAI(suggestion_answer())

    provider(stub).suggest("Learned Rust")

    assert stub.bodies[0]["response_format"] == {"type": "json_object"}
    assert "Answer only with a JSON object" in SUGGEST_PROMPT
    assert '{"category":' in SUGGEST_PROMPT and '"tags": [' in SUGGEST_PROMPT


def test_ai_openai_summarise_prompt_asks_for_a_review_ready_summary_in_the_main_language():
    assert "review-ready summary" in SUMMARISE_PROMPT
    assert "in the language that most of the entries use" in SUMMARISE_PROMPT


def test_ai_openai_valid_suggestion():
    stub = StubAI(suggestion_answer("Side project", ["Rust", "Open source"]))

    suggestion = provider(stub).suggest("Released a Rust crate")

    assert suggestion == Suggestion(category="Side project", tags=["Rust", "Open source"])


def test_ai_openai_valid_suggestion_without_tags():
    stub = StubAI(suggestion_answer("Feedback", []))

    assert provider(stub).suggest("Got feedback").tags == []


def test_ai_openai_valid_summary():
    summary = "In March you shipped the billing migration, so invoices went out on time."
    stub = StubAI(completion(summary))

    assert provider(stub).summarise([summary_entry()]) == summary


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"category": "Learning", "tags": ["Rust"]',
        '```json\n{"category": "Learning", "tags": ["Rust"]}\n```',
        "",
    ],
    ids=["text", "truncated", "fenced", "empty"],
)
def test_ai_openai_invalid_json_raises_the_provider_failure_error(content):
    with pytest.raises(AIProviderError):
        provider(StubAI(completion(content))).suggest("Learned Rust")


@pytest.mark.parametrize(
    "category",
    ["learning", "Lernen", "Achievement, Learning", "", None, 1, ["Learning"]],
)
def test_ai_openai_invalid_category_raises_the_provider_failure_error(category):
    with pytest.raises(AIProviderError):
        provider(StubAI(suggestion_answer(category))).suggest("Learned Rust")


@pytest.mark.parametrize(
    "content",
    [
        '["Learning", ["Rust"]]',
        '"Learning"',
        "null",
        '{"tags": ["Rust"]}',
        '{"category": "Learning"}',
        '{"category": "Learning", "tags": "Rust"}',
        '{"category": "Learning", "tags": null}',
        '{"category": "Learning", "tags": [""]}',
        '{"category": "Learning", "tags": ["Rust", "   "]}',
        '{"category": "Learning", "tags": [1]}',
        '{"category": "Learning", "tags": [null]}',
        '{"category": "Learning", "tags": [["Rust"]]}',
    ],
)
def test_ai_openai_suggestion_other_than_a_category_and_tag_names_raises_the_provider_failure_error(
    content,
):
    with pytest.raises(AIProviderError):
        provider(StubAI(completion(content))).suggest("Learned Rust")


@pytest.mark.parametrize("summary", ["", "   ", None])
def test_ai_openai_empty_summary_raises_the_provider_failure_error(summary):
    with pytest.raises(AIProviderError):
        provider(StubAI(completion(summary))).summarise([summary_entry()])


# --- Errors ---


@pytest.mark.parametrize(
    "error", [httpx2.ReadTimeout, httpx2.ConnectTimeout, httpx2.WriteTimeout, httpx2.PoolTimeout]
)
def test_ai_openai_timeout_raises_the_timeout_error(error):
    ai = provider(StubAI(raises(error)))

    with pytest.raises(AITimeoutError):
        ai.suggest("Learned Rust")
    with pytest.raises(AITimeoutError):
        ai.summarise([summary_entry()])


@pytest.mark.parametrize(
    "error", [httpx2.ConnectError, httpx2.ReadError, httpx2.RemoteProtocolError]
)
def test_ai_openai_network_error_raises_the_provider_failure_error(error):
    ai = provider(StubAI(raises(error)))

    with pytest.raises(AIProviderError):
        ai.suggest("Learned Rust")
    with pytest.raises(AIProviderError):
        ai.summarise([summary_entry()])


@pytest.mark.parametrize("code", [400, 401, 402, 403, 404, 408, 422, 429, 500, 502, 503])
def test_ai_openai_error_status_raises_the_provider_failure_error(code):
    ai = provider(StubAI(status(code)))

    with pytest.raises(AIProviderError) as suggest_error:
        ai.suggest("Learned Rust")
    with pytest.raises(AIProviderError) as summary_error:
        ai.summarise([summary_entry()])

    assert not isinstance(suggest_error.value, AITimeoutError)
    assert str(code) in str(suggest_error.value)
    assert str(code) in str(summary_error.value)


def test_ai_openai_401_for_a_bad_key_raises_the_provider_failure_error():
    with pytest.raises(AIProviderError, match="status 401"):
        provider(StubAI(status(401))).suggest("Learned Rust")


def test_ai_openai_429_for_provider_rate_limits_raises_the_provider_failure_error():
    with pytest.raises(AIProviderError, match="status 429"):
        provider(StubAI(status(429))).summarise([summary_entry()])


def test_ai_openai_500_raises_the_provider_failure_error():
    with pytest.raises(AIProviderError, match="status 500"):
        provider(StubAI(status(500))).suggest("Learned Rust")


@pytest.mark.parametrize(
    "answer",
    [
        lambda request: httpx2.Response(200, text="<html>Bad gateway</html>"),
        lambda request: httpx2.Response(200, content=b"\xff\xfe\x00"),
        lambda request: httpx2.Response(200, json={}),
        lambda request: httpx2.Response(200, json={"choices": []}),
        lambda request: httpx2.Response(200, json={"choices": [{}]}),
        lambda request: httpx2.Response(200, json={"error": {"message": "x", "code": 502}}),
        lambda request: httpx2.Response(200, json=[]),
    ],
    ids=["html", "bytes", "empty-object", "no-choices", "no-message", "error-body", "list"],
)
def test_ai_openai_unreadable_response_raises_the_provider_failure_error(answer):
    ai = provider(StubAI(answer))

    with pytest.raises(AIProviderError):
        ai.suggest("Learned Rust")
    with pytest.raises(AIProviderError):
        ai.summarise([summary_entry()])


def test_ai_openai_errors_do_not_chain_the_sdk_exception():
    # The SDK's exception can hold the provider's answer, so it is not kept as the cause.
    for answer in (status(500), raises(httpx2.ReadTimeout), raises(httpx2.ConnectError)):
        with pytest.raises(AIError) as error:
            provider(StubAI(answer)).suggest("Learned Rust")
        assert error.value.__cause__ is None
        assert error.value.__suppress_context__


# --- Privacy ---

ENTRY_TEXT = "Negotiated the Zephyrquartz contract renewal"
RESULT_IMPACT = "Saved Xylobank 40 percent"
TAG_NAMES = ("Quokkaproject", "Tangerinewave")
SUGGESTED_TAGS = ["Glimmerlake", "Fennelroad"]
SUMMARY_TEXT = "The Wobblefrost quarter went well"
PRIVATE = [API_KEY, ENTRY_TEXT, RESULT_IMPACT, *TAG_NAMES, *SUGGESTED_TAGS, SUMMARY_TEXT]


def test_ai_openai_logs_model_status_and_duration_but_no_key_or_content(caplog):
    caplog.set_level(logging.DEBUG)
    entries = [summary_entry(text=ENTRY_TEXT, result_impact=RESULT_IMPACT, tags=TAG_NAMES)]
    errors: list[AIError] = []

    # Success, invalid output, every kind of error, and an error answer that echoes content.
    assert (
        provider(StubAI(suggestion_answer("Learning", SUGGESTED_TAGS))).suggest(ENTRY_TEXT).tags
        == SUGGESTED_TAGS
    )
    assert provider(StubAI(completion(SUMMARY_TEXT))).summarise(entries) == SUMMARY_TEXT
    echo = lambda request: httpx2.Response(  # noqa: E731
        400, json={"error": {"message": f"{ENTRY_TEXT} {API_KEY} {SUMMARY_TEXT}"}}
    )
    answers = [
        suggestion_answer(ENTRY_TEXT, SUGGESTED_TAGS),
        completion(SUMMARY_TEXT + " not json"),
        raises(httpx2.ReadTimeout),
        raises(httpx2.ConnectError),
        status(401),
        status(429),
        status(500),
        echo,
        lambda request: httpx2.Response(200, text=f"<html>{ENTRY_TEXT}</html>"),
    ]
    for answer in answers:
        ai = provider(StubAI(answer))
        for call in (lambda ai=ai: ai.suggest(ENTRY_TEXT), lambda ai=ai: ai.summarise(entries)):
            try:
                call()
            except AIError as error:
                errors.append(error)

    # Every call fails except summarise with the first two answers, which are valid summaries.
    assert len(errors) == 2 * len(answers) - 2
    provider_logs = [r for r in caplog.records if r.name == "app.ai.openai_compatible"]
    assert len(provider_logs) == 2 + 2 * len(answers)
    messages = [record.getMessage() for record in provider_logs]
    assert all(MODEL in message and " ms" in message for message in messages)
    assert any("status 200" in message for message in messages)
    assert any("status 429" in message for message in messages)
    assert any("status none" in message for message in messages)
    for text in PRIVATE:
        assert text not in caplog.text
        for error in errors:
            assert text not in str(error)
            assert text not in repr(error)
