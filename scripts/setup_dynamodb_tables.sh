#!/usr/bin/env bash
#
# Create the DynamoDB tables the backend reads, idempotently, without CDK.
#
# This is the DynamoDB-only path: `cdk deploy` (see infra/README.md) is the full
# target architecture and also creates these tables, but it stands up OpenSearch
# Serverless and a Bedrock Knowledge Base too, which is slow and costly to spin
# up just to exercise persistence. Use this script to provision/verify DynamoDB
# on its own; use CDK for the real deploy.
#
# Key schemas below are the ones backend/app/*.py actually reads. They differ
# from the original app-memory branch's schemas (conflict_id / source_id /
# user_id+source_key / draft_id+version_id), because the registry, permissions
# and drafting APIs already existed against these keys. If a table from that
# earlier round is still present, this script REFUSES to touch it and tells you
# what to do rather than silently leaving a table the app cannot read.
#
# This script never deletes or mutates an existing table.
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-csub-policy}"
AWS_REGION="${AWS_REGION:-us-west-2}"
readonly AWS_PROFILE AWS_REGION

aws_cli=(aws --no-cli-pager --profile "$AWS_PROFILE" --region "$AWS_REGION")

# GSIs mirror infra/stacks/policy_intelligence_stack.py so both provisioning
# paths yield equivalent tables. The backend currently lists via Scan (fine at
# demo scale, per Yaza_DynamoDB_Work_Summary.md §10); these exist so query-based
# access patterns can be adopted without a table rebuild.
readonly CONFLICT_GSIS='[{"IndexName":"topic-index","KeySchema":[{"AttributeName":"topic","KeyType":"HASH"},{"AttributeName":"updated_at","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}},{"IndexName":"status-index","KeySchema":[{"AttributeName":"status","KeyType":"HASH"},{"AttributeName":"updated_at","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]'
readonly UPLOAD_GSIS='[{"IndexName":"status-index","KeySchema":[{"AttributeName":"status","KeyType":"HASH"},{"AttributeName":"filename","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]'

wait_for_active() {
  local table_name="$1"
  local table_status
  local attempt

  for attempt in {1..40}; do
    table_status="$("${aws_cli[@]}" dynamodb describe-table \
      --table-name "$table_name" \
      --query 'Table.TableStatus' \
      --output text)"
    if [[ "$table_status" == "ACTIVE" ]]; then
      echo "Table $table_name is ACTIVE."
      return 0
    fi

    echo "Waiting for $table_name to become ACTIVE (current status: $table_status)..."
    sleep 3
  done

  echo "Timed out waiting for $table_name to become ACTIVE." >&2
  return 1
}

# Render a table's key schema as "attr:HASH" or "attr:HASH,attr:RANGE".
# Each key is queried by KeyType rather than by position: DescribeTable is not
# documented to return KeySchema in HASH-then-RANGE order, so relying on the
# array order would make this check quietly order-dependent.
actual_key_schema() {
  local table_name="$1"
  local hash_key range_key

  hash_key="$("${aws_cli[@]}" dynamodb describe-table --table-name "$table_name" \
    --query "Table.KeySchema[?KeyType=='HASH'].AttributeName | [0]" --output text)"
  range_key="$("${aws_cli[@]}" dynamodb describe-table --table-name "$table_name" \
    --query "Table.KeySchema[?KeyType=='RANGE'].AttributeName | [0]" --output text)"

  if [[ -z "$range_key" || "$range_key" == "None" ]]; then
    echo "${hash_key}:HASH"
  else
    echo "${hash_key}:HASH,${range_key}:RANGE"
  fi
}

# ensure_table <name> <expected-key-schema> [create-args...]
ensure_table() {
  local table_name="$1"
  local expected_schema="$2"
  shift 2
  local describe_output
  local describe_status
  local found_schema

  set +e
  describe_output="$("${aws_cli[@]}" dynamodb describe-table --table-name "$table_name" 2>&1)"
  describe_status=$?
  set -e

  if [[ "$describe_status" -eq 0 ]]; then
    found_schema="$(actual_key_schema "$table_name")"
    if [[ "$found_schema" != "$expected_schema" ]]; then
      cat >&2 <<EOF

ERROR: $table_name exists with a key schema this backend cannot read.
         found:    $found_schema
         expected: $expected_schema

This table predates the merge of the app-memory branch and uses its original
key schema. Nothing was changed. To re-provision it correctly:

  1. Confirm it holds nothing you need:
       aws dynamodb scan --table-name $table_name --max-items 5 \\
         --profile $AWS_PROFILE --region $AWS_REGION
  2. If it is empty or disposable, delete it, then re-run this script:
       aws dynamodb delete-table --table-name $table_name \\
         --profile $AWS_PROFILE --region $AWS_REGION

If it holds data worth keeping, stop and migrate it deliberately instead.
EOF
      return 1
    fi
    echo "Table $table_name already exists with the expected key schema."
    wait_for_active "$table_name"
    return 0
  fi

  if [[ "$describe_output" != *"ResourceNotFoundException"* ]]; then
    echo "Unable to inspect DynamoDB table $table_name:" >&2
    echo "$describe_output" >&2
    return "$describe_status"
  fi

  echo "Creating table $table_name..."
  "${aws_cli[@]}" dynamodb create-table \
    --table-name "$table_name" \
    --billing-mode PAY_PER_REQUEST \
    "$@" \
    --query 'TableDescription.TableStatus' \
    --output text
  wait_for_active "$table_name"
}

echo "Configuring DynamoDB tables in $AWS_REGION using AWS profile $AWS_PROFILE."

# stores.py DynamoDBConflictStore — partition key "id".
ensure_table "policy-intelligence-conflicts" "id:HASH" \
  --attribute-definitions AttributeName=id,AttributeType=S AttributeName=topic,AttributeType=S \
    AttributeName=status,AttributeType=S AttributeName=updated_at,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --global-secondary-indexes "$CONFLICT_GSIS"

# stores.py DynamoDBUploadStore — was missing from the app-memory branch's set.
ensure_table "policy-intelligence-uploads" "id:HASH" \
  --attribute-definitions AttributeName=id,AttributeType=S AttributeName=status,AttributeType=S \
    AttributeName=filename,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --global-secondary-indexes "$UPLOAD_GSIS"

# registry.py DynamoDBRegistryStore — partition key "id".
ensure_table "policy-intelligence-source-registry" "id:HASH" \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH

# permissions.py DynamoDBPermissionStore — user_email + source_type.
ensure_table "policy-intelligence-access-control" "user_email:HASH,source_type:RANGE" \
  --attribute-definitions AttributeName=user_email,AttributeType=S AttributeName=source_type,AttributeType=S \
  --key-schema AttributeName=user_email,KeyType=HASH AttributeName=source_type,KeyType=RANGE

# drafting.py DynamoDBDraftStore — draft_id + numeric version.
ensure_table "policy-intelligence-draft-versions" "draft_id:HASH,version:RANGE" \
  --attribute-definitions AttributeName=draft_id,AttributeType=S AttributeName=version,AttributeType=N \
  --key-schema AttributeName=draft_id,KeyType=HASH AttributeName=version,KeyType=RANGE

# stores.py DynamoDBFeedbackStore — unchanged from the app-memory branch.
ensure_table "policy-intelligence-feedback" "feedback_id:HASH" \
  --attribute-definitions AttributeName=feedback_id,AttributeType=S \
  --key-schema AttributeName=feedback_id,KeyType=HASH

# stores.py DynamoDBRecurringQuestionStore — unchanged from the app-memory branch.
ensure_table "policy-intelligence-recurring-questions" "question_id:HASH" \
  --attribute-definitions AttributeName=question_id,AttributeType=S \
  --key-schema AttributeName=question_id,KeyType=HASH

echo "DynamoDB table setup complete."
