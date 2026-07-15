from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.config import PersistenceConfigurationError, load_persistence_settings
from backend.app.dynamodb_client import create_dynamodb_session, get_dynamodb_client, get_dynamodb_resource
from backend.app.stores import get_store_factory


def test_persistence_settings_default_to_sqlite() -> None:
    settings = load_persistence_settings({})

    assert settings.app_env == "development"
    assert settings.backend == "sqlite"
    assert settings.aws_region == "us-west-2"
    assert settings.aws_profile is None
    assert settings.dynamodb_conflicts_table == "policy-intelligence-conflicts"


def test_persistence_settings_read_dynamodb_environment() -> None:
    settings = load_persistence_settings(
        {
            "APP_PERSISTENCE_BACKEND": "dynamodb",
            "APP_ENV": "production",
            "AWS_REGION": "us-east-1",
            "AWS_PROFILE": "policy-demo",
            "DYNAMODB_ENDPOINT_URL": "http://localhost:8000",
            "DYNAMODB_CONFLICTS_TABLE": "conflicts-test",
            "DYNAMODB_FEEDBACK_TABLE": "feedback-test",
            "DYNAMODB_RECURRING_QUESTIONS_TABLE": "questions-test",
            "DYNAMODB_ACCESS_CONTROL_TABLE": "access-control-test",
            "DYNAMODB_SOURCE_REGISTRY_TABLE": "source-registry-test",
            "DYNAMODB_DRAFT_VERSIONS_TABLE": "draft-versions-test",
        }
    )

    assert settings.backend == "dynamodb"
    assert settings.aws_region == "us-east-1"
    assert settings.aws_profile == "policy-demo"
    assert settings.dynamodb_endpoint_url == "http://localhost:8000"
    assert settings.dynamodb_feedback_table == "feedback-test"
    assert settings.dynamodb_access_control_table == "access-control-test"


def test_production_requires_dynamodb_backend() -> None:
    with pytest.raises(
        PersistenceConfigurationError,
        match="APP_ENV=production requires APP_PERSISTENCE_BACKEND=dynamodb",
    ):
        load_persistence_settings({"APP_ENV": "production"})


def test_production_dynamodb_configuration_is_valid() -> None:
    settings = load_persistence_settings(
        {"APP_ENV": "production", "APP_PERSISTENCE_BACKEND": "dynamodb"}
    )

    assert settings.app_env == "production"
    assert settings.backend == "dynamodb"
    assert settings.dynamodb_source_registry_table == "policy-intelligence-source-registry"


def test_production_rejects_explicitly_blank_dynamodb_table_name() -> None:
    with pytest.raises(PersistenceConfigurationError, match="DYNAMODB_ACCESS_CONTROL_TABLE"):
        load_persistence_settings(
            {
                "APP_ENV": "production",
                "APP_PERSISTENCE_BACKEND": "dynamodb",
                "DYNAMODB_ACCESS_CONTROL_TABLE": " ",
            }
        )


def test_unknown_persistence_backend_fails_clearly() -> None:
    with pytest.raises(PersistenceConfigurationError, match="APP_PERSISTENCE_BACKEND"):
        load_persistence_settings({"APP_PERSISTENCE_BACKEND": "postgres"})


def test_store_factory_defaults_to_sqlite_without_creating_aws_clients() -> None:
    factory = get_store_factory(load_persistence_settings({}))

    assert factory.uses_sqlite is True
    assert factory.uses_dynamodb is False
    with pytest.raises(RuntimeError, match="APP_PERSISTENCE_BACKEND"):
        factory.dynamodb_resource()


def test_dynamodb_selection_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_boto3_import() -> object:
        raise AssertionError("boto3 must not load while merely selecting DynamoDB")

    monkeypatch.setattr("backend.app.dynamodb_client._boto3", unexpected_boto3_import)
    factory = get_store_factory(
        load_persistence_settings({"APP_PERSISTENCE_BACKEND": "dynamodb"})
    )

    assert factory.uses_dynamodb is True


def test_dynamodb_helpers_use_profile_and_endpoint_without_aws_calls(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr(
        "backend.app.dynamodb_client._boto3",
        lambda: SimpleNamespace(Session=fake_session),
    )
    settings = load_persistence_settings(
        {
            "APP_PERSISTENCE_BACKEND": "dynamodb",
            "AWS_REGION": "us-west-2",
            "AWS_PROFILE": "policy-demo",
            "DYNAMODB_ENDPOINT_URL": "http://localhost:8000",
        }
    )

    create_dynamodb_session(settings)
    get_dynamodb_resource(settings)
    get_dynamodb_client(settings)

    assert calls[0] == ("session", {"profile_name": "policy-demo", "region_name": "us-west-2"})
    assert ("resource", ("dynamodb", {"endpoint_url": "http://localhost:8000"})) in calls
    assert ("client", ("dynamodb", {"endpoint_url": "http://localhost:8000"})) in calls
