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

const reviewSubmissionStorageKey = "policy-intelligence.review-submission";
const conflictStateStorageKey = "policy-intelligence.conflict-state-v2";
const manualConflictsStorageKey = "policy-intelligence.manual-conflicts-v1";
const uploadedSourcesStorageKey = "policy-intelligence.uploaded-sources-v1";
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

interface BackendCitation { id: number; source: string; section: string; excerpt: string; }
interface BackendChatResponse {
  answer_id: string;
  answer: string;
  citations: BackendCitation[];
  conflict: { detected: boolean; guidance: string } | null;
  mode: "local-index" | "calibrated-static";
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
  mode: "local-index" | "calibrated-static";
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
interface BackendTopicSummary { name: string; count: number; }
interface BackendTopicDetail { name: string; chunks: Array<{ source: string; section: string; excerpt: string }>; }

const backendRequest = async <T>(path: string, init?: RequestInit): Promise<T | null> => {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4_000);
  try {
    const response = await fetch(`${apiBaseUrl}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) return null;
    return await response.json() as T;
  } catch {
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

const delay = async (milliseconds = 80): Promise<void> => {
  await new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
};

export async function login(role: Role): Promise<LoginResult> {
  const email = role === "reviewer" ? "reviewer@campus.edu" : "employee@campus.edu";
  const result = await backendRequest<LoginResult>("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: "demo123" }),
  });
  if (result !== null) return result;
  await delay();
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

export async function askQuestion(text: string): Promise<Answer> {
  const question = text.trim();
  if (!question) throw new Error("Enter a policy question.");
  const backend = await backendRequest<BackendChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (backend !== null) {
    const paragraphs = backend.answer.split(/\n\s*\n/).filter(Boolean);
    return {
      answerId: backend.answer_id,
      mode: backend.mode,
      question,
      heading: paragraphs[0]?.split(/[.!?]\s/)[0] ?? "Grounded policy response",
      paragraphs,
      citations: backend.citations.map((citation) => ({ id: citation.id, title: citation.source, section: citation.section })),
      ...(backend.conflict?.detected ? { conflictBanner: `Policy conflict — ${backend.conflict.guidance}` } : {}),
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
    if (typeof title !== "string" || typeof text !== "string" || (fileName !== undefined && typeof fileName !== "string")) return null;
    return fileName === undefined ? { title, text } : { title, text, fileName };
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

export function saveUploadedSource(source: KnowledgeSource): KnowledgeSource {
  const uploaded = readStoredArray<KnowledgeSource>(uploadedSourcesStorageKey);
  const next = [source, ...uploaded.filter((item) => item.title.toLowerCase() !== source.title.toLowerCase())];
  writeStoredArray(uploadedSourcesStorageKey, next);
  return { ...source };
}

export async function uploadSource(file: File): Promise<KnowledgeSource> {
  const title = file.name.replace(/\.[^.]+$/, "");
  const extension = file.name.split(".").pop()?.toLowerCase();
  const type: KnowledgeSource["type"] = extension === "pdf" ? "PDF" : "TXT";
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
  });
  if (backend !== null) {
    const findings = [
      ...backend.overlaps.map((finding) => ({ type: "Overlap" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.duplicates.map((finding) => ({ type: "Possible duplicate" as const, source: `${finding.source} • ${finding.section}` })),
      ...backend.conflicts.map((finding) => ({ type: "Conflict" as const, source: `${finding.source} • ${finding.section}` })),
    ];
    return {
      demoLabel: backend.mode === "calibrated-static" ? "Calibrated local demo analysis" : "Local source-index analysis",
      steps: [{ label: "Retrieved passages", complete: true }, { label: "Compared sources", complete: true }, { label: "Classified findings", complete: true }, { label: "Prepared recommendation", complete: true }],
      coverageLabel: findings.length > 0 ? "Coverage found in supplied sources" : "No material overlap found",
      confidence: findings.length > 0 ? 94 : 70,
      findings,
      recommendation: backend.recommendation,
    };
  }
  await delay();
  if (/\b(artificial intelligence|generative ai|ai tools?|large language model)\b/.test(normalized)) {
    return { ...reviewAnalysis, steps: reviewAnalysis.steps.map((step) => ({ ...step })), findings: reviewAnalysis.findings.map((finding) => ({ ...finding })) };
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
    };
  }
  return {
    demoLabel: "Static demo limitation: no calibrated scenario match",
    steps: [{ label: "Checked demo scenarios", complete: true }, { label: "No grounded match", complete: true }, { label: "No findings generated", complete: true }, { label: "Source review required", complete: true }],
    coverageLabel: "No calibrated coverage result",
    confidence: 0,
    findings: [],
    recommendation: "This static demo will not invent overlap or conflict findings for unrelated text. Use the FERP or generative-AI sample, or connect the production retrieval service.",
  };
}
