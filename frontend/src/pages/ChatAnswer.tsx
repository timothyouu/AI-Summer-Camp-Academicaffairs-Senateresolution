import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { useLocation, useParams } from "react-router-dom";
import { askQuestion, getConversation, submitFeedback, type FeedbackRating } from "../api";
import BackButton from "../components/BackButton";
import { type Answer, type Citation } from "../data/mock";
import { useRole } from "../state/role";

type Tab = "Answer" | "Sources" | "Related";

function BookIcon() {
  return <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 5.5A3.5 3.5 0 0 1 6.5 4H11v16H6.5A3.5 3.5 0 0 0 3 21.5zM21 5.5A3.5 3.5 0 0 0 17.5 4H13v16h4.5a3.5 3.5 0 0 1 3.5 1.5z" /></svg>;
}

function PaperclipIcon() {
  return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m9.5 14.5 6.1-6.1a3 3 0 0 0-4.2-4.2l-7 7a5 5 0 0 0 7.1 7.1l7.2-7.2" /></svg>;
}

function GlobeIcon() {
  return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></svg>;
}

function SendIcon() {
  return <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m3 11 18-8-8 18-2-8zM11 13l4-4" /></svg>;
}

function ActionIcon({ children, label, active = false, onClick }: { children: ReactNode; label: string; active?: boolean; onClick: () => void }) {
  return <button type="button" aria-label={label} aria-pressed={active} onClick={onClick} className={`flex h-9 w-9 items-center justify-center rounded-md hover:bg-cream hover:text-navy ${active ? "bg-blue-50 text-brand-blue" : "text-navy/70"}`}>{children}</button>;
}

function SourceCard({ citation }: { citation: Citation }) {
  const [expanded, setExpanded] = useState(false);
  const sourceUrl = citation.sectionUrl || citation.canonicalUrl;
  return (
    <div className="min-w-0 flex-1 rounded-lg border border-navy/15 bg-[#fbfaff] px-4 py-4 text-left hover:border-brand-blue">
      <button type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} className="block w-full text-left">
        <div className="flex items-center gap-3 text-sm font-semibold text-[#243f89]"><BookIcon /><span className="truncate">{citation.title}</span></div>
        <p className="mt-2 text-sm text-navy/75">{citation.section}</p>
        {expanded && <p className="mt-3 border-t border-navy/10 pt-3 text-xs leading-5 text-inkmuted">Trusted policy excerpt used to ground this answer. Select again to collapse source details.</p>}
      </button>
      {sourceUrl && <a href={sourceUrl} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs font-medium text-brand-blue hover:underline">Open cited section ↗</a>}
    </div>
  );
}

function CitationText({ text, citationIds }: { text: string; citationIds: number[] }) {
  const parts = text.split(/(\[\d+(?:,\s*\d+)*\])/g);
  return <>{parts.map((part, index) => {
    const marker = part.match(/^\[(\d+(?:,\s*\d+)*)\]$/);
    if (!marker) return <span key={`${part}-${index}`}>{part}</span>;
    const availableNumbers = marker[1].split(/,\s*/).filter((number) => citationIds.includes(Number(number)));
    return <span key={`${part}-${index}`} className="ml-1 inline-flex gap-1 align-middle">{availableNumbers.map((number) => <span key={number} className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-navy/5 px-1.5 text-xs">{number}</span>)}</span>;
  })}</>;
}

function AnswerBody({ answer, showQuestion = false }: { answer: Answer; showQuestion?: boolean }) {
  const { role } = useRole();
  const [feedback, setFeedback] = useState<FeedbackRating | null>(null);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [notice, setNotice] = useState("");
  const copyAnswer = async () => {
    try {
      await navigator.clipboard.writeText([answer.heading, ...answer.paragraphs].join("\n\n"));
      setNotice("Answer copied to clipboard.");
    } catch {
      setNotice("Copy is unavailable in this browser. Select the answer text to copy it.");
    }
  };
  const sendFeedback = async (rating: FeedbackRating) => {
    if (submittingFeedback) return;
    setFeedback(rating);
    setSubmittingFeedback(true);
    try {
      const result = await submitFeedback({
        answerId: answer.answerId ?? "local-answer",
        question: answer.question,
        rating,
        role,
        citationsUsed: answer.citations.map((citation) => `${citation.title} • ${citation.section}`),
        provider: answer.mode,
      });
      setNotice(result.submitted ? "Thanks for the feedback." : "Thanks — feedback noted for this demo.");
    } catch {
      setNotice("Thanks — feedback noted for this demo.");
    } finally {
      setSubmittingFeedback(false);
    }
  };
  return (
    <div className={showQuestion ? "border-t border-navy/10 pt-10" : ""}>
      {showQuestion && <div className="ml-auto mb-8 max-w-[592px] rounded-xl bg-[#f2f1f0] px-6 py-5 text-base text-navy">{answer.question}</div>}
      <h1 className="text-[28px] font-bold tracking-[-0.02em] text-navy">{answer.heading}</h1>
      <div className="mt-5 space-y-5 text-[17px] leading-[1.85] text-[#172842]">
        {answer.paragraphs.map((paragraph) => <p key={paragraph}><CitationText text={paragraph} citationIds={answer.citations.map((citation) => citation.id)} /></p>)}
      </div>

      {answer.conflictBanner && <div className="mt-6 flex gap-4 rounded-lg border border-[#e8ad22] bg-amberbg px-5 py-4 text-navy">
        <svg className="mt-0.5 h-6 w-6 shrink-0 text-[#c98a00]" viewBox="0 0 24 24" fill="currentColor"><path d="M11.1 3.5 2.3 19a1.2 1.2 0 0 0 1 1.8h17.4a1.2 1.2 0 0 0 1-1.8L12.9 3.5a1 1 0 0 0-1.8 0ZM13 18h-2v-2h2v2Zm0-4h-2V8h2v6Z" /></svg>
        <div><p className="font-semibold text-[#b87800]">Policy conflict</p><p className="mt-1 text-[15px] leading-7">{answer.conflictBanner.replace("Policy conflict — ", "")}</p></div>
      </div>}

      {answer.citations.length > 0 && <><p className="mt-6 text-xs font-bold tracking-[0.08em] text-navy/70">CITED SOURCES</p><div className="mt-2 flex flex-wrap gap-4">
        {answer.citations.filter((citation, index, all) => all.findIndex((item) => item.title === citation.title && item.section === citation.section) === index).map((citation) => <SourceCard key={`${citation.title}-${citation.section}`} citation={citation} />)}
      </div></>}
      <div className="mt-3 flex justify-end gap-1">
        <span aria-live="polite" className="mr-auto self-center text-xs text-inkmuted">{notice || (feedback ? "Thanks for the feedback." : "")}</span>
        <ActionIcon label="Copy answer" onClick={() => void copyAnswer()}><svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="8" y="5" width="11" height="15" rx="1" /><path d="M5 16H4V3h11v1" /></svg></ActionIcon>
        <ActionIcon label="Helpful" active={feedback === "helpful"} onClick={() => void sendFeedback("helpful")}><svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M7 10v11H3V10zM7 19h10l3-8-1-2h-6l1-6-2-1-5 8" /></svg></ActionIcon>
        <ActionIcon label="Not helpful" active={feedback === "not_helpful"} onClick={() => void sendFeedback("not_helpful")}><svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M7 14V3H3v11zM7 5h10l3 8-1 2h-6l1 6-2 1-5-8" /></svg></ActionIcon>
      </div>
    </div>
  );
}

export default function ChatAnswer() {
  const location = useLocation();
  const { conversationId } = useParams<{ conversationId: string }>();
  const { role } = useRole();
  const submittedQuestion = typeof location.state === "object" && location.state !== null && "question" in location.state && typeof location.state.question === "string" ? location.state.question : null;
  const [activeTab, setActiveTab] = useState<Tab>("Answer");
  const [followUp, setFollowUp] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [attachment, setAttachment] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    setAnswers([]);
    setLoadError("");
    const answerRequest = submittedQuestion !== null
      ? askQuestion(submittedQuestion, role)
      : getConversation(conversationId ?? "service-credit");
    void answerRequest
      .then((answer) => { if (active) setAnswers([answer]); })
      .catch((reason: unknown) => {
        if (active) setLoadError(reason instanceof Error ? reason.message : "Unable to load this conversation.");
      });
    return () => { active = false; };
  }, [conversationId, role, submittedQuestion]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!followUp.trim() || submitting) return;
    setSubmitting(true);
    try {
      const answer = await askQuestion(followUp, role);
      setAnswers((current) => [...current, answer]);
      setLoadError("");
      setFollowUp("");
      setActiveTab("Answer");
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "Unable to send this question.");
    } finally { setSubmitting(false); }
  };
  const attachFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) setAttachment(`${file.name} attached to your next question.`);
  };

  const initialAnswer = answers[0];
  const citations = answers.flatMap((answer) => answer.citations).filter((citation, index, all) => all.findIndex((item) => item.title === citation.title && item.section === citation.section) === index);

  return (
    <section className="mx-auto max-w-[806px] pb-3 text-navy">
      <BackButton fallback="/chats" />
      <div className="ml-auto max-w-[592px] rounded-xl bg-[#f2f1f0] px-6 py-5 text-base">{submittedQuestion ?? initialAnswer?.question ?? (loadError ? "Conversation unavailable" : "Loading conversation…")}</div>

      <div className="mt-7 flex gap-10 border-b border-navy/20">
        {(["Answer", "Sources", "Related"] as Tab[]).map((tab) => <button key={tab} type="button" onClick={() => setActiveTab(tab)} className={`border-b-[3px] px-0.5 pb-3 text-base ${activeTab === tab ? "border-brand-bright font-semibold text-navy" : "border-transparent text-navy/70"}`}>{tab}</button>)}
      </div>

      <div className="pt-9">
        {activeTab === "Answer" && (loadError
          ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-red-800"><p className="font-semibold">Unable to open this conversation</p><p className="mt-1 text-sm">{loadError}</p></div>
          : <div className="space-y-10">{answers.map((answer, index) => <AnswerBody key={`${answer.question}-${index}`} answer={answer} showQuestion={index > 0} />)}</div>)}
        {activeTab === "Sources" && <div><h1 className="text-2xl font-bold">Sources cited in this conversation</h1><p className="mt-2 text-sm text-inkmuted">Select a source to see why it was included.</p><div className="mt-5 flex flex-wrap gap-4">{citations.map((citation) => <SourceCard key={`${citation.title}-${citation.section}`} citation={citation} />)}</div>{citations.length === 0 && <p className="mt-5 rounded-lg border border-navy/15 bg-white p-5 text-inkmuted">No source was cited because this question is outside the calibrated static demo.</p>}</div>}
        {activeTab === "Related" && <div><h1 className="text-2xl font-bold">Related questions</h1><ul className="mt-5 divide-y divide-navy/10 rounded-lg border border-navy/15 bg-white px-5">{["How is prior service credit approved?", "What is the standard tenure timeline?", "Who reviews a faculty tenure file?"].map((question) => <li key={question} className="py-4 text-[15px] text-brand-blue">{question}</li>)}</ul></div>}
      </div>

      <form onSubmit={submit} className="mt-10 rounded-2xl border border-navy/20 bg-white px-5 py-4 shadow-card">
        <label htmlFor="follow-up" className="sr-only">Ask a follow-up</label>
        <input id="follow-up" value={followUp} onChange={(event) => setFollowUp(event.target.value)} placeholder="Ask a follow-up..." className="w-full bg-transparent text-base text-navy outline-none placeholder:text-navy/55" />
        <div className="mt-4 flex items-center gap-6 text-sm text-navy/70">
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" onChange={attachFile} className="sr-only" />
          <button type="button" onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2"><PaperclipIcon />Attach</button>
          <button type="button" onClick={() => setActiveTab("Sources")} className="flex items-center gap-2"><GlobeIcon />Sources</button>
          <span aria-live="polite" className="text-xs text-inkmuted">{attachment}</span>
          <button type="submit" disabled={submitting || !followUp.trim()} aria-label="Send follow-up" className="ml-auto flex h-12 w-12 items-center justify-center rounded-xl bg-brand-blue text-white transition hover:bg-brand-bright disabled:cursor-not-allowed disabled:opacity-50"><SendIcon /></button>
        </div>
      </form>
    </section>
  );
}
