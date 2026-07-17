from __future__ import annotations

import ast
from pathlib import Path
import re

import pytest

from backend.app.config import DEFAULT_BEDROCK_MODEL_ID
from infra.deployment_context import boolean_context


STACK_PATH = Path(__file__).resolve().parents[1] / "stacks" / "policy_intelligence_stack.py"


def test_cognito_context_defaults_off_and_explicitly_enables() -> None:
    assert boolean_context(None) is False
    assert boolean_context(False) is False
    assert boolean_context("false") is False
    assert boolean_context(True) is True
    assert boolean_context("true") is True


def test_cognito_context_rejects_ambiguous_values() -> None:
    with pytest.raises(ValueError, match="boolean CDK context"):
        boolean_context("enabled")


def test_stack_uses_one_cognito_switch_for_lambda_and_gateway() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    api_lambda_source = ast.unparse(methods["_build_api_lambda"])
    http_api_source = ast.unparse(methods["_build_http_api"])
    init_source = ast.unparse(methods["__init__"])

    assert "if cognito_enabled:" in api_lambda_source
    assert "'COGNITO_USER_POOL_ID'" in api_lambda_source
    assert "'COGNITO_CLIENT_ID'" in api_lambda_source
    assert "if cognito_enabled:" in http_api_source
    assert "HttpUserPoolAuthorizer" in http_api_source
    assert init_source.count("cognito_enabled=cognito_enabled") == 2


def test_both_deployed_cors_surfaces_allow_demo_identity_headers() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    allowed_headers_assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "API_ALLOWED_HEADERS"
            for target in node.targets
        )
    )
    methods = {
        node.name: ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert ast.literal_eval(allowed_headers_assignment.value) == [
        "Authorization",
        "Content-Type",
        "X-User-Email",
        "X-Role",
    ]
    assert "allow_headers=API_ALLOWED_HEADERS" in methods["_build_http_api"]
    assert "allowed_headers=API_ALLOWED_HEADERS" in methods["_build_agent_function_url"]


def test_api_lambda_receives_same_origins_as_deployed_cors_surfaces() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    methods = {
        node.name: ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "'FRONTEND_ORIGINS': ','.join(self._allowed_origins())" in methods[
        "_build_api_lambda"
    ]
    assert "allow_origins=self._allowed_origins()" in methods["_build_http_api"]
    assert "allowed_origins=self._allowed_origins()" in methods[
        "_build_agent_function_url"
    ]


def test_ingestion_bundle_copies_only_the_backend_package() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_ingestion_lambda"
    )
    source = ast.unparse(method)

    assert "tar -cf -" in source
    assert "backend/.venv" in source
    assert "backend | tar -xf - -C /asset-output" in source
    assert "cp -au" not in source


def test_lambda_bundles_do_not_ship_the_local_virtualenv() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    methods = {
        node.name: ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }

    for method_name in ("_build_catalog_scraper_lambda", "_build_api_lambda"):
        source = methods[method_name]
        assert "--exclude='./.venv'" in source
        assert "| tar -xf - -C /asset-output" in source
        assert "cp -au" not in source
        assert ";/^boto3/d" in source


def test_bedrock_data_source_and_guardrail_values_match_live_schema() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    corpus_prefixes = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "CORPUS_PREFIXES" for target in node.targets)
    )
    guardrail_method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_guardrail"
    )
    topic_names = [
        keyword.value.value
        for node in ast.walk(guardrail_method)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str)
    ]

    assert ast.literal_eval(corpus_prefixes) == ["corpus/"]
    assert topic_names
    assert all(re.fullmatch(r"[0-9A-Za-z\-_ !?.]+", name) for name in topic_names)


def test_bedrock_role_has_aoss_api_access_before_knowledge_base_creation() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    methods = {
        node.name: ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }

    role_source = methods["_build_opensearch_and_kb_role"]
    knowledge_base_source = methods["_build_knowledge_base"]

    assert "KnowledgeBaseAossApiPolicy" in role_source
    assert "actions=['aoss:APIAccessAll']" in role_source
    assert "resources=[collection.attr_arn]" in role_source
    assert "kb_aoss_policy.attach_to_role(kb_role)" in role_source
    assert "knowledge_base.node.add_dependency(kb_aoss_policy)" in knowledge_base_source


def test_api_lambda_role_allows_bedrock_converse_streaming() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_api_lambda"
    )
    runtime_statement = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and any(
            keyword.arg == "sid"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "BedrockRuntimeAccess"
            for keyword in node.keywords
        )
    )
    actions = next(
        keyword.value
        for keyword in runtime_statement.keywords
        if keyword.arg == "actions"
    )

    assert ast.literal_eval(actions) == [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
    ]


def test_api_lambda_role_allows_upload_ingestion_lifecycle() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_api_lambda"
    )
    ingestion_statement = next(
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and any(
            keyword.arg == "sid"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "BedrockKbIngestionStatus"
            for keyword in node.keywords
        )
    )
    keywords = {keyword.arg: keyword.value for keyword in ingestion_statement.keywords}

    assert ast.literal_eval(keywords["actions"]) == [
        "bedrock:ListDataSources",
        "bedrock:StartIngestionJob",
        "bedrock:GetIngestionJob",
    ]
    assert "knowledge_base.attr_knowledge_base_arn" in ast.unparse(keywords["resources"])


def test_api_lambda_pins_scp_compatible_regional_model() -> None:
    tree = ast.parse(STACK_PATH.read_text(encoding="utf-8"))
    model_id = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "BEDROCK_MODEL_ID" for target in node.targets)
    )
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_api_lambda"
    )

    assert ast.literal_eval(model_id) == DEFAULT_BEDROCK_MODEL_ID
    assert "'BEDROCK_MODEL_ID': BEDROCK_MODEL_ID" in ast.unparse(method)
    assert "'BEDROCK_GENERATION_ENABLED': 'false'" in ast.unparse(method)
