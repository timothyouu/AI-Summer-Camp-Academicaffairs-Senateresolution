#!/usr/bin/env bash
#
# Verify every DynamoDB table the backend reads: ACTIVE status, a conditional
# write + delete healthcheck, and GSI status. Writes nothing that survives the
# run and prints no credentials.
#
# Key schemas match scripts/setup_dynamodb_tables.sh and the stores in
# backend/app/. Run setup first if a table is missing.
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-csub-policy}"
AWS_REGION="${AWS_REGION:-us-west-2}"
readonly AWS_PROFILE AWS_REGION

aws_cli=(aws --no-cli-pager --profile "$AWS_PROFILE" --region "$AWS_REGION")

verify_table() {
  local table_name="$1"
  local key_json="$2"
  local put_condition="$3"
  local put_names="$4"
  local table_status
  local created_at
  local item

  echo "Describing $table_name..."
  table_status="$("${aws_cli[@]}" dynamodb describe-table \
    --table-name "$table_name" \
    --query 'Table.TableStatus' \
    --output text)"
  if [[ "$table_status" != "ACTIVE" ]]; then
    echo "Table $table_name is not ACTIVE (current status: $table_status)." >&2
    return 1
  fi

  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  item="${key_json%?},\"check_type\":{\"S\":\"dynamodb_healthcheck\"},\"created_at\":{\"S\":\"$created_at\"}}"

  echo "Writing and deleting a healthcheck item in $table_name..."
  "${aws_cli[@]}" dynamodb put-item \
    --table-name "$table_name" \
    --item "$item" \
    --condition-expression "$put_condition" \
    --expression-attribute-names "$put_names"

  "${aws_cli[@]}" dynamodb delete-item \
    --table-name "$table_name" \
    --key "$key_json" \
    --condition-expression '#check_type = :check_type AND #created_at = :created_at' \
    --expression-attribute-names '{"#check_type":"check_type","#created_at":"created_at"}' \
    --expression-attribute-values "{\":check_type\":{\"S\":\"dynamodb_healthcheck\"},\":created_at\":{\"S\":\"$created_at\"}}"

  echo "Healthcheck passed for $table_name."
}

verify_gsi() {
  local table_name="$1"
  local index_name="$2"
  local index_status

  index_status="$("${aws_cli[@]}" dynamodb describe-table \
    --table-name "$table_name" \
    --query "Table.GlobalSecondaryIndexes[?IndexName=='$index_name'].IndexStatus | [0]" \
    --output text)"
  if [[ "$index_status" != "ACTIVE" ]]; then
    echo "GSI $index_name on $table_name is not ACTIVE (current status: $index_status)." >&2
    return 1
  fi
  echo "GSI $index_name on $table_name is ACTIVE."
}

echo "Checking AWS caller identity..."
"${aws_cli[@]}" sts get-caller-identity

echo "Listing DynamoDB tables in $AWS_REGION..."
"${aws_cli[@]}" dynamodb list-tables --output table

verify_table "policy-intelligence-conflicts" \
  '{"id":{"S":"healthcheck_conflict"}}' \
  'attribute_not_exists(#pk)' \
  '{"#pk":"id"}'
verify_table "policy-intelligence-uploads" \
  '{"id":{"S":"healthcheck_upload"}}' \
  'attribute_not_exists(#pk)' \
  '{"#pk":"id"}'
verify_table "policy-intelligence-feedback" \
  '{"feedback_id":{"S":"healthcheck_feedback"}}' \
  'attribute_not_exists(#pk)' \
  '{"#pk":"feedback_id"}'
verify_table "policy-intelligence-recurring-questions" \
  '{"question_id":{"S":"healthcheck_recurring"}}' \
  'attribute_not_exists(#pk)' \
  '{"#pk":"question_id"}'
verify_table "policy-intelligence-access-control" \
  '{"user_email":{"S":"healthcheck@example.edu"},"source_type":{"S":"healthcheck_source"}}' \
  'attribute_not_exists(#pk) AND attribute_not_exists(#sk)' \
  '{"#pk":"user_email","#sk":"source_type"}'
verify_table "policy-intelligence-source-registry" \
  '{"id":{"S":"healthcheck_source_registry"}}' \
  'attribute_not_exists(#pk)' \
  '{"#pk":"id"}'
verify_table "policy-intelligence-draft-versions" \
  '{"draft_id":{"S":"healthcheck_draft"},"version":{"N":"0"}}' \
  'attribute_not_exists(#pk) AND attribute_not_exists(#sk)' \
  '{"#pk":"draft_id","#sk":"version"}'

verify_gsi "policy-intelligence-conflicts" "topic-index"
verify_gsi "policy-intelligence-conflicts" "status-index"
verify_gsi "policy-intelligence-uploads" "status-index"
echo "DynamoDB verification completed successfully."
