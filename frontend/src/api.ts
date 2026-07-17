import {
  conversationAnswers,
  conflicts,
  draftResolution,
  libraryItems,
  openConflicts,
  recentReviews,
  reviewAnalysis,
  conflictDetails,
  sources,
  topicDetails,
  topics,
  type Answer,
  type AgentName,
  type AgentTraceStatus,
  type AgentTraceStep,
  type Conflict,
  type ConflictDetail,
  type DraftResolution,
  type KnowledgeSource,
  type LibraryItem,
  type OpenConflict,
  type RecentReview,
  type ReviewAnalysis,
  type ReviewSubmission,
  type Role,
  type Topic,
  type TopicDetail,
} from "./data/mock";
import { CognitoSessionExpiredError, getCognitoAuthorizationToken } from "./auth/cognito";

const reviewSubmissionStorageKey = "policy-intelligence.review-submission";
const conflictStateStorageKey = "policy-intelligence.conflict-state-v2";
const manualConflictsStorageKey = "policy-intelligence.manual-conflicts-v1";
const uploadedSourcesStorageKey = "policy-intelligence.uploaded-sources-v1";
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const hasConfiguredApi = Boolean(import.meta.env.VITE_API_BASE_URL);
// The two long-running agent endpoints (chat, check-resolution) run retrieval
// plus a multi-agent Bedrock pipeline that can exceed API Gateway HTTP API's
// hard 29s integration cap. In AWS mode they are served by a Lambda Function
// URL (up to 15 min) supplied here; unset, they fall back to the normal API
// base so local/dev behavior is byte-for-byte unchanged.
const agentBaseUrl = (import.meta.env.VITE_AGENT_BASE_URL ?? "").replace(/\/$/, "") || apiBaseUrl;

interface BackendCitation {
  id: number;
  source: string;
  section: string;
  excerpt: string;
  canonical_url?: string;
  section_url?: string;
}
interface BackendChatResponse {
  answer_id: string;
  answer: string;
  citations: BackendCitation[];
  conflict: { detected: boolean; guidance: string } | null;
  mode: "local-index" | "calibrated-static" | "agent-grounded";
}
interface BackendFeedbackResponse { feedback_id: string; }
interface BackendRecurringQuestion {
  question_id: string;
  question_text: string;
  topic: string;
  ask_count: number;
}
interface BackendResolutionFinding { source: string; section: string; description: string; }
interface BackendResolutionResponse {
  overlaps: BackendResolutionFinding[];
  duplicates: BackendResolutionFinding[];
  conflicts: BackendResolutionFinding[];
  recommendation: string;
  mode: "local-index" | "calibrated-static" | "agent-grounded";
  agent_trace: BackendAgentTrace[];
}
interface BackendAgentTrace {
  agent: AgentName;
  label: string;
  status: AgentTraceStatus;
  detail?: string;
  citations?: BackendCitation[] | null;
}
interface BackendConflict {
  id: string | number;
  source_a: string;
  source_b: string;
  topic: string;
  description: string;
  status: Conflict["status"];
  created_at: string;
}
interface BackendUploadResponse { filename: string; status: string; chunks_added: number; }
interface BackendPresignedUploadResponse {
  upload_id: string;
  upload_url: string;
  headers?: Record<string, string>;
}
interface BackendIngestionResponse { upload_id: string; status: IngestionStatus; chunks_added?: number; error?: string; }
interface BackendTopicSummary { name: string; count: number; }
interface BackendTopicDetail { name: string; chunks: Array<{ source: string; section: string; excerpt: string }>; }
interface BackendRegistrySource {
  id: string;
  title: string;
  source_type: RegistrySource["sourceType"];
  status: RegistrySource["status"];
  canonical_url: string;
  owner: string;
  section_index: Record<string, string>;
  edition_year: number | null;
  is_current: boolean;
  passages: number;
  updated_at: string;
}
interface BackendPermission {
  user_email: string;
  source_type: Permission["sourceType"];
  can_add: boolean;
  can_edit: boolean;
}
interface BackendDraftRevision {
  draft_id: string;
  version: number;
  revised_text: string;
  rationale: string;
  title: string;
  owner: string;
  status: DraftStatus;
  overlaps: BackendResolutionFinding[];
  duplicates: BackendResolutionFinding[];
  conflicts: BackendResolutionFinding[];
  recommendation: string;
  agent_trace: BackendAgentTrace[];
}
interface BackendDraftVersion {
  draft_id: string;
  version: number;
  title: string;
  owner: string;
  status: DraftStatus;
  text: string;
  source_text: string;
  instruction: string;
  suggestion: string;
  restored_from_version: number | null;
  created_at: string;
}
interface BackendDraftSummary {
  draft_id: string;
  title: string;
  owner: string;
  status: DraftStatus;
  latest_version: number;
  latest_text: string;
  updated_at: string;
}
interface BackendDraftComparison {
  draft_id: string;
  from_version: number;
  to_version: number;
  from_text: string;
  to_text: string;
  unified_diff: string;
}

// Bedrock-backed endpoints (chat, resolution checks) run retrieval plus a
// multi-agent LLM pipeline server-side and routinely exceed a few seconds.
const DEFAULT_REQUEST_TIMEOUT_MS = 15_000;
const AGENT_REQUEST_TIMEOUT_MS = 120_000;

const DEMO_EMAIL_STORAGE_KEY = "policy-intelligence.user-email";

export const demoEmailForRole = (role: Role): string =>
  role === "reviewer" ? "reviewer@campus.edu" : "employee@campus.edu";

/** Keep the demo identity in step with the selected role.
 *
 * The backend resolves the demo role from X-User-Email in preference to
 * X-Role, so a role change that left the stored email behind would send a
 * reviewer view with an employee identity and 403 every reviewer-only route.
 */
export function setDemoIdentity(role: Role): void {
  if (import.meta.env.VITE_USE_COGNITO === "true") return;
  window.localStorage.setItem(DEMO_EMAIL_STORAGE_KEY, demoEmailForRole(role));
}

const backendRequest = async <T>(path: string, init?: RequestInit, timeoutMs: number = DEFAULT_REQUEST_TIMEOUT_MS, baseUrl: string = apiBaseUrl): Promise<T | null> => {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const authorizationToken = await getCognitoAuthorizationToken();
    const headers = new Headers(init?.headers);
    if (authorizationToken !== null) headers.set("Authorization", `Bearer ${authorizationToken}`);
    const demoEmail = window.localStorage.getItem(DEMO_EMAIL_STORAGE_KEY);
    if (authorizationToken === null && demoEmail !== null) headers.set("X-User-Email", demoEmail);
    const response = await fetch(`${baseUrl}${path}`, { ...init, headers, signal: controller.signal });
    if (!response.ok) {
      // A backend/gateway error (500/502/504) is otherwise indistinguishable
      // from a genuine "no data" and silently becomes a mock answer downstream.
      // Log the status so a live failure is diagnosable in devtools.
      console.error(`[api] ${init?.method ?? "GET"} ${path} -> HTTP ${response.status} ${response.statusText}; falling back.`);
      return null;
    }
    return await response.json() as T;
  } catch (error) {
    if (error instanceof CognitoSessionExpiredError) throw error;
    // Distinguish a client-side timeout (AbortController fired) from a real
    // network error. Both currently collapse to a silent mock fallback, which
    // hides the true cause — so name it explicitly.
    if (timedOut) {
      console.error(`[api] ${init?.method ?? "GET"} ${path} timed out after ${timeoutMs}ms; falling back.`);
    } else {
      console.error(`[api] ${init?.method ?? "GET"} ${path} failed (network/abort):`, error);
    }
    return null;
  } finally {
    window.clearTimeout(timeout);
  }
};

interface PersistedConflictState {
  status: Conflict["status"];
  note?: string;
  detected?: string;
}

type PersistedConflictMap = Record<string, PersistedConflictState>;

const readStoredArray = <T>(key: string): T[] => {
  try {
    const stored = window.localStorage.getItem(key);
    if (stored === null) return [];
    const parsed: unknown = JSON.parse(stored);
    return Array.isArray(parsed) ? parsed as T[] : [];
  } catch {
    return [];
  }
};

const writeStoredArray = <T>(key: string, values: T[]): void => {
  try { window.localStorage.setItem(key, JSON.stringify(values)); } catch { /* Keep the in-memory demo usable. */ }
};

export interface LoginResult {
  role: Role;
  name: string;
}

export type { AgentName, AgentTraceStatus, AgentTraceStep };
export type IngestionStatus = "pending" | "ingesting" | "ready" | "failed";

export interface PresignedUpload {
  uploadId: string;
  uploadUrl: string;
  headers: Record<string, string>;
  mock: boolean;
}

export interface IngestionUpdate {
  uploadId: string;
  status: IngestionStatus;
  chunksAdded?: number;
  error?: string;
}

export interface SourceUpload {
  source: KnowledgeSource;
  uploadId: string;
}

const delay = async (milliseconds = 80): Promise<void> => {
  await new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
};

export async function login(role: Role): Promise<LoginResult> {
  if (import.meta.env.VITE_USE_COGNITO === "true") {
    throw new Error("Demo login is unavailable while Cognito sign-in is enabled.");
  }
  const email = demoEmailForRole(role);
  const result = await backendRequest<LoginResult>("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: "demo123" }),
  });
  if (result !== null) {
    setDemoIdentity(role);
    return result;
  }
  await delay();
  setDemoIdentity(role);
  return { role, name: role === "reviewer" ? "Jennifer D." : "Alex B." };
}

const normalizeQuestion = (text: string): string => text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

const localAnswerId = (question: string): string => {
  let hash = 2166136261;
  for (let index = 0; index < question.length; index += 1) {
    hash = Math.imul(hash ^ question.charCodeAt(index), 16777619);
  }
  return `local-${(hash >>> 0).toString(36)}`;
};

const questionRoutes: ReadonlyArray<{ id: keyof typeof conversationAnswers; terms: string[] }> = [
  { id: "ferp-rtp-service", terms: ["ferp faculty member serve", "ferp rtp committee", "ferp committee service"] },
  { id: "ferp-additional-employment", terms: ["additional employment", "summer employment", "other employment during ferp", "accept summer"] },
  { id: "ferp-work-limits", terms: ["how much can i work", "work each year", "work limits", "960 hour", "90 workdays", "ferp employment limits"] },
  { id: "ferp-notice", terms: ["notify the president", "enter ferp", "six month notice", "february 15"] },
  { id: "ferp-180-day-wait", terms: ["180 day", "waiting period"] },
  { id: "wpaf-review-scope", terms: ["promotion wpaf", "developmental or cumulative", "review scope"] },
  { id: "wpaf-evidence", terms: ["evidence belongs", "wpaf evidence", "personnel action file"] },
  { id: "temporary-faculty-evaluation", terms: ["temporary faculty evaluated", "temporary faculty evaluation", "periodic evaluation"] },
  { id: "office-hours-six-wtu", terms: ["office hours", "6 wtu", "six wtu", "faculty office hours"] },
  { id: "emeriti-status", terms: ["emeriti", "emeritus"] },
  { id: "rtp-rebuttal-window", terms: ["rebut an rtp", "rebuttal window", "seven day response", "promotion review procedures"] },
  { id: "rtp-committee", terms: ["unit rtp committee", "who may serve", "rtp committee eligibility"] },
  { id: "service-credit", terms: ["service credit", "prior service", "tenure clock", "unit 3 cba article 13"] },
  { id: "workload-overview", terms: ["workload", "faculty workload", "assigned responsibilities"] },
  { id: "accessibility-overview", terms: ["accessibility", "instructional technology", "accessible technology", "accessibility exception", "equally effective alternative", "instructional materials accessibility"] },
  { id: "gecco-overview", terms: ["gecco", "general education curriculum committee"] },
];

const cloneAnswer = (answer: Answer, question = answer.question): Answer => ({
  ...answer,
  answerId: answer.answerId ?? localAnswerId(question),
  mode: answer.mode ?? "calibrated-static",
  question,
  paragraphs: [...answer.paragraphs],
  citations: answer.citations.map((citation) => ({ ...citation })),
});

const readConflictState = (): PersistedConflictMap => {
  try {
    const stored = window.localStorage.getItem(conflictStateStorageKey);
    if (stored === null) return {};
    const parsed: unknown = JSON.parse(stored);
    return typeof parsed === "object" && parsed !== null ? parsed as PersistedConflictMap : {};
  } catch { return {}; }
};

const writeConflictState = (state: PersistedConflictMap): void => {
  try { window.localStorage.setItem(conflictStateStorageKey, JSON.stringify(state)); } catch { /* Demo remains usable if storage is unavailable. */ }
};

export async function askQuestion(text: string, role: Role = "reviewer"): Promise<Answer> {
  const question = text.trim();
  if (!question) throw new Error("Enter a policy question.");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (import.meta.env.VITE_USE_COGNITO !== "true") headers["X-Role"] = role;
  const backend = await backendRequest<BackendChatResponse>("/api/chat", {
    method: "POST",
    headers,
    body: JSON.stringify({ question }),
  }, AGENT_REQUEST_TIMEOUT_MS, agentBaseUrl);
  if (backend !== null) {
    const paragraphs = backend.answer.split(/\n\s*\n/).filter(Boolean);
    const heading = paragraphs[0]?.split(/[.!?]\s/)[0] ?? "Grounded policy response";
    // The heading is the first sentence of the answer; strip that sentence from
    // the body so it isn't shown twice (once as the headline, once as body text).
    if (paragraphs[0] !== undefined) {
      const remainder = paragraphs[0].slice(heading.length).replace(/^[.!?]\s*/, "").trim();
      if (remainder) paragraphs[0] = remainder;
      else paragraphs.shift();
    }
    return {
      answerId: backend.answer_id,
      mode: backend.mode,
      question,
      heading,
      paragraphs,
      citations: backend.citations.map((citation) => ({
        id: citation.id,
        title: citation.source,
        section: citation.section,
        canonicalUrl: citation.canonical_url,
        sectionUrl: citation.section_url,
      })),
      ...(backend.conflict?.detected ? { conflictBanner: `Policy conflict — ${backend.conflict.guidance}` } : {}),
    };
  }
  // When a live backend is configured, /api/chat never legitimately returns
  // "nothing" — it answers or errors. So a null here means the request failed
  // (timeout / 5xx / network, already logged in backendRequest). Surfacing the
  // mock "outside the calibrated demo" answer here would silently mask that
  // failure as if the question were simply unsupported. Report it instead.
  if (hasConfiguredApi) {
    return {
      answerId: localAnswerId(question),
      mode: "agent-grounded",
      question,
      heading: "The assistant could not complete this request",
      paragraphs: [
        "The policy assistant did not return an answer in time. This is a backend or connection issue, not a limit on the question itself. Please try again; if it persists, check the server logs (a timeout or Bedrock error will be recorded there).",
      ],
      citations: [],
    };
  }
  await delay();
  const normalized = normalizeQuestion(question);
  const exactMatch = Object.entries(conversationAnswers).find(([, answer]) => normalizeQuestion(answer.question) === normalized);
  const route = exactMatch?.[0] ?? questionRoutes.find((candidate) => candidate.terms.some((term) => normalized.includes(term)))?.id;
  if (route !== undefined) {
    return cloneAnswer(conversationAnswers[route], question);
  }
  return {
    answerId: localAnswerId(question),
    mode: "calibrated-static",
    question,
    heading: "This question is outside the calibrated static demo",
    paragraphs: [
      "No policy conclusion was generated because this frontend demo only has reviewed static answers for selected FERP, RTP, WPAF, office-hours, Emeriti, and service-credit questions. Try one of the suggested questions or browse a supplied topic. A production deployment would retrieve current source passages before answering.",
    ],
    citations: [],
  };
}

export type FeedbackRating = "helpful" | "not_helpful";

export interface FeedbackSubmission {
  answerId: string;
  question: string;
  rating: FeedbackRating;
  role?: Role;
  citationsUsed?: string[];
  provider?: Answer["mode"];
}

export interface FeedbackSubmissionResult {
  submitted: boolean;
  feedbackId?: string;
}

export interface RecurringQuestion {
  questionId: string;
  questionText: string;
  topic: string;
  askCount: number;
}

const fallbackRecurringQuestions: ReadonlyArray<RecurringQuestion> = [
  { questionId: "demo-service-credit", questionText: "Does service credit count toward the tenure clock?", topic: "general", askCount: 0 },
  { questionId: "demo-rtp", questionText: "What is the RTP process?", topic: "general", askCount: 0 },
  { questionId: "demo-gecco", questionText: "What is the GECCo Committee?", topic: "general", askCount: 0 },
  { questionId: "demo-accessibility", questionText: "Where can I find accessibility policy?", topic: "general", askCount: 0 },
];

export async function getRecurringQuestions(topic?: string, limit = 4): Promise<RecurringQuestion[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (topic) params.set("topic", topic);
  const result = await backendRequest<BackendRecurringQuestion[]>(`/api/recurring-questions?${params.toString()}`);
  if (result !== null && result.length > 0) {
    return result.map((question) => ({
      questionId: question.question_id,
      questionText: question.question_text,
      topic: question.topic,
      askCount: question.ask_count,
    }));
  }
  return fallbackRecurringQuestions.slice(0, limit).map((question) => ({ ...question }));
}

export async function submitFeedback(input: FeedbackSubmission): Promise<FeedbackSubmissionResult> {
  const result = await backendRequest<BackendFeedbackResponse>("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      answer_id: input.answerId,
      question: input.question,
      rating: input.rating,
      role: input.role,
      citations_used: input.citationsUsed ?? [],
      provider: input.provider,
    }),
  });
  return result === null ? { submitted: false } : { submitted: true, feedbackId: result.feedback_id };
}

export async function getConversation(conversationId: string): Promise<Answer> {
  await delay();
  const answer = conversationAnswers[conversationId];
  if (answer === undefined) throw new Error(`Conversation not found: ${conversationId}`);
  return cloneAnswer(answer);
}

export function saveReviewSubmission(submission: ReviewSubmission): void {
  window.sessionStorage.setItem(reviewSubmissionStorageKey, JSON.stringify(submission));
}

export function clearReviewSubmission(): void {
  window.sessionStorage.removeItem(reviewSubmissionStorageKey);
}

export function getReviewSubmission(): ReviewSubmission | null {
  const stored = window.sessionStorage.getItem(reviewSubmissionStorageKey);
  if (stored === null) return null;

  try {
    const value: unknown = JSON.parse(stored);
    if (typeof value !== "object" || value === null || !("title" in value) || !("text" in value)) return null;
    const { title, text } = value;
    const fileName = "fileName" in value ? value.fileName : undefined;
    const draftId = "draftId" in value ? value.draftId : undefined;
    if (typeof title !== "string" || typeof text !== "string" || (fileName !== undefined && typeof fileName !== "string") || (draftId !== undefined && typeof draftId !== "string")) return null;
    return { title, text, ...(fileName === undefined ? {} : { fileName }), ...(draftId === undefined ? {} : { draftId }) };
  } catch {
    return null;
  }
}

export async function getLibrary(): Promise<LibraryItem[]> {
  await delay();
  return libraryItems.map((item) => ({ ...item }));
}

export async function getTopics(): Promise<Topic[]> {
  const backend = await backendRequest<BackendTopicSummary[]>("/api/topics");
  if (backend !== null && backend.length > 0) {
    return backend.map((topic) => {
      const slug = topic.name.split("&").join("").trim().replace(/\s+/g, "-");
      const fallback = topics.find((item) => item.slug === slug || item.name.toLowerCase() === topic.name);
      return { slug, name: fallback?.name ?? topic.name.replace(/\b\w/g, (letter) => letter.toUpperCase()), count: topic.count, description: fallback?.description ?? "Browse indexed passages from supplied policy sources." };
    });
  }
  await delay();
  return topics.map((topic) => ({ ...topic }));
}

export async function getTopic(slug: string): Promise<TopicDetail> {
  const backend = await backendRequest<BackendTopicDetail>(`/api/topics/${encodeURIComponent(slug)}`);
  if (backend !== null) {
    const fallback = topicDetails[slug] ?? topicDetails["tenure-promotion"];
    const topic = { ...fallback.topic, slug, name: backend.name.replace(/\b\w/g, (letter) => letter.toUpperCase()), count: backend.chunks.length };
    return {
      topic,
      sourceFilters: ["All sources", ...new Set(backend.chunks.map((chunk) => chunk.source))],
      commonQuestions: [...fallback.commonQuestions],
      policies: backend.chunks.map((chunk) => ({ title: chunk.excerpt.slice(0, 95), source: chunk.source, section: chunk.section, updated: "Indexed locally" })),
    };
  }
  await delay();
  const detail = topicDetails[slug] ?? topicDetails["tenure-promotion"];
  return {
    ...detail,
    topic: { ...detail.topic },
    sourceFilters: [...detail.sourceFilters],
    commonQuestions: [...detail.commonQuestions],
    policies: detail.policies.map((policy) => ({ ...policy })),
  };
}

export async function getRecentReviews(): Promise<RecentReview[]> {
  await delay();
  return recentReviews.map((review) => ({ ...review }));
}

export async function getOpenConflicts(): Promise<OpenConflict[]> {
  await delay();
  const currentConflicts = mergePersistedConflicts();
  return openConflicts
    .filter((conflict) => currentConflicts.find((item) => item.slug === conflict.slug)?.status !== "Resolved")
    .map((conflict) => ({ ...conflict }));
}

const mergePersistedConflicts = (): Conflict[] => {
  const state = readConflictState();
  const manual = readStoredArray<Conflict>(manualConflictsStorageKey);
  return [...manual, ...conflicts.filter((conflict) => !manual.some((item) => item.slug === conflict.slug))].map((conflict) => {
    const persisted = state[conflict.slug];
    return persisted === undefined ? { ...conflict } : { ...conflict, status: persisted.status, detected: persisted.detected ?? conflict.detected };
  });
};

export async function getConflicts(): Promise<Conflict[]> {
  const backend = await backendRequest<BackendConflict[]>("/api/conflicts");
  if (backend !== null) {
    const apiConflicts: Conflict[] = backend.map((conflict) => ({
      slug: `local-api-${conflict.id}`,
      topic: conflict.topic,
      sources: `${conflict.source_a} ↔ ${conflict.source_b}`,
      owner: "Faculty Affairs",
      status: conflict.status,
      detected: new Date(conflict.created_at).toLocaleDateString(),
    }));
    return [...apiConflicts, ...mergePersistedConflicts().filter((item) => !apiConflicts.some((apiItem) => apiItem.topic === item.topic && apiItem.sources === item.sources))];
  }
  await delay();
  return mergePersistedConflicts();
}

export async function createConflict(input: { title: string; sourceA: string; sourceB: string; topic: string }): Promise<Conflict> {
  const clean = {
    title: input.title.trim(),
    sourceA: input.sourceA.trim(),
    sourceB: input.sourceB.trim(),
    topic: input.topic.trim(),
  };
  if (Object.values(clean).some((value) => value.length === 0)) throw new Error("Complete every field before adding the conflict.");
  const backend = await backendRequest<BackendConflict>("/api/conflicts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_a: clean.sourceA, source_b: clean.sourceB, topic: clean.title, description: clean.topic, status: "Open" }),
  });
  if (backend !== null) {
    return { slug: `local-api-${backend.id}`, topic: backend.topic, sources: `${backend.source_a} ↔ ${backend.source_b}`, owner: clean.topic, status: backend.status, detected: "Just now" };
  }
  await delay();
  const sourceKey = [clean.sourceA.toLowerCase(), clean.sourceB.toLowerCase()].sort().join("|");
  const duplicate = mergePersistedConflicts().some((conflict) => {
    const existingSourceKey = conflict.sources.split(" ↔ ").map((source) => source.toLowerCase()).sort().join("|");
    return conflict.topic.toLowerCase() === clean.title.toLowerCase() && existingSourceKey === sourceKey;
  });
  if (duplicate) throw new Error("That conflict is already in the log.");
  const conflict: Conflict = { slug: `local-${Date.now()}`, topic: clean.title, sources: `${clean.sourceA} ↔ ${clean.sourceB}`, owner: clean.topic, status: "Open", detected: "Just now" };
  const manual = readStoredArray<Conflict>(manualConflictsStorageKey);
  writeStoredArray(manualConflictsStorageKey, [conflict, ...manual]);
  return conflict;
}

export async function getConflict(slug: string): Promise<ConflictDetail> {
  await delay();
  const detail = conflictDetails[slug];
  if (detail === undefined) throw new Error(`Conflict not found: ${slug}`);
  return { ...detail, left: { ...detail.left }, right: { ...detail.right }, aiSummary: [...detail.aiSummary] };
}

export async function resolveConflict(slug: string, note: string): Promise<Conflict> {
  const conflict = mergePersistedConflicts().find((item) => item.slug === slug);
  if (note.trim().length === 0) throw new Error("A resolution note is required.");
  if (slug.startsWith("local-api-")) {
    const conflictId = slug.replace("local-api-", "");
    const backend = await backendRequest<BackendConflict>(
      `/api/conflicts/${encodeURIComponent(conflictId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "Resolved", resolution_note: note.trim() }),
      },
    );
    if (backend !== null) return { slug, topic: backend.topic, sources: `${backend.source_a} ↔ ${backend.source_b}`, owner: "Faculty Affairs", status: backend.status, detected: new Date(backend.created_at).toLocaleDateString() };
  }
  await delay();
  if (conflict === undefined) throw new Error(`Conflict not found: ${slug}`);
  const state = readConflictState();
  state[slug] = { status: "Resolved", note: note.trim(), detected: state[slug]?.detected ?? conflict.detected };
  writeConflictState(state);
  return { ...conflict, status: "Resolved", detected: state[slug].detected ?? conflict.detected };
}

export function getConflictResolutionNote(slug: string): string {
  return readConflictState()[slug]?.note ?? "";
}

export async function getSources(): Promise<KnowledgeSource[]> {
  await delay();
  const uploaded = readStoredArray<KnowledgeSource>(uploadedSourcesStorageKey);
  return [...uploaded, ...sources.filter((source) => !uploaded.some((item) => item.title.toLowerCase() === source.title.toLowerCase()))].map((source) => ({ ...source }));
}

export interface RegistrySource {
  id: string;
  title: string;
  sourceType: "handbook" | "cba" | "policystat" | "catalog" | "uploads";
  status: "active" | "archived";
  canonicalUrl: string;
  owner: string;
  sectionIndex: Record<string, string>;
  editionYear: number | null;
  isCurrent: boolean;
  passages: number;
  updated: string;
}

const mapRegistrySource = (item: BackendRegistrySource): RegistrySource => ({
  id: item.id,
  title: item.title,
  sourceType: item.source_type,
  status: item.status,
  canonicalUrl: item.canonical_url,
  owner: item.owner,
  sectionIndex: item.section_index,
  editionYear: item.edition_year,
  isCurrent: item.is_current,
  passages: item.passages,
  updated: new Date(item.updated_at).toLocaleDateString(),
});

export async function getRegistrySources(): Promise<RegistrySource[]> {
  const backend = await backendRequest<BackendRegistrySource[]>("/api/sources");
  return backend === null ? [] : backend.map(mapRegistrySource);
}

export async function setSourceStatus(id: string, status: "active" | "archived"): Promise<RegistrySource> {
  const backend = await backendRequest<BackendRegistrySource>(`/api/sources/${encodeURIComponent(id)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (backend === null) throw new Error("Unable to update the source status.");
  return mapRegistrySource(backend);
}

export interface Permission {
  userEmail: string;
  sourceType: RegistrySource["sourceType"];
  canAdd: boolean;
  canEdit: boolean;
}

export async function getPermissions(): Promise<Permission[]> {
  const backend = await backendRequest<BackendPermission[]>("/api/permissions");
  return backend === null ? [] : backend.map((item) => ({
    userEmail: item.user_email,
    sourceType: item.source_type,
    canAdd: item.can_add,
    canEdit: item.can_edit,
  }));
}

export async function savePermission(permission: Permission): Promise<Permission> {
  const backend = await backendRequest<BackendPermission>("/api/permissions", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_email: permission.userEmail,
      source_type: permission.sourceType,
      can_add: permission.canAdd,
      can_edit: permission.canEdit,
    }),
  });
  if (backend === null) throw new Error("Unable to save the permission.");
  return {
    userEmail: backend.user_email,
    sourceType: backend.source_type,
    canAdd: backend.can_add,
    canEdit: backend.can_edit,
  };
}

export function saveUploadedSource(source: KnowledgeSource): KnowledgeSource {
  const uploaded = readStoredArray<KnowledgeSource>(uploadedSourcesStorageKey);
  const next = [source, ...uploaded.filter((item) => item.title.toLowerCase() !== source.title.toLowerCase())];
  writeStoredArray(uploadedSourcesStorageKey, next);
  return { ...source };
}

const sourceTypeFromFile = (file: File): KnowledgeSource["type"] => {
  const extension = file.name.split(".").pop()?.toLowerCase();
  return extension === "pdf" ? "PDF" : extension === "docx" ? "DOCX" : "TXT";
};

const sourceFromIngestion = (file: File, update: IngestionUpdate): KnowledgeSource => ({
  title: file.name.replace(/\.[^.]+$/, ""),
  type: sourceTypeFromFile(file),
  passages: update.chunksAdded ?? Math.max(1, Math.round(file.size / 2_400)),
  status: update.status === "pending" ? "Pending" : update.status === "ingesting" ? "Ingesting" : update.status === "ready" ? "Ready" : "Failed",
  updated: "Just now",
});

const mockUploadStartedAt = new Map<string, number>();
const MAX_INGESTION_STATUS_FAILURES = 3;

export async function requestPresignedUpload(file: File): Promise<PresignedUpload> {
  if (hasConfiguredApi) {
    const backend = await backendRequest<BackendPresignedUploadResponse>("/api/uploads/presign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream" }),
    });
    if (backend !== null) return { uploadId: backend.upload_id, uploadUrl: backend.upload_url, headers: backend.headers ?? {}, mock: false };
    throw new Error("Unable to start the source upload. Please try again.");
  }
  const uploadId = `mock-upload-${Date.now()}`;
  mockUploadStartedAt.set(uploadId, Date.now());
  return { uploadId, uploadUrl: `mock://uploads/${uploadId}`, headers: {}, mock: true };
}

export async function putPresignedFile(file: File, upload: PresignedUpload): Promise<void> {
  if (upload.mock) {
    await delay(120);
    return;
  }
  const headers = new Headers(upload.headers);
  // Without CORPUS_BUCKET the presign endpoint hands back our own protected
  // /api/upload URL, which the auth middleware guards — attach the bearer
  // token there, but never leak it to S3 presigned URLs.
  if (upload.uploadUrl.startsWith(`${apiBaseUrl}/`)) {
    const authorizationToken = await getCognitoAuthorizationToken();
    if (authorizationToken !== null) headers.set("Authorization", `Bearer ${authorizationToken}`);
  }
  const response = await fetch(upload.uploadUrl, { method: "PUT", headers, body: file });
  if (!response.ok) throw new Error("The source file could not be uploaded to storage.");
}

export async function getIngestionStatus(uploadId: string): Promise<IngestionUpdate> {
  if (hasConfiguredApi) {
    const backend = await backendRequest<BackendIngestionResponse>(`/api/uploads/${encodeURIComponent(uploadId)}`);
    if (backend !== null) return { uploadId: backend.upload_id, status: backend.status, chunksAdded: backend.chunks_added, error: backend.error };
    throw new Error("Unable to check ingestion status.");
  }
  const elapsed = Date.now() - (mockUploadStartedAt.get(uploadId) ?? Date.now());
  const status: IngestionStatus = elapsed < 650 ? "pending" : elapsed < 2_250 ? "ingesting" : "ready";
  return { uploadId, status, ...(status === "ready" ? { chunksAdded: 12 } : {}) };
}

export async function pollIngestionStatus(uploadId: string, onUpdate: (update: IngestionUpdate) => void): Promise<IngestionUpdate> {
  let consecutiveFailures = 0;
  while (true) {
    let update: IngestionUpdate;
    try {
      update = await getIngestionStatus(uploadId);
      consecutiveFailures = 0;
    } catch (reason) {
      if (!hasConfiguredApi) throw reason;
      consecutiveFailures += 1;
      if (consecutiveFailures < MAX_INGESTION_STATUS_FAILURES) {
        await delay(600);
        continue;
      }
      update = {
        uploadId,
        status: "failed",
        error: reason instanceof Error ? reason.message : "Unable to check ingestion status.",
      };
    }
    onUpdate(update);
    if (update.status === "ready" || update.status === "failed") return update;
    await delay(600);
  }
}

/** Starts the same presigned-URL upload protocol used by the AWS deployment. */
export async function startSourceUpload(file: File): Promise<SourceUpload> {
  const upload = await requestPresignedUpload(file);
  await putPresignedFile(file, upload);
  const pending: IngestionUpdate = { uploadId: upload.uploadId, status: "pending" };
  return { source: saveUploadedSource(sourceFromIngestion(file, pending)), uploadId: upload.uploadId };
}

export async function uploadSource(file: File): Promise<KnowledgeSource> {
  const title = file.name.replace(/\.[^.]+$/, "");
  const type = sourceTypeFromFile(file);
  const formData = new FormData();
  formData.append("file", file);
  const result = await backendRequest<BackendUploadResponse>("/api/upload", { method: "POST", body: formData });
  if (result === null) {
    return saveUploadedSource({ title, type, passages: Math.max(1, Math.round(file.size / 2_400)), status: "Processing 64%", updated: "Just now" });
  }
  return saveUploadedSource({ title, type, passages: result.chunks_added, status: "Ready", updated: "Just now" });
}

export async function getDraftResolution(): Promise<DraftResolution> {
  await delay();
  return { ...draftResolution, sections: draftResolution.sections.map((section) => ({ ...section })) };
}

export async function checkResolution(text: string): Promise<ReviewAnalysis> {
  const normalized = normalizeQuestion(text);
  if (!normalized) throw new Error("Resolution text is required.");
  const backend = await backendRequest<BackendResolutionResponse>("/api/check-resolution", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  }, AGENT_REQUEST_TIMEOUT_MS, agentBaseUrl);
  if (backend !== null) {
    const findings = [
      ...backend.overlaps.map((finding) => ({ type: "Overlap" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.duplicates.map((finding) => ({ type: "Possible duplicate" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.conflicts.map((finding) => ({ type: "Conflict" as const, source: `${finding.source} • ${finding.section}` })),
    ];
    return {
      demoLabel: backend.mode === "agent-grounded" ? "Grounded Strands agent analysis" : backend.mode === "calibrated-static" ? "Calibrated local demo analysis" : "Local source-index analysis",
      steps: [{ label: "Retrieved passages", complete: true }, { label: "Compared sources", complete: true }, { label: "Classified findings", complete: true }, { label: "Prepared recommendation", complete: true }],
      coverageLabel: findings.length > 0 ? "Coverage found in supplied sources" : "No material overlap found",
      confidence: findings.length > 0 ? 94 : 70,
      findings,
      recommendation: backend.recommendation,
      agentTrace: (Array.isArray(backend.agent_trace) ? backend.agent_trace : reviewAnalysis.agentTrace).map(({ citations, ...step }) => ({
        ...step,
        ...(citations == null ? {} : { citations: citations.map((citation) => "source" in citation ? {
          id: citation.id,
          title: citation.source,
          section: citation.section,
          canonicalUrl: citation.canonical_url,
          sectionUrl: citation.section_url,
        } : { ...citation }) }),
      })),
    };
  }
  await delay();
  if (/\b(artificial intelligence|generative ai|ai tools?|large language model)\b/.test(normalized)) {
    return { ...reviewAnalysis, steps: reviewAnalysis.steps.map((step) => ({ ...step })), findings: reviewAnalysis.findings.map((finding) => ({ ...finding })), agentTrace: reviewAnalysis.agentTrace.map((step) => ({ ...step, ...(step.citations === undefined ? {} : { citations: step.citations.map((citation) => ({ ...citation })) }) })) };
  }
  if (/\b(ferp|faculty early retirement|retired annuitant|960 hours?)\b/.test(normalized)) {
    return {
      demoLabel: "Calibrated static demo: supplied FERP/CBA/CalPERS scenario",
      steps: [{ label: "Retrieved 12 passages", complete: true }, { label: "Compared 3 supplied sources", complete: true }, { label: "Found overlapping limits", complete: true }, { label: "Flagged for confirmation", complete: true }],
      coverageLabel: "FERP coverage found in supplied sources",
      confidence: 96,
      findings: [
        { type: "Overlap", source: "Unit 3 CBA Article 29.8-29.9" },
        { type: "Overlap", source: "CalPERS Employment After Retirement • 960-hour limit" },
        { type: "Possible duplicate", source: "CSUB FERP FAQs • campus implementation guidance" },
      ],
      recommendation: "Static demo result: reconcile the draft with the most restrictive CBA and CalPERS limit, then confirm the individual appointment with Faculty Affairs.",
      agentTrace: [
        { agent: "orchestrator", label: "Orchestrator scoped the FERP review", status: "complete", detail: "Directed a grounded comparison of appointment limits and retirement guidance." },
        { agent: "retrieval", label: "Retrieval collected 12 passages", status: "complete", detail: "Retrieved CBA, CalPERS, and campus FAQ passages.", citations: [{ id: 1, title: "Unit 3 Collective Bargaining Agreement", section: "Article 29.8-29.9" }, { id: 2, title: "CalPERS Employment After Retirement", section: "960-hour limit" }] },
        { agent: "extractor", label: "Extractors compared numeric limits", status: "complete", detail: "Parallel extraction isolated 90-workday, 50% timebase, and 960-hour constraints." },
        { agent: "conflict", label: "Conflict detector found overlapping limits", status: "warning", detail: "The sources impose cumulative constraints; an individual appointment requires confirmation." },
        { agent: "verifier", label: "Verifier checked supporting spans", status: "complete", detail: "The recommendation is tied to retrieved source sections." },
        { agent: "escalation", label: "Escalation routed appointment review", status: "warning", detail: "Faculty Affairs should confirm the applicable limit for the individual appointment." },
      ],
    };
  }
  return {
    demoLabel: "Static demo limitation: no calibrated scenario match",
    steps: [{ label: "Checked demo scenarios", complete: true }, { label: "No grounded match", complete: true }, { label: "No findings generated", complete: true }, { label: "Source review required", complete: true }],
    coverageLabel: "No calibrated coverage result",
    confidence: 0,
    findings: [],
    recommendation: "This static demo will not invent overlap or conflict findings for unrelated text. Use the FERP or generative-AI sample, or connect the production retrieval service.",
    agentTrace: [
      { agent: "orchestrator", label: "Orchestrator received the draft", status: "complete", detail: "Prepared a grounded review request." },
      { agent: "retrieval", label: "Retrieval found no calibrated evidence", status: "warning", detail: "The local demo has no reviewed source scenario for this text." },
      { agent: "extractor", label: "Extraction abstained", status: "pending", detail: "No unsupported obligations were extracted." },
      { agent: "conflict", label: "Conflict detection abstained", status: "pending", detail: "No finding was generated without source coverage." },
      { agent: "verifier", label: "Verifier preserved abstention", status: "complete", detail: "The result correctly avoids ungrounded conclusions." },
      { agent: "escalation", label: "Escalation requested source review", status: "warning", detail: "Connect production retrieval or review the source set manually." },
    ],
  };
}

export interface DraftRevision {
  draftId: string;
  version: number;
  revisedText: string;
  rationale: string;
  title: string;
  owner: string;
  status: DraftStatus;
  findings: ReviewAnalysis["findings"];
  recommendation: string;
  agentTrace: AgentTraceStep[];
}

export type DraftStatus = "draft" | "in_review" | "archived";

export interface DraftVersionRecord {
  draftId: string;
  version: number;
  title: string;
  owner: string;
  status: DraftStatus;
  text: string;
  sourceText: string;
  instruction: string;
  suggestion: string;
  restoredFromVersion: number | null;
  createdAt: string;
}

export interface DraftSummaryRecord {
  draftId: string;
  title: string;
  owner: string;
  status: DraftStatus;
  latestVersion: number;
  latestText: string;
  updatedAt: string;
}

export interface DraftComparisonRecord {
  draftId: string;
  fromVersion: number;
  toVersion: number;
  fromText: string;
  toText: string;
  unifiedDiff: string;
}

const mapDraftVersion = (value: BackendDraftVersion): DraftVersionRecord => ({
  draftId: value.draft_id,
  version: value.version,
  title: value.title,
  owner: value.owner,
  status: value.status,
  text: value.text,
  sourceText: value.source_text,
  instruction: value.instruction,
  suggestion: value.suggestion,
  restoredFromVersion: value.restored_from_version,
  createdAt: value.created_at,
});

const mapDraftSummary = (value: BackendDraftSummary): DraftSummaryRecord => ({
  draftId: value.draft_id,
  title: value.title,
  owner: value.owner,
  status: value.status,
  latestVersion: value.latest_version,
  latestText: value.latest_text,
  updatedAt: value.updated_at,
});

export async function listDrafts(): Promise<DraftSummaryRecord[]> {
  const backend = await backendRequest<BackendDraftSummary[]>("/api/draft");
  if (backend === null) return [];
  return backend.map(mapDraftSummary);
}

export async function getDraftVersions(draftId: string): Promise<DraftVersionRecord[]> {
  const backend = await backendRequest<BackendDraftVersion[]>(`/api/draft/${encodeURIComponent(draftId)}/versions`);
  if (backend === null) throw new Error("Unable to load draft versions.");
  return backend.map(mapDraftVersion);
}

export async function saveDraftVersion(input: {
  draftId?: string;
  title: string;
  text: string;
  status: DraftStatus;
}): Promise<DraftVersionRecord> {
  const backend = await backendRequest<BackendDraftVersion>("/api/draft/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: input.title,
      text: input.text,
      status: input.status,
      ...(input.draftId === undefined ? {} : { draft_id: input.draftId }),
    }),
  });
  if (backend === null) throw new Error("Unable to save this draft.");
  return mapDraftVersion(backend);
}

export async function restoreDraftVersion(draftId: string, version: number): Promise<DraftVersionRecord> {
  const backend = await backendRequest<BackendDraftVersion>(
    `/api/draft/${encodeURIComponent(draftId)}/restore/${version}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
  );
  if (backend === null) throw new Error("Unable to restore this draft version.");
  return mapDraftVersion(backend);
}

export async function compareDraftVersions(
  draftId: string,
  fromVersion: number,
  toVersion: number,
): Promise<DraftComparisonRecord> {
  const query = new URLSearchParams({ from_version: String(fromVersion), to_version: String(toVersion) });
  const backend = await backendRequest<BackendDraftComparison>(
    `/api/draft/${encodeURIComponent(draftId)}/compare?${query.toString()}`,
  );
  if (backend === null) throw new Error("Unable to compare these draft versions.");
  return {
    draftId: backend.draft_id,
    fromVersion: backend.from_version,
    toVersion: backend.to_version,
    fromText: backend.from_text,
    toText: backend.to_text,
    unifiedDiff: backend.unified_diff,
  };
}

export async function reviseDraft(
  text: string,
  draftId?: string,
  options: { title?: string; instruction?: string; status?: DraftStatus } = {},
): Promise<DraftRevision> {
  const backend = await backendRequest<BackendDraftRevision>("/api/draft/revise", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      title: options.title ?? "Untitled draft",
      instruction: options.instruction ?? "",
      status: options.status ?? "draft",
      ...(draftId === undefined ? {} : { draft_id: draftId }),
    }),
  }, AGENT_REQUEST_TIMEOUT_MS, agentBaseUrl);
  if (backend === null) throw new Error("The drafting assistant is unavailable. Start the backend and try again.");
  return {
    draftId: backend.draft_id,
    version: backend.version,
    revisedText: backend.revised_text,
    rationale: backend.rationale,
    title: backend.title,
    owner: backend.owner,
    status: backend.status,
    recommendation: backend.recommendation,
    findings: [
      ...backend.overlaps.map((finding) => ({ type: "Overlap" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.duplicates.map((finding) => ({ type: "Possible duplicate" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.conflicts.map((finding) => ({ type: "Conflict" as const, source: `${finding.source} • ${finding.section}` })),
    ],
    agentTrace: backend.agent_trace.map(({ citations, ...step }) => ({
      ...step,
      ...(citations == null ? {} : { citations: citations.map((citation) => ({
        id: citation.id,
        title: citation.source,
        section: citation.section,
        canonicalUrl: citation.canonical_url,
        sectionUrl: citation.section_url,
      })) }),
    })),
  };
}
