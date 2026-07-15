"""Custom-resource Lambda: creates/deletes the OpenSearch Serverless vector
index that Bedrock Knowledge Base reads/writes from.

Why this exists: CloudFormation/CDK has no native resource for an OpenSearch
Serverless *index* (only the collection). AWS's own reference patterns create
the index via a custom resource that signs a request to the collection's data
plane. We do that here with botocore's SigV4 signer + urllib, since botocore
ships in every AWS Lambda Python runtime — no pip-installed dependencies
(e.g. opensearch-py) are required, which matters because this repo's guard
hooks block package installs.

Wired up as the `on_event` handler behind a cdk.custom_resources.Provider in
infra/stacks/policy_intelligence_stack.py.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE = "aoss"
# 403/404/503 (and status 0 = connection failure) are how AOSS presents
# not-yet-propagated collections/permissions; anything else is a real error.
RETRYABLE_STATUSES = {0, 403, 404, 503}
CREATE_RETRY_WINDOW_SECONDS = 480.0


def _signed_request(
    method: str,
    url: str,
    region: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, str]:
    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials is None:
        raise RuntimeError("No AWS credentials available to the vector-index Lambda")

    data = json.dumps(body).encode("utf-8") if body is not None else b""
    request = AWSRequest(method=method, url=url, data=data, headers={"Content-Type": "application/json"})
    SigV4Auth(credentials, SERVICE, region).add_auth(request)
    prepared_headers = dict(request.headers.items())

    http_request = urllib.request.Request(url, data=data or None, headers=prepared_headers, method=method)
    try:
        with urllib.request.urlopen(http_request, timeout=25) as response:  # noqa: S310 - trusted AWS endpoint
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def _create_index(endpoint: str, region: str, index_name: str, vector_field: str, text_field: str, metadata_field: str, dimension: int) -> None:
    # `endpoint` is CfnCollection.attr_collection_endpoint, which already
    # includes the https:// scheme (e.g. https://<id>.<region>.aoss.amazonaws.com).
    url = f"{endpoint}/{index_name}"
    body = {
        "settings": {
            "index.knn": True,
        },
        "mappings": {
            "properties": {
                vector_field: {
                    "type": "knn_vector",
                    "dimension": dimension,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "space_type": "l2",
                    },
                },
                text_field: {"type": "text"},
                metadata_field: {"type": "text", "index": False},
            }
        },
    }
    # The collection and data-access policy report CloudFormation completion
    # before the data-plane endpoint and permissions finish propagating, so a
    # fresh deploy's first PUT often gets a transient 403/404/503. Retry with
    # backoff until the deadline instead of rolling back the stack.
    deadline = time.monotonic() + CREATE_RETRY_WINDOW_SECONDS
    attempt = 0
    while True:
        try:
            status, payload = _signed_request("PUT", url, region, body)
        except urllib.error.URLError as error:
            status, payload = 0, str(error)
        if 0 < status < 300 or "resource_already_exists_exception" in payload:
            break
        if status in RETRYABLE_STATUSES and time.monotonic() < deadline:
            attempt += 1
            wait = min(30.0, 2.0 ** attempt)
            logger.info("AOSS index %s not ready yet (%s); retrying in %.0fs", index_name, status or payload, wait)
            time.sleep(wait)
            continue
        raise RuntimeError(f"Failed to create AOSS index {index_name!r}: {status} {payload}")
    logger.info("AOSS index %s create response: %s %s", index_name, status, payload)


def _delete_index(endpoint: str, region: str, index_name: str) -> None:
    url = f"{endpoint}/{index_name}"
    status, payload = _signed_request("DELETE", url, region)
    # 404 is fine on delete — index may never have been created, or the
    # collection is already gone (e.g. stack rollback ordering).
    if status >= 300 and status != 404:
        logger.warning("AOSS index %s delete response: %s %s (ignored on stack teardown)", index_name, status, payload)


def on_event(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """CloudFormation custom-resource Provider entry point."""
    request_type = event["RequestType"]
    props = event["ResourceProperties"]

    endpoint: str = props["CollectionEndpoint"]
    region: str = props["Region"]
    index_name: str = props["IndexName"]
    vector_field: str = props.get("VectorField", "bedrock-knowledge-base-default-vector")
    text_field: str = props.get("TextField", "AMAZON_BEDROCK_TEXT_CHUNK")
    metadata_field: str = props.get("MetadataField", "AMAZON_BEDROCK_METADATA")
    dimension: int = int(props.get("Dimension", 1024))  # Titan Text Embeddings V2 default output size

    physical_id = f"aoss-index/{index_name}"

    if request_type in ("Create", "Update"):
        _create_index(endpoint, region, index_name, vector_field, text_field, metadata_field, dimension)
    elif request_type == "Delete":
        _delete_index(endpoint, region, index_name)
    else:
        raise ValueError(f"Unsupported RequestType: {request_type}")

    return {"PhysicalResourceId": physical_id}
