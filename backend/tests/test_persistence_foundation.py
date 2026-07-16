"""Persistence configuration and lazy-AWS-client guarantees.

The app-memory branch originally carried a second config system
(APP_ENV / APP_PERSISTENCE_BACKEND via load_persistence_settings). That was
dropped in favour of this repo's per-table DDB_*_TABLE gating, so these tests
cover the surviving contract: each table opts in independently, the branch's
DYNAMODB_* spellings still resolve to the same settings, and nothing imports
boto3 or touches AWS until a store actually needs a session.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.config import get_settings
from backend.app.dynamodb_client import create_dynamodb_session, get_dynamodb_client, get_dynamodb_resource
from backend.app.stores import (
    SQLiteFeedbackStore,
    SQLiteRecurringQuestionStore,
    feedback_store,
    recurring_question_store,
)


DDB_ENV_NAMES = (
    "DDB_CONFLICTS_TABLE", "DDB_UPLOADS_TABLE", "DDB_REGISTRY_TABLE",
    "DDB_PERMISSIONS_TABLE", "DDB_DRAFTS_TABLE", "DDB_FEEDBACK_TABLE",
    "DDB_RECURRING_QUESTIONS_TABLE",
    "DYNAMODB_CONFLICTS_TABLE", "DYNAMODB_UPLOADS_TABLE", "DYNAMODB_SOURCE_REGISTRY_TABLE",
    "DYNAMODB_ACCESS_CONTROL_TABLE", "DYNAMODB_DRAFT_VERSIONS_TABLE", "DYNAMODB_FEEDBACK_TABLE",
    "DYNAMODB_RECURRING_QUESTIONS_TABLE",
    "AWS_PROFILE", "DYNAMODB_ENDPOINT_URL",
)


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in DDB_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_settings_default_to_sqlite_for_every_table(clean_env: pytest.MonkeyPatch) -> None:
    settings = get_settings()

    assert settings.conflicts_aws is False
    assert settings.uploads_aws is False
    assert settings.registry_aws is False
    assert settings.permissions_aws is False
    assert settings.drafts_aws is False
    assert settings.feedback_aws is False
    assert settings.recurring_questions_aws is False


def test_each_table_opts_into_dynamodb_independently(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DDB_FEEDBACK_TABLE", "feedback-test")

    settings = get_settings()

    assert settings.feedback_aws is True
    assert settings.ddb_feedback_table == "feedback-test"
    # Naming one table must not drag the rest onto AWS.
    assert settings.conflicts_aws is False
    assert settings.recurring_questions_aws is False


def test_app_memory_branch_dynamodb_env_names_are_accepted_as_aliases(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The table names in Yaza_DynamoDB_Work_Summary.md §7 must configure these stores."""
    clean_env.setenv("DYNAMODB_CONFLICTS_TABLE", "policy-intelligence-conflicts")
    clean_env.setenv("DYNAMODB_FEEDBACK_TABLE", "policy-intelligence-feedback")
    clean_env.setenv("DYNAMODB_RECURRING_QUESTIONS_TABLE", "policy-intelligence-recurring-questions")
    clean_env.setenv("DYNAMODB_ACCESS_CONTROL_TABLE", "policy-intelligence-access-control")
    clean_env.setenv("DYNAMODB_SOURCE_REGISTRY_TABLE", "policy-intelligence-source-registry")
    clean_env.setenv("DYNAMODB_DRAFT_VERSIONS_TABLE", "policy-intelligence-draft-versions")

    settings = get_settings()

    assert settings.ddb_conflicts_table == "policy-intelligence-conflicts"
    assert settings.ddb_feedback_table == "policy-intelligence-feedback"
    assert settings.ddb_recurring_questions_table == "policy-intelligence-recurring-questions"
    # access-control / source-registry / draft-versions are this repo's
    # permissions / registry / drafts tables under the branch's names.
    assert settings.ddb_permissions_table == "policy-intelligence-access-control"
    assert settings.ddb_registry_table == "policy-intelligence-source-registry"
    assert settings.ddb_drafts_table == "policy-intelligence-draft-versions"


def test_ddb_names_win_over_dynamodb_aliases(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DDB_REGISTRY_TABLE", "from-cdk")
    clean_env.setenv("DYNAMODB_SOURCE_REGISTRY_TABLE", "from-script")

    assert get_settings().ddb_registry_table == "from-cdk"


def test_store_selection_never_imports_boto3(clean_env: pytest.MonkeyPatch) -> None:
    def unexpected_boto3_import() -> object:
        raise AssertionError("boto3 must not load while merely selecting a store")

    clean_env.setattr("backend.app.dynamodb_client._boto3", unexpected_boto3_import)

    assert isinstance(feedback_store(), SQLiteFeedbackStore)
    assert isinstance(recurring_question_store(), SQLiteRecurringQuestionStore)


def test_dynamodb_helpers_use_profile_and_endpoint_without_aws_calls(
    clean_env: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    class FakeSession:
        def resource(self, service_name: str, **kwargs: str) -> object:
            calls.append(("resource", (service_name, kwargs)))
            return object()

        def client(self, service_name: str, **kwargs: str) -> object:
            calls.append(("client", (service_name, kwargs)))
            return object()

    def fake_session(**kwargs: str) -> FakeSession:
        calls.append(("session", kwargs))
        return FakeSession()

    clean_env.setattr(
        "backend.app.dynamodb_client._boto3",
        lambda: SimpleNamespace(Session=fake_session),
    )
    clean_env.setenv("AWS_REGION", "us-west-2")
    clean_env.setenv("AWS_PROFILE", "csub-policy")
    clean_env.setenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")

    create_dynamodb_session()
    get_dynamodb_resource()
    get_dynamodb_client()

    assert calls[0] == ("session", {"profile_name": "csub-policy", "region_name": "us-west-2"})
    assert ("resource", ("dynamodb", {"endpoint_url": "http://localhost:8000"})) in calls
    assert ("client", ("dynamodb", {"endpoint_url": "http://localhost:8000"})) in calls
