"""The hosted alert rules for Grafana Cloud, read from the repository (issue #117).

`ops/grafana-cloud/alert-rules.yaml` holds one rule per hosted environment, production and dev,
in Prometheus rule-file format, which the product owner imports in Grafana Cloud's UI as
Grafana-managed rules (`ops/deployment.md`, "Hosted alerts: Grafana Cloud"). Each rule's query
is the local rule's query from `ops/grafana/alerting/user-impact.yaml` with an environment
matcher and the 5% threshold added, so an edit to one rule without the other fails here.

No requirement ID covers the alert rules (product-spec.md §9 "Observability" has none), so the
test names describe the behaviour. The file is only parsed: no network connection, no Grafana.
The live run of the same file in the local stack is section D of #117
(`docs/observability.md`, "Alerts").
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
HOSTED_PATH = ROOT / "ops" / "grafana-cloud" / "alert-rules.yaml"
LOCAL_PATH = ROOT / "ops" / "grafana" / "alerting" / "user-impact.yaml"
HOSTED = yaml.safe_load(HOSTED_PATH.read_text(encoding="utf-8"))
LOCAL = yaml.safe_load(LOCAL_PATH.read_text(encoding="utf-8"))

ENVIRONMENTS = ("production", "dev")
SERVICE_MATCHER = 'service_name="winlog-backend"'
DESCRIPTION = (
    'See docs/observability.md, section "Alerts", for what the rule measures and what to check.'
)


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _rules() -> list[dict]:
    return HOSTED["groups"][0]["rules"]


def _local_expr() -> str:
    rules = [rule for group in LOCAL["groups"] for rule in group["rules"]]
    (rule,) = [rule for rule in rules if rule["uid"] == "winlog-server-errors"]
    (query,) = [item for item in rule["data"] if item["refId"] == "A"]
    return query["model"]["expr"]


def _expected_expr(environment: str) -> str:
    local = _normalise(_local_expr())
    matcher = f'{SERVICE_MATCHER}, deployment_environment_name="{environment}"'
    return local.replace(SERVICE_MATCHER, matcher) + " > 0.05"


def _texts(rule: dict) -> list[str]:
    return [
        *rule["labels"].keys(),
        *map(str, rule["labels"].values()),
        *rule["annotations"].values(),
    ]


def test_hosted_alert_rules_file_has_namespace_and_one_group():
    assert list(HOSTED) == ["namespace", "groups"]
    assert HOSTED["namespace"] == "Winlog"
    assert len(HOSTED["groups"]) == 1
    group = HOSTED["groups"][0]
    assert group["name"] == "user-impact"
    assert group["interval"] == "1m"


def test_hosted_alert_rules_file_has_the_shape_the_import_form_requires():
    assert isinstance(HOSTED["namespace"], str)
    assert isinstance(HOSTED["groups"], list)
    for group in HOSTED["groups"]:
        assert isinstance(group["name"], str)
        assert isinstance(group["rules"], list)
        for rule in group["rules"]:
            assert isinstance(rule["alert"], str)
            assert isinstance(rule["expr"], str)
            assert "record" not in rule
            assert isinstance(rule["labels"], dict)
            assert isinstance(rule["annotations"], dict)
            # The import form refuses a `for` that is not a string.
            assert isinstance(rule["for"], str)


def test_hosted_alert_rules_are_one_per_environment_production_first():
    rules = _rules()
    assert [rule["alert"] for rule in rules] == [
        "Server errors above 5% in production",
        "Server errors above 5% in dev",
    ]
    assert [rule["labels"]["__grafana_alert_rule_uid__"] for rule in rules] == [
        "winlog-server-errors-production",
        "winlog-server-errors-dev",
    ]
    assert [rule["labels"]["environment"] for rule in rules] == list(ENVIRONMENTS)
    for rule in rules:
        assert set(rule) == {"alert", "expr", "for", "labels", "annotations"}
        assert rule["for"] == "1m"


def test_hosted_alert_rules_query_is_the_local_query_per_environment_above_5_percent():
    local = _normalise(_local_expr())
    # The local query has the service matcher in both selectors and no threshold.
    assert local.count(SERVICE_MATCHER) == 2
    assert ">" not in local
    for rule, environment in zip(_rules(), ENVIRONMENTS, strict=True):
        assert _normalise(rule["expr"]) == _expected_expr(environment)


def test_hosted_alert_rules_query_aggregates_without_labels_from_the_data():
    for rule in _rules():
        expr = rule["expr"]
        assert expr.count("sum(") == 2
        assert re.search(r"\b(by|without)\b", expr) is None


def test_hosted_alert_rules_labels_are_fixed_text():
    for rule, environment in zip(_rules(), ENVIRONMENTS, strict=True):
        assert rule["labels"] == {
            "__grafana_alert_rule_uid__": f"winlog-server-errors-{environment}",
            "severity": "critical",
            "service": "winlog-backend",
            "environment": environment,
        }


def test_hosted_alert_rules_annotations_are_fixed_text():
    for rule, environment in zip(_rules(), ENVIRONMENTS, strict=True):
        assert rule["annotations"] == {
            "summary": (
                f"More than 5% of the backend's requests in {environment} failed with a server "
                "error (5xx) in the last 5 minutes."
            ),
            "description": DESCRIPTION,
        }


def test_hosted_alert_rules_labels_and_annotations_hold_no_template_address_or_url():
    for rule in _rules():
        for text in _texts(rule):
            assert "{{" not in text
            assert "@" not in text
            assert "://" not in text


def test_hosted_alert_rules_file_holds_no_address_url_or_data_source_uid():
    text = HOSTED_PATH.read_text(encoding="utf-8")
    assert "@" not in text
    assert "://" not in text
    assert "www." not in text
    assert re.search(r"datasource|uid:", text, re.IGNORECASE) is None


def test_hosted_alert_rules_file_header_comment_says_how_it_is_loaded():
    lines = HOSTED_PATH.read_text(encoding="utf-8").splitlines()
    header = " ".join(line.lstrip("# ") for line in lines if line.startswith("#"))
    assert lines[0].startswith("#")
    assert "#117" in header
    assert "Grafana Cloud does not load this file by itself" in header
    assert 'ops/deployment.md, "Hosted alerts: Grafana Cloud"' in header
    assert "docker-compose.yml does not mount it" in header
    assert 'docs/observability.md, section "Alerts"' in header


def test_hosted_alert_rules_file_is_not_mounted_in_docker_compose():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "grafana-cloud" not in compose
    assert "./ops/grafana/alerting/user-impact.yaml:" in compose
