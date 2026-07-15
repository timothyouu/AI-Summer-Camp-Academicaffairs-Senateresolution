export type Role = "employee" | "reviewer";

export interface Citation {
  id: number;
  title: string;
  section: string;
}

export interface Answer {
  question: string;
  heading: string;
  paragraphs: string[];
  conflictBanner?: string;
  citations: Citation[];
}

export interface ReviewSubmission {
  title: string;
  text: string;
  fileName?: string;
}

export interface LibraryItem {
  id: string;
  title: string;
  kind: "Answer" | "Policy";
  time: string;
  sourceCount: number;
  bookmarked: boolean;
  group: "Today" | "Yesterday" | "Earlier";
}

export interface Topic {
  slug: string;
  name: string;
  count: number;
  description: string;
}

export interface PolicyRow {
  title: string;
  source: string;
  section: string;
  updated: string;
  badge?: "Potential conflict";
}

export interface TopicDetail {
  topic: Topic;
  sourceFilters: string[];
  commonQuestions: string[];
  policies: PolicyRow[];
}

export type ReviewStatus = "Ready" | "In progress" | "Needs attention";

export interface RecentReview {
  title: string;
  status: ReviewStatus;
  updated: string;
}

export interface OpenConflict {
  slug: string;
  title: string;
  overlappingSources: number;
}

export type ConflictStatus = "Open" | "Under review" | "Resolved";

export interface Conflict {
  slug: string;
  topic: string;
  sources: string;
  owner: string;
  status: ConflictStatus;
  detected: string;
}

export interface ConflictSourcePanel {
  title: string;
  beforeHighlight: string;
  highlight: string;
  afterHighlight: string;
  supportingText: string;
}

export interface ConflictDetail {
  slug: string;
  title: string;
  subtitle: string;
  left: ConflictSourcePanel;
  right: ConflictSourcePanel;
  aiSummary: string[];
  disclaimer: string;
}

export type SourceStatus = "Pending" | "Ingesting" | "Ready" | "Failed" | "Processing 64%" | "Needs review";

export interface KnowledgeSource {
  title: string;
  type: "PDF" | "DOCX" | "TXT";
  passages: number;
  status: SourceStatus;
  updated: string;
}

export interface DraftSection {
  number: number;
  title: string;
  body: string;
}

export interface DraftResolution {
  title: string;
  wordCount: number;
  sections: DraftSection[];
}

export interface ReviewProgressStep {
  label: string;
  complete: boolean;
}

export type FindingType = "Overlap" | "Possible duplicate" | "Conflict";

export interface ReviewFinding {
  type: FindingType;
  source: string;
  conflictSlug?: string;
}

export interface ReviewAnalysis {
  steps: ReviewProgressStep[];
  coverageLabel: string;
  confidence: number;
  findings: ReviewFinding[];
  recommendation: string;
  demoLabel: string;
  agentTrace: AgentTraceStep[];
}

export type AgentName = "orchestrator" | "retrieval" | "extractor" | "conflict" | "verifier" | "escalation";
export type AgentTraceStatus = "pending" | "running" | "complete" | "warning" | "failed";

export interface AgentTraceStep {
  agent: AgentName;
  label: string;
  status: AgentTraceStatus;
  detail?: string;
  citations?: Citation[];
}

export const suggestionChips = [
  "Tenure clock",
  "Workload",
  "Accessibility",
  "GECCo Committee",
] as const;

export const canonicalAnswer: Answer = {
  question: "Does service credit count toward the tenure clock?",
  heading: "Both supplied sources allow up to two years of prior-service credit",
  paragraphs: [
    "CSUB University Handbook section 304.4.1 permits up to two years of service credit toward the probationary period. Unit 3 CBA Article 13.4 likewise permits up to two years of credit for prior service. The supplied sources align on that ceiling. [1, 2]",
    "Credit is not automatic. The appointment record determines whether credit was granted and how much applies, so Faculty Affairs should confirm the written appointment terms before calculating a tenure-review date. [1, 2]",
  ],
  citations: [
    { id: 1, title: "CSUB University Handbook 2025", section: "Section 304.4.1 • Prior service credit" },
    { id: 2, title: "Unit 3 Collective Bargaining Agreement", section: "Article 13.4 • Prior service credit" },
  ],
};

export const conversationAnswers: Readonly<Record<string, Answer>> = {
  "service-credit": canonicalAnswer,
  "ferp-work-limits": {
    question: "How much can I work each year while participating in FERP?",
    heading: "FERP and CalPERS impose overlapping limits",
    paragraphs: [
      "CBA Article 29.8 limits a FERP period of employment to one academic term and no more than 90 workdays or 50% of the employee's regular timebase in the year before retirement. Summer, special-session, or extension days that do not coincide with the FERP period are included in that calculation. [1]",
      "CalPERS separately limits CSU academic retired-annuitant work to 960 hours in a fiscal year or 50% of the prior fiscal year's hours, whichever is less, combining work for all CalPERS employers. The 960-hour ceiling does not override Article 29's narrower appointment limit. [2, 3]",
    ],
    conflictBanner: "Policy conflict — These limits are cumulative, not alternatives. Faculty Affairs and CalPERS should confirm the most restrictive limit for the individual appointment.",
    citations: [
      { id: 1, title: "Unit 3 Collective Bargaining Agreement", section: "Article 29.8-29.9 • PDF pp. 161-162" },
      { id: 2, title: "CalPERS Employment After Retirement", section: "Retired Annuitant Rules - 960-Hour Limit • PDF p. 9" },
      { id: 3, title: "CSUB FERP FAQs (July 8, 2026)", section: "FAQs 18 and 21 • Guidance subject to change" },
    ],
  },
  "ferp-notice": {
    question: "When must I notify the President that I want to enter FERP?",
    heading: "Provide written notice at least six months before the academic year",
    paragraphs: [
      "CBA Article 29.2 requires written notice to the President at least six months before the beginning of the campus academic year. The President may waive that notice period but is not required to do so. [1]",
      "The July 8, 2026 CSUB FERP FAQ operationalizes this as a February 15 deadline and directs faculty to copy the Provost, Dean, and AVP for Faculty Affairs. February 15 is campus guidance; the controlling CBA wording remains 'at least six months.' [2, 3]",
    ],
    conflictBanner: "Policy conflict — No direct contradiction is identified, but a late request depends on a discretionary presidential waiver; the campus FAQ should not be read as guaranteeing one.",
    citations: [
      { id: 1, title: "Unit 3 Collective Bargaining Agreement", section: "Article 29.2 • PDF p. 160" },
      { id: 2, title: "CSUB FERP FAQs (July 8, 2026)", section: "FAQ 6 • Campus notice process" },
      { id: 3, title: "CSUB FERP FAQs (July 8, 2026)", section: "FAQ 7 • Late-notice waiver" },
    ],
  },
  "ferp-180-day-wait": {
    question: "Does the CalPERS 180-day waiting period apply to FERP?",
    heading: "Qualifying CSU FERP participation is listed as an exception",
    paragraphs: [
      "CalPERS states a general 180-day waiting period for retired-annuitant employment and lists participation in the CSU Faculty Early Retirement Program under a qualifying collective bargaining agreement as an exception. [1]",
      "Other requirements can still apply. A retiree younger than normal retirement age must satisfy separate bona fide separation rules, and a retirement or separation incentive can remove eligibility for an exception. Confirm the individual facts with CalPERS and Faculty Affairs. [2, 3]",
    ],
    conflictBanner: "Policy conflict — A blanket statement that every FERP appointment must wait 180 days conflicts with the stated CalPERS FERP exception, but the exception does not waive every other eligibility rule.",
    citations: [
      { id: 1, title: "CalPERS Employment After Retirement", section: "Eligibility Requirements for Retired Annuitants • PDF pp. 10-11" },
      { id: 2, title: "CalPERS Employment After Retirement", section: "Bona fide separation and incentive qualifiers • PDF pp. 10-11" },
      { id: 3, title: "CSUB FERP FAQs (July 8, 2026)", section: "FAQ 20 • Guidance subject to change" },
    ],
  },
  "wpaf-evidence": {
    question: "What evidence belongs in my WPAF?",
    heading: "Use organized, representative evidence aligned to the review",
    paragraphs: [
      "Handbook Appendix G calls for a log or access record, master index, assignments sheet, current vita, current Unit RTP Criteria, prior and current evaluations, and documentation organized by review area. Teaching evidence includes SOCIs and may include representative syllabi, course materials, peer evaluations, professional development, curriculum work, and advising evidence. [1]",
      "Supplied RES 252644 replaces paper-era size guidance with electronic organization and representative evidence. Developmental reviews emphasize work since the most recent WPAF submission; cumulative reviews use the broader relevant period. [2, 3]",
    ],
    conflictBanner: "Policy conflict — Treat the 2025 Handbook as the baseline and RES 252644 as a supplied later amendment; the corpus does not independently confirm every adoption or effective-date detail.",
    citations: [
      { id: 1, title: "CSUB University Handbook 2025", section: "Appendix G • PDF pp. 154-158" },
      { id: 2, title: "RES 252644: WPAF Contents and Timelines", section: "Resolution overview • PDF pp. 1-2" },
      { id: 3, title: "RES 252644: WPAF Contents and Timelines", section: "Clean/revised Appendix G • Supplied later resolution" },
    ],
  },
  "rtp-committee": {
    question: "Who may serve on a Unit RTP Committee?",
    heading: "Eligible tenured faculty are elected, with at least three members",
    paragraphs: [
      "Under supplied RES 252610, the unit elects the committee from eligible tenured faculty, with no fewer than three full-time tenured members. Rank and conflict rules apply, and a unit chair who submits a separate evaluation may not participate in that candidate's committee review. [1]",
      "FERP faculty may be eligible in accordance with their FERP contracts and may decline service. RES 252610 expressly replaces or amends Handbook sections 305.4.1, 305.6.1-.4, and 306.3, so it should be shown alongside the 2025 Handbook baseline. [2, 3]",
    ],
    conflictBanner: "Policy conflict — A two-person committee conflicts with the supplied later resolution's minimum of three; confirm the resolution's adoption/effective metadata before operational use.",
    citations: [
      { id: 1, title: "RES 252610: RTP/PTR Committee Composition", section: "Committee eligibility and composition • PDF pp. 1-3" },
      { id: 2, title: "RES 252610: RTP/PTR Committee Composition", section: "Clean language • PDF p. 11" },
      { id: 3, title: "CSUB University Handbook 2025", section: "Section 305.6.1 • PDF p. 77 (baseline)" },
    ],
  },
  "temporary-faculty-evaluation": {
    question: "How often is temporary faculty evaluated?",
    heading: "The schedule depends on appointment length and department service",
    paragraphs: [
      "CBA Articles 15.23-.24 require periodic evaluation for full- or part-time temporary faculty appointed for at least two semesters or three quarters, regardless of a break in service. Faculty on three-year appointments are evaluated at least once during the appointment and may be evaluated more often at the employee's or President's request. [1]",
      "Supplied RES 252645 adds CSUB procedures: service in different departments is evaluated separately, and its clean version distinguishes annual review for many non-three-year appointments from third-year review for three-year appointments, subject to the resolution's stated exceptions. [2, 3]",
    ],
    conflictBanner: "Policy conflict — No direct contradiction is identified, but the CBA minimum and supplied campus schedule must be applied together; confirm adoption/effective metadata for RES 252645.",
    citations: [
      { id: 1, title: "Unit 3 Collective Bargaining Agreement", section: "Articles 15.23-15.28 • PDF pp. 83-84" },
      { id: 2, title: "RES 252645: Periodic Evaluation of Temporary Faculty", section: "Approved revisions • PDF pp. 1-4" },
      { id: 3, title: "RES 252645: Periodic Evaluation of Temporary Faculty", section: "Clean schedule • Supplied later resolution" },
    ],
  },
  "office-hours-six-wtu": {
    question: "What office hours are expected for a 6-WTU lecturer?",
    heading: "The Handbook formula yields two hours per week",
    paragraphs: [
      "Handbook section 303.1.3 says part-time teaching faculty schedule at least one office hour per week, plus 20 minutes per week for each WTU above 3. For a 6-WTU lecturer, that formula is one hour plus 60 minutes, or two hours per week. [1]",
      "A department policy may require more. For comparison, full-time teaching faculty are generally expected to be available at least five office hours per week, including at least one hour per day on at least three days, with fewer days or hours requiring formal written approval. [2, 3]",
    ],
    conflictBanner: "Policy conflict — No conflicting supplied source was identified. The calculation is a Handbook minimum, and department policy may set a higher expectation.",
    citations: [
      { id: 1, title: "CSUB University Handbook 2025", section: "Section 303.1.3 • Part-time formula • PDF p. 35" },
      { id: 2, title: "CSUB University Handbook 2025", section: "Section 303.1.3 • Full-time availability • PDF p. 35" },
    ],
  },
  "workload-overview": {
    question: "What does faculty workload policy cover?",
    heading: "Workload includes the full range of assigned faculty responsibilities",
    paragraphs: [
      "Unit 3 CBA Article 20 is the supplied controlling source for faculty workload. It addresses instructional assignments alongside the other professional responsibilities assigned to faculty; a teaching-unit count alone is not a complete workload determination. [1]",
      "For a concrete campus rule, Handbook section 303.1.3 separately states office-hour expectations. A 6-WTU lecturer schedules at least two office hours per week under its part-time formula. [2]",
    ],
    citations: [
      { id: 1, title: "Unit 3 Collective Bargaining Agreement", section: "Article 20 • Workload" },
      { id: 2, title: "CSUB University Handbook 2025", section: "Section 303.1.3 • Faculty office hours • PDF p. 35" },
    ],
  },
  "accessibility-overview": {
    question: "Who reviews instructional technology for accessibility?",
    heading: "Accessibility review is shared across faculty, technology, procurement, and curriculum teams",
    paragraphs: [
      "Handbook Appendix K assigns faculty responsibility for accessible LMS and non-LMS content, accessible exams and documents, captions or transcripts for digital media, image descriptions, alt text, and language tags. [1]",
      "For campus-purchased software and hardware, Solutions Consulting and the Technology Accessibility Review teams bring together ITS, Procurement, the Library, and Services for Students with Disabilities. Program review, the Academic Affairs Committee, and school curriculum committees also incorporate accessibility compliance into curriculum review. [2, 3]",
    ],
    citations: [
      { id: 1, title: "CSUB University Handbook 2025", section: "Appendix K • IMAP Goal 4 • PDF p. 153" },
      { id: 2, title: "CSUB University Handbook 2025", section: "Appendix K • IMAP Goal 5 • PDF p. 154" },
      { id: 3, title: "CSUB University Handbook 2025", section: "Appendix K • IMAP Goal 6 • PDF p. 154" },
    ],
  },
  "gecco-overview": {
    question: "What is the GECCo Committee?",
    heading: "The supplied Handbook names GECCo leadership but does not define the committee charge",
    paragraphs: [
      "Handbook section 313 identifies the GECCo Director as a university-wide faculty director subject to a third-year review. The supplied Handbook does not spell out the committee's full charge, so this static demo does not invent one. [1]",
      "The name is commonly expanded in campus materials as the General Education Curriculum Committee. Confirm the current charge and membership from the linked committee resource before relying on a procedural answer. [2]",
    ],
    citations: [
      { id: 1, title: "CSUB University Handbook 2025", section: "Section 313 • University-wide faculty directors • PDF p. 111" },
      { id: 2, title: "Foundational Resource List - URLs", section: "GECCo committee resource link • supplied reference list" },
    ],
  },
  "emeriti-status": {
    question: "How does a faculty member qualify for Emeriti status?",
    heading: "Emeriti status recognizes sustained meritorious contribution",
    paragraphs: [
      "Handbook sections 308.2-.2.3 describe eligibility in terms of a retiring or retired faculty member's meritorious contributions over an extended period in teaching, scholarship, and/or service, together with strong commitment to the University. [1]",
      "A peer or group of peers submits the nomination and supporting materials; self-nominations are not allowed. The President makes the final award decision, and the campus FERP FAQ also points faculty to this process. [2, 3]",
    ],
    conflictBanner: "Policy conflict — No conflicting supplied source was identified. Eligibility does not guarantee an award; the President makes the final decision after nomination review.",
    citations: [
      { id: 1, title: "CSUB University Handbook 2025", section: "Sections 308.2-308.2.3 • PDF pp. 92-93" },
      { id: 2, title: "CSUB University Handbook 2025", section: "Emeriti nomination and decision process • PDF pp. 92-93" },
      { id: 3, title: "CSUB FERP FAQs (July 8, 2026)", section: "FAQ 33 • Guidance subject to change" },
    ],
  },
  "rtp-rebuttal-window": {
    question: "How long do I have to rebut an RTP evaluation?",
    heading: "Appendix G provides a seven-day response window",
    paragraphs: [
      "The 2025 Handbook says the faculty member receives each level's evaluation before the WPAF moves to the next review level. [1]",
      "After receiving that evaluation, the faculty member has seven days to submit a written rebuttal or response. Because supplied later resolutions amend parts of RTP policy, confirm the current calendar and delivery date with Faculty Affairs. [2, 3]",
    ],
    conflictBanner: "Policy conflict — No conflicting supplied source was identified for the seven-day window, but later RTP amendments and the actual notice date should be checked before calculating a deadline.",
    citations: [
      { id: 1, title: "CSUB University Handbook 2025", section: "Appendix G • Evaluation routing • PDF p. 155" },
      { id: 2, title: "CSUB University Handbook 2025", section: "Appendix G • Seven-day rebuttal/response • PDF p. 155" },
    ],
  },
  "ferp-rtp-service": {
    question: "Can a FERP faculty member serve on an RTP committee?",
    heading: "Potentially, when the contract and eligibility rules permit",
    paragraphs: [
      "Supplied RES 252610 says FERP faculty may be eligible for Unit RTP Committee service in accordance with their FERP contracts and may decline service. The committee must still satisfy the resolution's rank, conflict, and minimum-membership rules. [1]",
      "CBA Article 29.19 permits FERP participants to serve on governance committees whose assignments normally finish during the participant's active FERP work period. Read the appointment contract, CBA, and later committee resolution together. [2, 3]",
    ],
    conflictBanner: "Policy conflict — Eligibility is not automatic: the FERP contract, active work period, committee rules, rank, and conflict requirements all matter.",
    citations: [
      { id: 1, title: "RES 252610: RTP/PTR Committee Composition", section: "FERP eligibility and right to decline • PDF pp. 1-3" },
      { id: 2, title: "Unit 3 Collective Bargaining Agreement", section: "Article 29.19 • PDF p. 162" },
    ],
  },
  "wpaf-review-scope": {
    question: "Is a promotion WPAF developmental or cumulative?",
    heading: "The evidentiary period depends on the review type",
    paragraphs: [
      "Supplied RES 252644 distinguishes developmental reviews, which emphasize work since the most recent WPAF submission, from cumulative reviews, which use the broader relevant period. Evidence should be representative, organized electronically, and aligned with the applicable Unit RTP Criteria. [1]",
      "The 2025 Handbook Appendix G remains the baseline source for the WPAF's index, assignments, vita, criteria, evaluations, and review-area documentation. Use the later resolution for the updated evidence standard and confirm which review category applies to the promotion action. [2, 3]",
    ],
    conflictBanner: "Policy conflict — Paper-era physical-size guidance should not be carried forward where RES 252644 replaces it with electronic, representative evidence.",
    citations: [
      { id: 1, title: "RES 252644: WPAF Contents and Timelines", section: "Developmental and cumulative review scope • PDF pp. 1-2" },
      { id: 2, title: "CSUB University Handbook 2025", section: "Appendix G • PDF pp. 154-158 (baseline)" },
      { id: 3, title: "RES 252644: WPAF Contents and Timelines", section: "Clean/revised Appendix G • Supplied later resolution" },
    ],
  },
  "ferp-additional-employment": {
    question: "Can I accept summer or other additional employment during FERP?",
    heading: "Additional work requires advance review",
    paragraphs: [
      "CBA Article 29.14 generally bars other CSU appointments while a faculty member participates in FERP, subject to the agreement's exact extension and auxiliary provisions. Article 29.8 also counts certain summer, special-session, or extension days in the FERP period calculation. [1]",
      "The CSUB FAQ advises that additional work be reviewed in advance. Before accepting CSU, extension, summer, special-session, auxiliary, or work for another CalPERS employer, ask Faculty Affairs and CalPERS to verify Article 29, Article 36, timebase, and 960-hour compliance. [2, 3]",
    ],
    conflictBanner: "Policy conflict — Staying below 960 hours does not by itself authorize additional employment; Article 29 appointment restrictions and the narrower applicable ceiling still control.",
    citations: [
      { id: 1, title: "Unit 3 Collective Bargaining Agreement", section: "Articles 29.8 and 29.14 • PDF pp. 161-162" },
      { id: 2, title: "CSUB FERP FAQs (July 8, 2026)", section: "FAQ 26 • Advance review of additional work" },
      { id: 3, title: "CalPERS Employment After Retirement", section: "960-hour limit across CalPERS employers • PDF p. 9" },
    ],
  },
};

export const libraryItems: LibraryItem[] = [
  { id: "ferp-work-limits", title: "FERP work limits and the 960-hour rule", kind: "Answer", time: "10:24 AM", sourceCount: 3, bookmarked: true, group: "Today" },
  { id: "service-credit", title: canonicalAnswer.question, kind: "Answer", time: "9:48 AM", sourceCount: 2, bookmarked: true, group: "Today" },
  { id: "ferp-notice", title: "Six-month notice for entering FERP", kind: "Answer", time: "Yesterday 2:47 PM", sourceCount: 2, bookmarked: false, group: "Yesterday" },
  { id: "ferp-180-day-wait", title: "Does FERP bypass the 180-day wait?", kind: "Answer", time: "Yesterday 10:15 AM", sourceCount: 2, bookmarked: true, group: "Yesterday" },
  { id: "wpaf-evidence", title: "What evidence belongs in my WPAF?", kind: "Answer", time: "Jul 9", sourceCount: 2, bookmarked: true, group: "Earlier" },
  { id: "rtp-committee", title: "Unit RTP Committee eligibility and rank", kind: "Answer", time: "Jul 8", sourceCount: 2, bookmarked: false, group: "Earlier" },
  { id: "temporary-faculty-evaluation", title: "Temporary faculty evaluation schedule", kind: "Answer", time: "Jul 5", sourceCount: 2, bookmarked: false, group: "Earlier" },
  { id: "office-hours-six-wtu", title: "Office hours for a 6-WTU lecturer", kind: "Answer", time: "Jun 28", sourceCount: 1, bookmarked: false, group: "Earlier" },
  { id: "emeriti-status", title: "Emeriti nomination requirements", kind: "Answer", time: "Jun 24", sourceCount: 2, bookmarked: false, group: "Earlier" },
  { id: "rtp-rebuttal-window", title: "Seven-day rebuttal window in RTP review", kind: "Answer", time: "Jun 20", sourceCount: 1, bookmarked: true, group: "Earlier" },
  { id: "ferp-rtp-service", title: "Can a FERP faculty member serve on RTP?", kind: "Answer", time: "Jun 17", sourceCount: 2, bookmarked: false, group: "Earlier" },
  { id: "wpaf-review-scope", title: "Promotion WPAF: developmental or cumulative?", kind: "Answer", time: "Jun 11", sourceCount: 2, bookmarked: false, group: "Earlier" },
  { id: "ferp-additional-employment", title: "Additional employment during FERP", kind: "Answer", time: "Jun 3", sourceCount: 3, bookmarked: true, group: "Earlier" },
];

export const topics: Topic[] = [
  { slug: "tenure-promotion", name: "Tenure & Promotion", count: 18, description: "Appointments, service credit, evaluation, tenure, and promotion." },
  { slug: "hiring-appointments", name: "Hiring & Appointments", count: 24, description: "Recruitment, appointment types, searches, and onboarding." },
  { slug: "workload", name: "Workload", count: 16, description: "Faculty assignments, teaching load, and assigned time." },
  { slug: "curriculum", name: "Curriculum", count: 22, description: "Course, program, and curriculum approval requirements." },
  { slug: "accessibility", name: "Accessibility", count: 12, description: "Accessible technology, instruction, and campus services." },
  { slug: "senate-procedures", name: "Senate Procedures", count: 20, description: "Academic Senate governance, resolutions, and voting." },
  { slug: "committees", name: "Committees", count: 15, description: "Standing committees, membership, charges, and reporting." },
  { slug: "cba-labor", name: "CBA & Labor", count: 30, description: "Collective bargaining provisions and labor relations." },
];

export const tenurePromotionDetail: TopicDetail = {
  topic: topics[0],
  sourceFilters: ["All sources", "Handbook", "CBA"],
  commonQuestions: ["Does service credit count toward the tenure clock?", "What evidence belongs in my WPAF?", "How long do I have to rebut an RTP evaluation?"],
  policies: [
    { title: "Tenure and Tenure-Track Appointments", source: "University Handbook", section: "305.3", updated: "Apr 2 2024" },
    { title: "Service Credit Toward Tenure", source: "University Handbook", section: "304.4.1", updated: "Apr 10 2024", badge: "Potential conflict" },
    { title: "Periodic Evaluation of Probationary Faculty", source: "University Handbook", section: "305.6", updated: "Mar 18 2024" },
    { title: "Promotion Review Procedures", source: "University Handbook", section: "305.7", updated: "Apr 2 2024" },
    { title: "Personnel Action File", source: "University Handbook", section: "305.9", updated: "Jan 22 2024" },
    { title: "Unit 3 CBA — Article 13", source: "CBA", section: "Article 13", updated: "Nov 15 2023" },
  ],
};

export const topicDetails: Readonly<Record<string, TopicDetail>> = {
  "tenure-promotion": tenurePromotionDetail,
  "hiring-appointments": {
    topic: topics[1],
    sourceFilters: ["All sources", "Handbook", "CBA"],
    commonQuestions: ["What approvals are required for a faculty search?", "How are temporary appointments made?", "When must appointment terms be provided?"],
    policies: [
      { title: "Faculty Recruitment and Search Procedures", source: "University Handbook", section: "301.2", updated: "Apr 5 2024" },
      { title: "Appointment Types and Terms", source: "University Handbook", section: "302.1", updated: "Mar 22 2024" },
      { title: "Temporary Faculty Appointments", source: "Unit 3 CBA", section: "Article 12", updated: "Nov 15 2023" },
      { title: "Appointment and Reappointment", source: "Unit 3 CBA", section: "Article 13", updated: "Nov 15 2023" },
    ],
  },
  workload: {
    topic: topics[2],
    sourceFilters: ["All sources", "Handbook", "CBA"],
    commonQuestions: ["What office hours are expected for a 6-WTU lecturer?", "How much can I work each year while participating in FERP?", "Can I accept summer or other additional employment during FERP?"],
    policies: [
      { title: "Faculty Office Hours", source: "University Handbook", section: "303.1.3", updated: "Apr 12 2024" },
      { title: "FERP Employment Limits", source: "Unit 3 CBA", section: "Article 29.8", updated: "Nov 15 2023", badge: "Potential conflict" },
      { title: "Workload", source: "Unit 3 CBA", section: "Article 20", updated: "Nov 15 2023", badge: "Potential conflict" },
      { title: "Assigned Time", source: "Unit 3 CBA", section: "Article 20.3", updated: "Nov 15 2023" },
    ],
  },
  curriculum: {
    topic: topics[3],
    sourceFilters: ["All sources", "Handbook", "Senate Policy"],
    commonQuestions: ["What is the curriculum approval timeline?", "Who approves a new course?", "When does a program change reach the Senate?"],
    policies: [
      { title: "Curriculum Proposal Procedures", source: "University Handbook", section: "404.3", updated: "Apr 18 2024", badge: "Potential conflict" },
      { title: "New Course Approval", source: "University Handbook", section: "404.4", updated: "Apr 18 2024" },
      { title: "Program Modification Review", source: "Senate Policy", section: "CURR-02", updated: "Mar 8 2024" },
      { title: "General Education Course Review", source: "Senate Policy", section: "GECCo Charge", updated: "Feb 26 2024" },
    ],
  },
  accessibility: {
    topic: topics[4],
    sourceFilters: ["All sources", "Handbook", "CSU Policy"],
    commonQuestions: ["Who reviews instructional technology for accessibility?", "When is an accessibility exception allowed?", "What must an equally effective alternative provide?"],
    policies: [
      { title: "Instructional Materials Accessibility Plan", source: "University Handbook", section: "Appendix K", updated: "May 2 2024", badge: "Potential conflict" },
      { title: "Instructional Materials Accessibility", source: "University Handbook", section: "110.8", updated: "Apr 9 2024" },
      { title: "Accessible Technology Initiative", source: "CSU Policy", section: "ATI-01", updated: "Jan 30 2024" },
      { title: "Equally Effective Alternate Access", source: "CSU Policy", section: "ATI-03", updated: "Jan 30 2024" },
    ],
  },
  "senate-procedures": {
    topic: topics[5],
    sourceFilters: ["All sources", "Senate Bylaws", "Senate Policy"],
    commonQuestions: ["How is a Senate resolution introduced?", "What constitutes a quorum?", "When is a second reading required?"],
    policies: [
      { title: "Academic Senate Meeting Procedures", source: "Senate Bylaws", section: "Article IV", updated: "Apr 25 2024" },
      { title: "Quorum and Voting", source: "Senate Bylaws", section: "Article V", updated: "Apr 25 2024" },
      { title: "Resolution Submission and Readings", source: "Senate Policy", section: "GOV-01", updated: "Mar 14 2024" },
      { title: "Emergency Senate Business", source: "Senate Policy", section: "GOV-04", updated: "Mar 14 2024" },
    ],
  },
  committees: {
    topic: topics[6],
    sourceFilters: ["All sources", "Senate Bylaws", "Committee Charge"],
    commonQuestions: ["Who may serve on a Unit RTP Committee?", "Can a FERP faculty member serve on an RTP committee?", "What is the GECCo Committee charge?"],
    policies: [
      { title: "Standing Committee Membership", source: "Senate Bylaws", section: "Article VI", updated: "Apr 25 2024" },
      { title: "General Education Curriculum Committee", source: "Committee Charge", section: "GECCo", updated: "Feb 26 2024" },
      { title: "Faculty Affairs Committee", source: "Committee Charge", section: "FAC", updated: "Feb 26 2024" },
      { title: "Committee Reports and Recommendations", source: "Senate Bylaws", section: "Article VI.8", updated: "Apr 25 2024" },
    ],
  },
  "cba-labor": {
    topic: topics[7],
    sourceFilters: ["All sources", "CBA", "Handbook"],
    commonQuestions: ["How much can I work each year while participating in FERP?", "When must I notify the President that I want to enter FERP?", "Does the CalPERS 180-day waiting period apply to FERP?"],
    policies: [
      { title: "Grievance Procedure", source: "Unit 3 CBA", section: "Article 10", updated: "Nov 15 2023" },
      { title: "Appointment", source: "Unit 3 CBA", section: "Article 12", updated: "Nov 15 2023" },
      { title: "Evaluation", source: "Unit 3 CBA", section: "Article 15", updated: "Nov 15 2023" },
      { title: "Consultation and Workload", source: "Unit 3 CBA", section: "Article 20", updated: "Nov 15 2023", badge: "Potential conflict" },
      { title: "Collective Bargaining Administration", source: "University Handbook", section: "308.1", updated: "Apr 1 2024" },
    ],
  },
};

export const recentReviews: RecentReview[] = [
  { title: "Academic Calendars – Generative AI Use", status: "Ready", updated: "Updated 2 hours ago" },
  { title: "Data Classification and Handling", status: "In progress", updated: "Updated yesterday" },
  { title: "Student Use of AI in Coursework", status: "Needs attention", updated: "Updated 3 days ago" },
];

export const openConflicts: OpenConflict[] = [
  { slug: "ai-academic-administrative-work", title: "AI Use in Academic and Administrative Work", overlappingSources: 2 },
  { slug: "student-data-privacy", title: "Student Data Privacy in Third-Party Tools", overlappingSources: 3 },
  { slug: "generative-ai-instruction", title: "Use of Generative AI in Instruction", overlappingSources: 2 },
];

export const conflicts: Conflict[] = [
  { slug: "service-credit", topic: "Service credit source alignment", sources: "Handbook ↔ Unit 3 CBA", owner: "Faculty Affairs", status: "Resolved", detected: "May 8 2024 10:24 AM" },
  { slug: "ai-data-handling", topic: "AI use and data handling", sources: "Handbook ↔ AI Guidance (Demo stand-in)", owner: "Academic Technology", status: "Under review", detected: "May 7 2024 3:11 PM" },
  { slug: "schools-departments", topic: "Schools vs. departments", sources: "Handbook ↔ Unit 3 CBA", owner: "Governance", status: "Open", detected: "May 6 2024 1:42 PM" },
  { slug: "faculty-workload", topic: "Faculty workload calculation", sources: "Handbook ↔ Unit 3 CBA", owner: "Faculty Affairs", status: "Under review", detected: "May 5 2024 11:09 AM" },
  { slug: "accessibility-review", topic: "Accessibility review responsibility", sources: "Handbook ↔ CSU Policy", owner: "Compliance", status: "Resolved", detected: "May 4 2024 9:18 AM" },
  { slug: "curriculum-approval", topic: "Curriculum approval timeline", sources: "Handbook ↔ Unit 3 CBA", owner: "Academic Programs", status: "Resolved", detected: "May 3 2024 4:37 PM" },
  { slug: "ai-academic-administrative-work", topic: "AI Use in Academic and Administrative Work", sources: "Senate Resolution 2024-07 (Demo stand-in) ↔ Administrative AI Standard (Demo stand-in)", owner: "Academic Technology", status: "Open", detected: "May 2 2024 2:18 PM" },
  { slug: "student-data-privacy", topic: "Student Data Privacy in Third-Party Tools", sources: "Student Records Policy (Demo stand-in) ↔ Third-Party Technology Standard (Demo stand-in)", owner: "Privacy and Procurement", status: "Open", detected: "May 1 2024 11:32 AM" },
  { slug: "generative-ai-instruction", topic: "Use of Generative AI in Instruction", sources: "Academic Integrity Guidance (Demo stand-in) ↔ Inclusive Instruction Framework (Demo stand-in)", owner: "Academic Affairs", status: "Open", detected: "Apr 30 2024 9:45 AM" },
];

export const serviceCreditConflict: ConflictDetail = {
  slug: "service-credit",
  title: "Service credit source alignment",
  subtitle: "A completed review found that the supplied Handbook and Unit 3 CBA agree on the maximum credit.",
  left: {
    title: "University Handbook §304.4.1",
    beforeHighlight: "The Handbook permits ",
    highlight: "up to two years of prior-service credit",
    afterHighlight: "",
    supportingText: "The credit applies toward fulfillment of the probationary period when it is granted as part of the appointment.",
  },
  right: {
    title: "Unit 3 CBA Article 13.4",
    beforeHighlight: "The collective bargaining agreement likewise permits ",
    highlight: "up to two years of service credit",
    afterHighlight: ".",
    supportingText: "The appointment record is the source for whether credit was granted to a particular faculty member.",
  },
  aiSummary: [
    "Both supplied sources permit up to two years of prior-service credit.",
    "No source conflict remains; the individual appointment record determines whether credit was actually granted.",
    "Faculty Affairs should confirm the credited period before calculating a tenure-review date.",
  ],
  disclaimer: "Resolved as source alignment; individual appointment terms still require confirmation.",
};

function conflictDetail(
  slug: string, title: string, subtitle: string,
  left: ConflictSourcePanel, right: ConflictSourcePanel, aiSummary: string[],
): ConflictDetail {
  return { slug, title, subtitle, left, right, aiSummary, disclaimer: "The assistant does not determine which source controls." };
}

const additionalConflictDetails: ConflictDetail[] = [
  conflictDetail("ai-data-handling", "AI use and data handling", "Campus AI guidance and the University Handbook set different boundaries for protected information.",
    { title: "University Handbook §110.6", beforeHighlight: "Approved services may process university records when ", highlight: "institutional safeguards and access controls are in place", afterHighlight: ".", supportingText: "The provision conditionally allows authorized systems to handle protected records." },
    { title: "Campus AI Guidance §4", beforeHighlight: "Users must ", highlight: "not enter confidential or student data into generative AI tools", afterHighlight: ".", supportingText: "The guidance does not distinguish between approved and public AI services." },
    ["The Handbook conditionally permits approved services to process protected records.", "The AI guidance states a broader prohibition for generative AI tools.", "Academic Technology and Information Security should clarify whether approved AI services are an exception."]),
  conflictDetail("schools-departments", "Schools vs. departments", "Governance documents use different organizational units for faculty consultation.",
    { title: "University Handbook §201.2", beforeHighlight: "Consultation occurs through each ", highlight: "school or academic unit", afterHighlight: ".", supportingText: "The Handbook treats schools as the primary unit for specified governance actions." },
    { title: "Unit 3 CBA Article 20", beforeHighlight: "Faculty consultation occurs at the ", highlight: "department or equivalent unit", afterHighlight: ".", supportingText: "The agreement assigns consultation rights to departments and formally equivalent units." },
    ["The sources name different default units for faculty consultation.", "A school may be equivalent, but neither passage makes that explicit.", "Governance should document the campus mapping among schools, departments, and equivalent units."]),
  conflictDetail("faculty-workload", "Faculty workload calculation", "The Handbook and collective bargaining agreement describe assigned time differently.",
    { title: "University Handbook §303.1.3", beforeHighlight: "Faculty availability includes ", highlight: "scheduled office hours tied to instructional assignment", afterHighlight: ".", supportingText: "The supplied Handbook supports office-hour expectations; broader workload calculations require the CBA and current campus practice." },
    { title: "Unit 3 CBA Article 20", beforeHighlight: "Faculty workload includes instruction and ", highlight: "all assigned professional responsibilities", afterHighlight: ".", supportingText: "The agreement includes advising, research, service, and other assigned duties." },
    ["The Handbook emphasizes instructional units as the starting calculation.", "The CBA frames workload as the full set of professional responsibilities.", "Faculty Affairs should clarify how non-instructional work converts to assigned time."]),
  conflictDetail("accessibility-review", "Accessibility review responsibility", "Campus and system policies assign overlapping accessibility review duties.",
    { title: "University Handbook Appendix K", beforeHighlight: "The instructional materials accessibility plan requires the campus to ", highlight: "coordinate timely accessible instructional materials", afterHighlight: ".", supportingText: "Appendix K is the supplied Handbook location for the IMAP framework." },
    { title: "CSU Accessible Technology Policy §3", beforeHighlight: "The campus accessibility office must ", highlight: "coordinate and approve high-impact reviews", afterHighlight: ".", supportingText: "Central review applies to technology with broad use or significant barriers." },
    ["Both sources assign responsibility to different campus actors.", "The system policy focuses on high-impact acquisitions while the Handbook covers departmental adoption.", "Compliance should publish a review handoff and approval matrix."]),
  conflictDetail("curriculum-approval", "Curriculum approval timeline", "The Handbook calendar and bargaining consultation period may produce different deadlines.",
    { title: "University Handbook §404.3", beforeHighlight: "Complete proposals must reach the Senate by ", highlight: "October 1 for the next catalog year", afterHighlight: ".", supportingText: "Later proposals normally move to the following catalog cycle." },
    { title: "Unit 3 CBA Article 20", beforeHighlight: "Affected faculty must receive ", highlight: "at least 30 days for consultation", afterHighlight: ".", supportingText: "Consultation precedes changes affecting working conditions." },
    ["The fixed Senate deadline can conflict with consultation for late proposals.", "The sources govern different stages without reconciling compressed schedules.", "Academic Programs should set an earlier internal deadline when consultation is required."]),
  conflictDetail("ai-academic-administrative-work", "AI Use in Academic and Administrative Work", "Two campus sources set different approval expectations for routine AI-assisted work.",
    { title: "Senate Resolution 2024-07 §3 (Demo stand-in)", beforeHighlight: "Faculty and staff may use generative AI with ", highlight: "meaningful human review and disclosure", afterHighlight: ".", supportingText: "People remain accountable for AI-assisted work." },
    { title: "Administrative AI Standard §2 (Demo stand-in)", beforeHighlight: "AI use in business processes requires ", highlight: "prior unit and technology approval", afterHighlight: ".", supportingText: "Approval is required even when no restricted data is involved." },
    ["The Senate resolution permits responsible use based on review and disclosure.", "The administrative standard additionally requires prior approval.", "The campus should clarify which mixed academic-administrative activities require approval."]),
  conflictDetail("student-data-privacy", "Student Data Privacy in Third-Party Tools", "Privacy guidance differs on whether consent is sufficient for third-party processing.",
    { title: "Student Records Policy §7", beforeHighlight: "Information may be shared when ", highlight: "the student gives informed consent", afterHighlight: ".", supportingText: "The policy presents consent as a basis for limited disclosure." },
    { title: "Third-Party Technology Standard §5", beforeHighlight: "Student data may be processed only under ", highlight: "an approved contract and security review", afterHighlight: ".", supportingText: "Institutional controls apply regardless of individual consent." },
    ["One source presents consent as a basis for sharing student information.", "The technology standard always requires a contract and security review.", "Privacy and Procurement should clarify whether consent can ever replace vendor review."]),
  conflictDetail("generative-ai-instruction", "Use of Generative AI in Instruction", "Instructional guidance differs on course AI rules and access obligations.",
    { title: "Academic Integrity Guidance §4", beforeHighlight: "Instructors may ", highlight: "set course-specific limits on generative AI", afterHighlight: ".", supportingText: "Syllabi may define permitted assistance based on learning outcomes." },
    { title: "Inclusive Instruction Framework §6", beforeHighlight: "Students must have ", highlight: "equitable access to required instructional technologies", afterHighlight: ".", supportingText: "Required tools must be accessible and supported by an alternative when necessary." },
    ["Instructors may establish course-specific AI rules.", "Required AI tools also trigger access and alternative obligations.", "Academic Affairs should clarify approval and access expectations for required AI use."]),
];

export const conflictDetails: Readonly<Record<string, ConflictDetail>> = Object.fromEntries(
  [serviceCreditConflict, ...additionalConflictDetails].map((detail) => [detail.slug, detail]),
);

export const sources: KnowledgeSource[] = [
  { title: "University Handbook", type: "PDF", passages: 1024, status: "Ready", updated: "May 20 2024 10:42 AM" },
  { title: "Unit 3 CBA 2022–2026", type: "PDF", passages: 418, status: "Processing 64%", updated: "May 20 2024 10:28 AM" },
  { title: "Campus PolicyStat Export (Demo stand-in)", type: "PDF", passages: 2312, status: "Ready", updated: "May 19 2024 4:15 PM" },
  { title: "CSU PolicyStat Export (Demo stand-in)", type: "PDF", passages: 3845, status: "Ready", updated: "May 18 2024 2:03 PM" },
  { title: "Senate Resolution 2024-07 (Demo stand-in)", type: "PDF", passages: 156, status: "Needs review", updated: "May 18 2024 9:17 AM" },
  { title: "ATI Accessibility Appendix", type: "DOCX", passages: 92, status: "Ready", updated: "May 17 2024 11:55 AM" },
];

export const draftResolution: DraftResolution = {
  title: "Responsible Use of Generative AI",
  wordCount: 612,
  sections: [
    { number: 1, title: "Purpose", body: "This policy establishes expectations for the responsible and ethical use of generative AI tools in academic and administrative activities at California State University, Bakersfield." },
    { number: 2, title: "Scope", body: "This policy applies to students, faculty, staff, administrators, contractors, and university units that use generative AI systems for teaching, learning, research, communication, or campus operations." },
    { number: 3, title: "Acceptable Use", body: "Generative AI may support university work when its use is lawful, appropriate to the task, consistent with course and workplace requirements, and subject to meaningful human review." },
    { number: 4, title: "Transparency", body: "Users must disclose material use of generative AI when required by an instructor, supervisor, publisher, funding body, or applicable university procedure, and must not represent generated content as independently produced work." },
    { number: 5, title: "Integrity", body: "Generative AI must not be used to evade academic integrity standards, fabricate evidence or citations, impersonate another person, or make consequential decisions without qualified human oversight." },
    { number: 6, title: "Data Protection", body: "Confidential, restricted, personally identifiable, student, personnel, health, or unpublished research data must not be entered into an unapproved generative AI service. Users remain responsible for verifying outputs and protecting university information." },
  ],
};

export const reviewAnalysis: ReviewAnalysis = {
  steps: [
    { label: "Retrieved 18 passages", complete: true },
    { label: "Compared 4 sources", complete: true },
    { label: "Found 2 overlaps", complete: true },
    { label: "Reviewed conflicts", complete: false },
  ],
  coverageLabel: "Existing coverage found",
  confidence: 94,
  findings: [
    { type: "Overlap", source: "Senate Resolution 2024-07 §3 (Demo stand-in)" },
    { type: "Possible duplicate", source: "AI acceptable use guidance (Demo stand-in)" },
    { type: "Conflict", source: "Senate Resolution 2024-07 §3 ↔ Administrative AI Standard §2 (Demo stand-ins)", conflictSlug: "ai-academic-administrative-work" },
  ],
  recommendation: "Static demo result: amend the existing stand-in policy rather than create a duplicate resolution.",
  demoLabel: "Calibrated static demo: AI policy stand-in scenario",
  agentTrace: [
    { agent: "orchestrator", label: "Orchestrator scoped the resolution", status: "complete", detail: "Classified the draft as generative-AI governance and dispatched grounded review tasks." },
    { agent: "retrieval", label: "Retrieval grounded 18 passages", status: "complete", detail: "Ranked passages from four supplied policy sources before any finding was produced.", citations: [{ id: 1, title: "Senate Resolution 2024-07 (Demo stand-in)", section: "§3 • Responsible use" }, { id: 2, title: "Administrative AI Standard (Demo stand-in)", section: "§2 • Data handling" }] },
    { agent: "extractor", label: "Extractors mapped draft obligations", status: "complete", detail: "Parallel extractors compared acceptable use, disclosure, integrity, and data-protection provisions." },
    { agent: "conflict", label: "Conflict detector found a policy tension", status: "warning", detail: "The draft's broad approval wording may conflict with the supplied administrative standard's restricted-data controls.", citations: [{ id: 3, title: "Administrative AI Standard (Demo stand-in)", section: "§2 • Restricted data" }] },
    { agent: "verifier", label: "Verifier checked cited spans", status: "complete", detail: "Every displayed finding is tied to a retrieved source span; no unsupported conclusion was retained." },
    { agent: "escalation", label: "Escalation recommended human review", status: "warning", detail: "Route the data-handling tension to Academic Technology before the resolution advances." },
  ],
};
