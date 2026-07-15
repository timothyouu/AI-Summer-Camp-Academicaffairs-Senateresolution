"""Single-stack CDK definition of the target AWS architecture in
implementation2.md §2 / §3 Phase A.

Resource map (see infra/README.md for the full deploy story):
  - S3 corpus bucket (handbook/, cba/, resolutions/, synthetic/ prefixes) with
    an ObjectCreated -> ingestion Lambda notification.
  - OpenSearch Serverless VECTORSEARCH collection (encryption/network/access
    policies + a custom-resource-created vector index) backing a Bedrock
    Knowledge Base (Titan Text Embeddings V2) with an S3 data source
    (~500 token / 20% overlap fixed-size chunking).
  - DynamoDB tables ConflictLog and Uploads.
  - Cognito User Pool (+ hosted UI domain, app client, `makers`/`employees`
    groups).
  - API Lambda (FastAPI app, handler app.lambda_entry.handler, asset root
    backend/) behind an API Gateway HTTP API with a Cognito JWT authorizer.
  - Ingestion Lambda (handler backend.lambda_handlers.ingestion.handler,
    asset root = repo root, since that module does an absolute
    `from backend.app... import` and needs `backend` importable as a
    top-level package) triggered by the S3 notification above.

Env var names on both Lambdas are pinned to exactly what
backend/app/config.py's get_settings() reads (BEDROCK_KB_ID,
DDB_CONFLICTS_TABLE, DDB_UPLOADS_TABLE, CORPUS_BUCKET,
COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID) — AWS_REGION is deliberately not
set since it's a reserved Lambda runtime env var. This worktree owns
`infra/` only; backend/app/lambda_entry.py and
backend/lambda_handlers/ingestion.py are Phase B code owned elsewhere.
Dependencies are pip-bundled into each asset via BundlingOptions (Docker
required at synth time) — see infra/README.md "Packaging note".
"""
from __future__ import annotations

from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_bedrock as bedrock,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_event_sources,
    aws_logs as logs,
    aws_opensearchserverless as aoss,
    aws_s3 as s3,
    aws_s3_notifications as s3_notifications,
    custom_resources as cr,
)
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_ROOT = Path(__file__).resolve().parents[1]

# Titan Text Embeddings V2 default output dimension (matches
# implementation2.md §2/§3: "Titan Text Embeddings V2 ... default chunking").
TITAN_EMBED_V2_DIMENSION = 1024
CHUNK_MAX_TOKENS = 500
CHUNK_OVERLAP_PERCENTAGE = 20
# "uploads/" is where backend/app/uploads.py's presigned-URL flow (AWS mode)
# writes newly uploaded files (`key = f"uploads/{filename}"`) — it must be in
# the data source's inclusion_prefixes or the live-ingestion demo step
# (implementation2.md §1 step 9) will upload successfully but never get
# synced into the Knowledge Base.
CORPUS_PREFIXES = ["handbook/", "cba/", "resolutions/", "synthetic/", "uploads/"]
VECTOR_INDEX_NAME = "policy-intelligence-index"
VECTOR_FIELD_NAME = "bedrock-knowledge-base-default-vector"
TEXT_FIELD_NAME = "AMAZON_BEDROCK_TEXT_CHUNK"
METADATA_FIELD_NAME = "AMAZON_BEDROCK_METADATA"

# Ingestion Lambda's asset root is the repo root (it needs `backend` importable
# as a top-level package — see _build_ingestion_lambda). Exclude everything
# that isn't backend/ so the zip stays small and doesn't ship frontend
# node_modules, git history, or the local SQLite/NumPy demo data.
_REPO_ROOT_ASSET_EXCLUDES = [
    "frontend",
    ".git",
    ".pytest_cache",
    "infra",
    "data",
    "*.md",
    "backend/.venv",
    "backend/tests",
    "backend/**/__pycache__",
    "backend/.pytest_cache",
]


class PolicyIntelligenceStack(Stack):
    """One stack, all resources — mirrors LOOP.md decision 3 ("one stack")."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        region = self.region

        corpus_bucket = self._build_corpus_bucket()
        conflicts_table, uploads_table = self._build_dynamodb_tables()
        user_pool, user_pool_client, user_pool_domain = self._build_cognito()
        collection, kb_role = self._build_opensearch_and_kb_role(corpus_bucket)
        vector_index_resource = self._build_vector_index_custom_resource(collection, region)
        knowledge_base, data_source = self._build_knowledge_base(
            corpus_bucket=corpus_bucket,
            collection=collection,
            kb_role=kb_role,
            vector_index_resource=vector_index_resource,
        )
        ingestion_lambda = self._build_ingestion_lambda(
            corpus_bucket=corpus_bucket,
            uploads_table=uploads_table,
            knowledge_base=knowledge_base,
            data_source=data_source,
        )
        # Only presigned uploads (uploads/{upload_id}/{filename}) flow through
        # the event-driven handler; bulk corpus prefixes are synced manually.
        corpus_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3_notifications.LambdaDestination(ingestion_lambda),
            s3.NotificationKeyFilter(prefix="uploads/"),
        )

        api_lambda = self._build_api_lambda(
            corpus_bucket=corpus_bucket,
            conflicts_table=conflicts_table,
            uploads_table=uploads_table,
            knowledge_base=knowledge_base,
            data_source=data_source,
            user_pool=user_pool,
            user_pool_client=user_pool_client,
        )
        http_api = self._build_http_api(api_lambda=api_lambda, user_pool=user_pool, user_pool_client=user_pool_client)
        agent_function_url = self._build_agent_function_url(api_lambda)

        self._build_outputs(
            region=region,
            corpus_bucket=corpus_bucket,
            conflicts_table=conflicts_table,
            uploads_table=uploads_table,
            knowledge_base=knowledge_base,
            data_source=data_source,
            user_pool=user_pool,
            user_pool_client=user_pool_client,
            user_pool_domain=user_pool_domain,
            http_api=http_api,
            agent_function_url=agent_function_url,
        )

    # ------------------------------------------------------------------
    # S3
    # ------------------------------------------------------------------
    def _build_corpus_bucket(self) -> s3.Bucket:
        bucket = s3.Bucket(
            self,
            "CorpusBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            # Prefixes handbook/, cba/, resolutions/, synthetic/ are a naming
            # convention enforced by the upload path (backend/app/uploads.py
            # AWS-mode branch), not separate S3 resources. See README.
            # The frontend PUTs presigned uploads straight from the browser,
            # so the bucket itself must answer the CORS preflight.
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT],
                    allowed_origins=self._allowed_origins(),
                    allowed_headers=["Content-Type"],
                    max_age=3600,
                )
            ],
        )
        return bucket

    # ------------------------------------------------------------------
    # DynamoDB
    # ------------------------------------------------------------------
    def _build_dynamodb_tables(self) -> tuple[dynamodb.Table, dynamodb.Table]:
        conflicts_table = dynamodb.Table(
            self,
            "ConflictLogTable",
            table_name="ConflictLog",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )
        conflicts_table.add_global_secondary_index(
            index_name="topic-index",
            partition_key=dynamodb.Attribute(name="topic", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="updated_at", type=dynamodb.AttributeType.STRING),
        )
        conflicts_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="updated_at", type=dynamodb.AttributeType.STRING),
        )

        uploads_table = dynamodb.Table(
            self,
            "UploadsTable",
            table_name="Uploads",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )
        uploads_table.add_global_secondary_index(
            index_name="status-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="filename", type=dynamodb.AttributeType.STRING),
        )

        return conflicts_table, uploads_table

    # ------------------------------------------------------------------
    # Cognito
    # ------------------------------------------------------------------
    def _build_cognito(self) -> tuple[cognito.UserPool, cognito.UserPoolClient, cognito.UserPoolDomain]:
        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="policy-intelligence-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=10,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
        )

        cognito.CfnUserPoolGroup(
            self,
            "MakersGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="makers",
            description="Policy makers / reviewers — resolution checker, conflict log.",
        )
        cognito.CfnUserPoolGroup(
            self,
            "EmployeesGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="employees",
            description="Employees — cited, conflict-aware policy Q&A chat.",
        )

        user_pool_client = user_pool.add_client(
            "SpaClient",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                # Cognito requires an EXACT match on redirect_uri. The
                # frontend's PKCE flow (frontend/src/auth/cognito.ts) sends
                # VITE_REDIRECT_URI, documented in frontend/.env.example as
                # http://localhost:5173/auth/callback — so /auth/callback is
                # registered for both localhost dev ports plus the deployed
                # frontend origin from the same `frontendOrigin` CDK context
                # value used for CORS (`cdk deploy -c frontendOrigin=...`).
                callback_urls=self._callback_urls(),
                logout_urls=self._logout_urls(),
            ),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
        )

        user_pool_domain = user_pool.add_domain(
            "HostedUiDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=f"policy-intel-{self.account}"),
        )

        return user_pool, user_pool_client, user_pool_domain

    # ------------------------------------------------------------------
    # OpenSearch Serverless (vector store) + Bedrock KB service role
    # ------------------------------------------------------------------
    def _build_opensearch_and_kb_role(self, corpus_bucket: s3.Bucket) -> tuple[aoss.CfnCollection, iam.Role]:
        collection_name = "policy-intelligence-vectors"

        kb_role = iam.Role(
            self,
            "KnowledgeBaseServiceRole",
            role_name=f"AmazonBedrockExecutionRoleForKB-{self.stack_name}",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/*"},
                },
            ),
        )
        kb_role.add_to_policy(
            iam.PolicyStatement(
                sid="TitanEmbeddingModel",
                actions=["bedrock:InvokeModel"],
                resources=[f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"],
            )
        )
        corpus_bucket.grant_read(kb_role)

        encryption_policy = aoss.CfnSecurityPolicy(
            self,
            "CollectionEncryptionPolicy",
            name="policy-intel-encryption",
            type="encryption",
            policy=self._to_json(
                {
                    "Rules": [{"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]}],
                    "AWSOwnedKey": True,
                }
            ),
        )

        network_policy = aoss.CfnSecurityPolicy(
            self,
            "CollectionNetworkPolicy",
            name="policy-intel-network",
            type="network",
            policy=self._to_json(
                [
                    {
                        "Rules": [
                            {"ResourceType": "collection", "Resource": [f"collection/{collection_name}"]},
                            {"ResourceType": "dashboard", "Resource": [f"collection/{collection_name}"]},
                        ],
                        # Public access keeps the demo simple; tighten to a VPC
                        # endpoint policy before any non-demo use. See README.
                        "AllowFromPublic": True,
                    }
                ]
            ),
        )

        collection = aoss.CfnCollection(
            self,
            "VectorCollection",
            name=collection_name,
            type="VECTORSEARCH",
            description="Vector store backing the Bedrock Knowledge Base over the policy corpus.",
        )
        collection.add_dependency(encryption_policy)
        collection.add_dependency(network_policy)

        # Data access policy: who may call the AOSS data plane (create/read the
        # index). Grants the KB role and the account root (for the vector-index
        # custom resource Lambda below, whose exact role ARN is added after
        # creation — see _build_vector_index_custom_resource).
        self._access_policy_principals: list[str] = [kb_role.role_arn]
        self._collection = collection
        self._collection_name = collection_name

        return collection, kb_role

    def _build_vector_index_custom_resource(self, collection: aoss.CfnCollection, region: str) -> cr.CustomResource:
        index_role = iam.Role(
            self,
            "VectorIndexProviderRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )
        index_role.add_to_policy(
            iam.PolicyStatement(
                sid="AossApiAccess",
                actions=["aoss:APIAccessAll"],
                resources=[collection.attr_arn],
            )
        )

        access_policy = aoss.CfnAccessPolicy(
            self,
            "CollectionDataAccessPolicy",
            name="policy-intel-data-access",
            type="data",
            policy=self._to_json(
                [
                    {
                        "Rules": [
                            {
                                "ResourceType": "index",
                                "Resource": [f"index/{self._collection_name}/*"],
                                "Permission": [
                                    "aoss:CreateIndex",
                                    "aoss:DeleteIndex",
                                    "aoss:UpdateIndex",
                                    "aoss:DescribeIndex",
                                    "aoss:ReadDocument",
                                    "aoss:WriteDocument",
                                ],
                            },
                            {
                                "ResourceType": "collection",
                                "Resource": [f"collection/{self._collection_name}"],
                                "Permission": ["aoss:CreateCollectionItems", "aoss:DescribeCollectionItems"],
                            },
                        ],
                        "Principal": self._access_policy_principals + [index_role.role_arn],
                    }
                ]
            ),
        )
        access_policy.add_dependency(collection)

        index_provider_fn = _lambda.Function(
            self,
            "VectorIndexProviderFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.on_event",
            code=_lambda.Code.from_asset(str(INFRA_ROOT / "lambda_src" / "vector_index_provider")),
            role=index_role,
            timeout=Duration.minutes(2),
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        provider = cr.Provider(
            self,
            "VectorIndexProvider",
            on_event_handler=index_provider_fn,
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        resource = cr.CustomResource(
            self,
            "VectorIndexResource",
            service_token=provider.service_token,
            properties={
                "CollectionEndpoint": collection.attr_collection_endpoint,
                "Region": region,
                "IndexName": VECTOR_INDEX_NAME,
                "VectorField": VECTOR_FIELD_NAME,
                "TextField": TEXT_FIELD_NAME,
                "MetadataField": METADATA_FIELD_NAME,
                "Dimension": TITAN_EMBED_V2_DIMENSION,
            },
        )
        resource.node.add_dependency(access_policy)
        resource.node.add_dependency(collection)

        return resource

    # ------------------------------------------------------------------
    # Bedrock Knowledge Base + S3 data source
    # ------------------------------------------------------------------
    def _build_knowledge_base(
        self,
        *,
        corpus_bucket: s3.Bucket,
        collection: aoss.CfnCollection,
        kb_role: iam.Role,
        vector_index_resource: cr.CustomResource,
    ) -> tuple[bedrock.CfnKnowledgeBase, bedrock.CfnDataSource]:
        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name="policy-intelligence-kb",
            description="Handbook / CBA / resolutions / synthetic corpus for the Policy Intelligence Assistant.",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            dimensions=TITAN_EMBED_V2_DIMENSION,
                        ),
                    ),
                    embedding_model_arn=f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0",
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=collection.attr_arn,
                    vector_index_name=VECTOR_INDEX_NAME,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        vector_field=VECTOR_FIELD_NAME,
                        text_field=TEXT_FIELD_NAME,
                        metadata_field=METADATA_FIELD_NAME,
                    ),
                ),
            ),
        )
        knowledge_base.node.add_dependency(vector_index_resource)

        data_source = bedrock.CfnDataSource(
            self,
            "CorpusDataSource",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            name="policy-corpus-s3",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=corpus_bucket.bucket_arn,
                    inclusion_prefixes=CORPUS_PREFIXES,
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=CHUNK_MAX_TOKENS,
                        overlap_percentage=CHUNK_OVERLAP_PERCENTAGE,
                    ),
                ),
            ),
        )

        return knowledge_base, data_source

    # ------------------------------------------------------------------
    # Ingestion Lambda (S3 ObjectCreated -> KB sync)
    # ------------------------------------------------------------------
    def _build_ingestion_lambda(
        self,
        *,
        corpus_bucket: s3.Bucket,
        uploads_table: dynamodb.Table,
        knowledge_base: bedrock.CfnKnowledgeBase,
        data_source: bedrock.CfnDataSource,
    ) -> _lambda.Function:
        # backend/lambda_handlers/ingestion.py uses an ABSOLUTE import
        # (`from backend.app.config import get_settings`), which means
        # "backend" must be a top-level importable package inside the
        # deployment zip — so the asset root is the repo root, not
        # backend/lambda_handlers/ (excludes keep frontend/, .git, and local
        # demo data out of the container input).
        #
        # Bundling: ingestion.py's import chain (config -> stores -> models)
        # only reaches pydantic beyond the stdlib; boto3 is imported lazily
        # and ships in the Lambda runtime. Installing just pydantic (with the
        # same version pin as backend/requirements.txt) keeps this zip tiny
        # instead of dragging in fastapi/numpy/strands.
        fn = _lambda.Function(
            self,
            "IngestionFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.lambda_handlers.ingestion.handler",
            code=_lambda.Code.from_asset(
                str(REPO_ROOT),
                exclude=_REPO_ROOT_ASSET_EXCLUDES,
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install 'pydantic>=2.8,<3' -t /asset-output"
                        " && cp -au . /asset-output",
                    ],
                ),
            ),
            timeout=Duration.minutes(5),
            memory_size=256,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                # Names match backend/app/config.py's get_settings() exactly —
                # ingestion.py looks up the data source id itself at runtime
                # via list_data_sources(), so no BEDROCK_DATA_SOURCE_ID env is
                # read (BedrockDataSourceId is still a stack output, for the
                # manual `start-ingestion-job` CLI command in README).
                "BEDROCK_KB_ID": knowledge_base.attr_knowledge_base_id,
                "DDB_UPLOADS_TABLE": uploads_table.table_name,
                # AWS_REGION is a reserved Lambda env var name (set
                # automatically by the runtime) — do not set it explicitly,
                # CDK/CloudFormation rejects it.
            },
        )
        uploads_table.grant_read_write_data(fn)
        corpus_bucket.grant_read(fn)
        # The handler deletes oversized uploads/ objects so they cannot ride
        # along with a later Knowledge Base sync.
        corpus_bucket.grant_delete(fn, "uploads/*")
        fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="KbIngestion",
                # ingestion.py calls list_data_sources on every event,
                # start_ingestion_job, and (on the concurrent-job reuse path)
                # list_ingestion_jobs; get_ingestion_job kept for parity with
                # status checks. All four scope to the knowledge-base ARN per
                # the Bedrock service authorization reference / AWS's own KB
                # management example policy.
                actions=[
                    "bedrock:StartIngestionJob",
                    "bedrock:GetIngestionJob",
                    "bedrock:ListIngestionJobs",
                    "bedrock:ListDataSources",
                ],
                resources=[knowledge_base.attr_knowledge_base_arn],
            )
        )
        return fn

    # ------------------------------------------------------------------
    # API Lambda (FastAPI via Mangum) + HTTP API
    # ------------------------------------------------------------------
    def _build_api_lambda(
        self,
        *,
        corpus_bucket: s3.Bucket,
        conflicts_table: dynamodb.Table,
        uploads_table: dynamodb.Table,
        knowledge_base: bedrock.CfnKnowledgeBase,
        data_source: bedrock.CfnDataSource,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
    ) -> _lambda.Function:
        # backend/app/lambda_entry.py uses a RELATIVE import (`from .main
        # import app`), unlike ingestion.py — so its asset root is
        # backend/ itself (making "app" the top-level package in the zip),
        # and the handler string is "app.lambda_entry.handler", not
        # "backend.app.lambda_entry.handler".
        #
        # Bundling: pip-installs backend/requirements.txt into the asset
        # inside the runtime's build container (Docker required at synth
        # time). Dev/server-only deps (pytest, uvicorn, httpx) are stripped
        # first — they're not needed in Lambda and just bloat the zip toward
        # the 250 MB unzipped limit. boto3 ships in the runtime and is left
        # in requirements harmlessly (pip just installs its pinned copy).
        api_asset_path = REPO_ROOT / "backend"

        fn = _lambda.Function(
            self,
            "ApiFn",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="app.lambda_entry.handler",
            code=_lambda.Code.from_asset(
                str(api_asset_path),
                exclude=[".venv", "tests", "**/__pycache__", ".pytest_cache", "lambda_handlers"],
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "sed '/^pytest/d;/^uvicorn/d;/^httpx/d' requirements.txt > /tmp/requirements-lambda.txt"
                        " && pip install -r /tmp/requirements-lambda.txt -t /asset-output"
                        " && cp -au . /asset-output",
                    ],
                ),
            ),
            # 120s matches the frontend's AGENT_REQUEST_TIMEOUT_MS. Requests
            # routed through the HTTP API are still cut by the gateway's own
            # ~29s integration cap (fine — those routes are fast), but the two
            # long-running agent endpoints are served via the Lambda Function
            # URL below (no 29s cap), so the function itself must be allowed to
            # run past 29s. Function URLs support up to the 15-min Lambda max.
            timeout=Duration.seconds(120),
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                # Names match backend/app/config.py's get_settings() exactly.
                # AWS_REGION is a reserved Lambda env var (set automatically
                # by the runtime) — do not set it explicitly.
                "BEDROCK_KB_ID": knowledge_base.attr_knowledge_base_id,
                "DDB_CONFLICTS_TABLE": conflicts_table.table_name,
                "DDB_UPLOADS_TABLE": uploads_table.table_name,
                "CORPUS_BUCKET": corpus_bucket.bucket_name,
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": user_pool_client.user_pool_client_id,
            },
        )
        conflicts_table.grant_read_write_data(fn)
        uploads_table.grant_read_write_data(fn)
        corpus_bucket.grant_read_write(fn)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                sid="BedrockRuntimeAccess",
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                ],
                resources=["*"],  # Claude/Titan foundation-model ARNs vary by version; scope down post-demo.
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # retrieval.py calls bedrock-agent-runtime retrieve;
                # RetrieveAndGenerate was dropped — the backend never calls
                # it, and per AWS docs that action only works with
                # Resource "*" (a KB-ARN-scoped grant would be ineffective).
                sid="BedrockKbRetrieve",
                actions=["bedrock:Retrieve"],
                resources=[knowledge_base.attr_knowledge_base_arn],
            )
        )
        fn.add_to_role_policy(
            iam.PolicyStatement(
                # uploads.py's GET /api/uploads/{id} polling calls
                # list_data_sources + get_ingestion_job on bedrock-agent.
                # Both scope to the knowledge-base ARN.
                sid="BedrockKbIngestionStatus",
                actions=["bedrock:ListDataSources", "bedrock:GetIngestionJob"],
                resources=[knowledge_base.attr_knowledge_base_arn],
            )
        )
        return fn

    def _build_http_api(
        self,
        *,
        api_lambda: _lambda.Function,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
    ) -> apigwv2.HttpApi:
        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="policy-intelligence-api",
            # API Gateway HTTP API treats each allowed origin as a LITERAL
            # string — "https://*.amplifyapp.com" would never match, so the
            # deployed frontend's exact origin must be passed at deploy time
            # via CDK context: `cdk deploy -c frontendOrigin=https://...`.
            # Localhost dev origins are always included as the default.
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=self._allowed_origins(),
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["Authorization", "Content-Type"],
                allow_credentials=True,
            ),
        )

        authorizer = apigwv2_authorizers.HttpUserPoolAuthorizer(
            "CognitoAuthorizer",
            user_pool,
            user_pool_clients=[user_pool_client],
        )

        integration = apigwv2_integrations.HttpLambdaIntegration("ApiIntegration", api_lambda)

        # /api/health stays open (no auth) so uptime checks / the demo backup
        # plan can probe the stack without a token; everything else requires
        # a valid Cognito JWT — role comes from the token's cognito:groups
        # claim per implementation2.md Phase B.
        http_api.add_routes(
            path="/api/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=integration,
        )
        http_api.add_routes(
            path="/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=integration,
            authorizer=authorizer,
        )

        return http_api

    # ------------------------------------------------------------------
    # Lambda Function URL (escapes API Gateway's 29s cap for agent endpoints)
    # ------------------------------------------------------------------
    def _build_agent_function_url(self, api_lambda: _lambda.Function) -> _lambda.FunctionUrl:
        """A Function URL on the SAME API Lambda for the two long-running agent
        endpoints (POST /api/chat, POST /api/check-resolution).

        API Gateway HTTP API has a hard ~29s integration timeout; the retrieval
        + multi-agent Bedrock pipeline can exceed it. Function URLs allow up to
        the 15-min Lambda max (the function's own timeout is 120s here), so the
        frontend routes just those two POSTs here via VITE_AGENT_BASE_URL while
        every other route keeps flowing through the gateway + JWT authorizer.

        auth_type is NONE because Function URLs cannot use the Cognito JWT
        authorizer; the backend validates the Cognito token itself in-app
        (backend/app/auth.py require_authenticated / require_reviewer), so these
        endpoints stay authenticated in AWS mode. CORS is scoped to the same
        origins as the HTTP API so the browser can call it cross-origin.
        """
        return api_lambda.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
            cors=_lambda.FunctionUrlCorsOptions(
                allowed_origins=self._allowed_origins(),
                allowed_methods=[_lambda.HttpMethod.POST],
                allowed_headers=["Authorization", "Content-Type"],
                allow_credentials=True,
                max_age=Duration.hours(1),
            ),
        )

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------
    def _build_outputs(
        self,
        *,
        region: str,
        corpus_bucket: s3.Bucket,
        conflicts_table: dynamodb.Table,
        uploads_table: dynamodb.Table,
        knowledge_base: bedrock.CfnKnowledgeBase,
        data_source: bedrock.CfnDataSource,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
        user_pool_domain: cognito.UserPoolDomain,
        http_api: apigwv2.HttpApi,
        agent_function_url: _lambda.FunctionUrl,
    ) -> None:
        hosted_ui_url = (
            f"https://{user_pool_domain.domain_name}.auth.{region}.amazoncognito.com"
        )
        CfnOutput(self, "AwsRegion", value=region)
        CfnOutput(self, "CorpusBucketName", value=corpus_bucket.bucket_name)
        CfnOutput(self, "BedrockKbId", value=knowledge_base.attr_knowledge_base_id)
        CfnOutput(self, "BedrockDataSourceId", value=data_source.attr_data_source_id)
        CfnOutput(self, "DdbConflictsTable", value=conflicts_table.table_name)
        CfnOutput(self, "DdbUploadsTable", value=uploads_table.table_name)
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "CognitoHostedUiUrl", value=hosted_ui_url)
        CfnOutput(self, "ApiUrl", value=http_api.api_endpoint)
        # Feed into the frontend's VITE_AGENT_BASE_URL so chat / check-resolution
        # bypass the HTTP API's 29s cap. Trailing slash trimmed by the frontend.
        CfnOutput(self, "AgentFunctionUrl", value=agent_function_url.url)

    # ------------------------------------------------------------------
    def _allowed_origins(self) -> list[str]:
        """CORS origins: localhost dev servers plus an optional deployed
        frontend origin from CDK context (`-c frontendOrigin=https://...`).

        HTTP API CORS origins are literal strings (no wildcards below the
        scheme), so the real Amplify/hosting URL has to be supplied once it
        is known — see infra/README.md "CORS and Cognito redirects: pass the frontend origin at deploy time".
        """
        origins = ["http://localhost:5173", "http://localhost:5174"]
        frontend_origin = self.node.try_get_context("frontendOrigin")
        if isinstance(frontend_origin, str) and frontend_origin:
            origins.append(frontend_origin.rstrip("/"))
        return origins

    def _callback_urls(self) -> list[str]:
        """Cognito OAuth callback URLs — exact-match against the frontend's
        redirect_uri, which is `<origin>/auth/callback` (see
        frontend/.env.example VITE_REDIRECT_URI and
        frontend/src/auth/cognito.ts). Derived from the same origins as CORS
        so `-c frontendOrigin=...` fixes both in one flag.
        """
        return [f"{origin}/auth/callback" for origin in self._allowed_origins()]

    def _logout_urls(self) -> list[str]:
        """Cognito allowed sign-out URLs — the site roots (the SPA lands on
        its login page after logout, not the callback route)."""
        return [f"{origin}/" for origin in self._allowed_origins()]

    @staticmethod
    def _to_json(value: object) -> str:
        import json

        return json.dumps(value)
