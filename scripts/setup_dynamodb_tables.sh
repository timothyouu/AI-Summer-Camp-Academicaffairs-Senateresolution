#!/usr/bin/env bash
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-csub-policy}"
AWS_REGION="${AWS_REGION:-us-west-2}"
readonly AWS_PROFILE AWS_REGION

aws_cli=(aws --no-cli-pager --profile "$AWS_PROFILE" --region "$AWS_REGION")

readonly ACCESS_CONTROL_GSIS='[{"IndexName":"source-key-user-index","KeySchema":[{"AttributeName":"source_key","KeyType":"HASH"},{"AttributeName":"user_id","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]'
readonly SOURCE_REGISTRY_GSIS='[{"IndexName":"status-last-synced-index","KeySchema":[{"AttributeName":"status","KeyType":"HASH"},{"AttributeName":"last_synced","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}},{"IndexName":"source-type-last-synced-index","KeySchema":[{"AttributeName":"source_type","KeyType":"HASH"},{"AttributeName":"last_synced","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}},{"IndexName":"owner-last-synced-index","KeySchema":[{"AttributeName":"owner","KeyType":"HASH"},{"AttributeName":"last_synced","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]'
readonly DRAFT_VERSION_GSIS='[{"IndexName":"owner-updated-index","KeySchema":[{"AttributeName":"owner_user_id","KeyType":"HASH"},{"AttributeName":"updated_at","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]'

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

ensure_table() {
  local table_name="$1"
  local describe_output
  local describe_status
  shift

  set +e
  describe_output="$("${aws_cli[@]}" dynamodb describe-table --table-name "$table_name" 2>&1)"
  describe_status=$?
  set -e

  if [[ "$describe_status" -eq 0 ]]; then
    echo "Table $table_name already exists; leaving its schema unchanged."
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
ensure_table "policy-intelligence-conflicts" \
  --attribute-definitions AttributeName=conflict_id,AttributeType=S \
  --key-schema AttributeName=conflict_id,KeyType=HASH
ensure_table "policy-intelligence-feedback" \
  --attribute-definitions AttributeName=feedback_id,AttributeType=S \
  --key-schema AttributeName=feedback_id,KeyType=HASH
ensure_table "policy-intelligence-recurring-questions" \
  --attribute-definitions AttributeName=question_id,AttributeType=S \
  --key-schema AttributeName=question_id,KeyType=HASH
ensure_table "policy-intelligence-access-control" \
  --attribute-definitions AttributeName=user_id,AttributeType=S AttributeName=source_key,AttributeType=S \
  --key-schema AttributeName=user_id,KeyType=HASH AttributeName=source_key,KeyType=RANGE \
  --global-secondary-indexes "$ACCESS_CONTROL_GSIS"
ensure_table "policy-intelligence-source-registry" \
  --attribute-definitions AttributeName=source_id,AttributeType=S AttributeName=status,AttributeType=S AttributeName=last_synced,AttributeType=S AttributeName=source_type,AttributeType=S AttributeName=owner,AttributeType=S \
  --key-schema AttributeName=source_id,KeyType=HASH \
  --global-secondary-indexes "$SOURCE_REGISTRY_GSIS"
ensure_table "policy-intelligence-draft-versions" \
  --attribute-definitions AttributeName=draft_id,AttributeType=S AttributeName=version_id,AttributeType=S AttributeName=owner_user_id,AttributeType=S AttributeName=updated_at,AttributeType=S \
  --key-schema AttributeName=draft_id,KeyType=HASH AttributeName=version_id,KeyType=RANGE \
  --global-secondary-indexes "$DRAFT_VERSION_GSIS"
echo "DynamoDB table setup complete."
