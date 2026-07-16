import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

const conversationId = "service-credit";

function GlobeIcon() {
  return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></svg>;
}

function PaperclipIcon() {
  return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m9.5 14.5 6.1-6.1a3 3 0 0 0-4.2-4.2l-7 7a5 5 0 0 0 7.1 7.1l7.2-7.2" /></svg>;
}

function SendIcon() {
  return <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m3 11 18-8-8 18-2-8zM11 13l4-4" /></svg>;
}

export default function Chats() {
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [sourceScope, setSourceScope] = useState("All trusted sources");
  const [openMenu, setOpenMenu] = useState<"sources" | null>(null);
  const [attachment, setAttachment] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const openConversation = (submittedQuestion = question) => {
    const trimmedQuestion = submittedQuestion.trim();
    navigate(`/chats/${conversationId}`, trimmedQuestion ? { state: { question: trimmedQuestion } } : undefined);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (question.trim()) openConversation();
  };
  const attachFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) setAttachment(`${file.name} attached for this question`);
  };

  return (
    <section className="mx-auto flex max-w-5xl flex-col items-center pt-[132px] text-navy">
      <h1 className="text-center text-[54px] font-bold leading-tight tracking-[-0.035em]">Policy Intelligence</h1>
      <p className="mt-3 text-center text-xl text-inkmuted">Clear answers from trusted university policy.</p>

      <form onSubmit={submit} className="mt-9 w-full max-w-[814px] rounded-2xl border border-navy/25 bg-white px-6 pb-4 pt-5 shadow-card">
        <label htmlFor="policy-question" className="sr-only">Ask a policy question</label>
        <textarea
          id="policy-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && question.trim()) {
              event.preventDefault();
              openConversation();
            }
          }}
          placeholder="Ask a policy question..."
          className="h-[142px] w-full resize-none bg-transparent text-lg text-navy outline-none placeholder:text-inkmuted/80"
        />
        <div className="flex items-center border-t border-navy/15 pt-3 text-sm text-navy">
          <div className="relative">
            <button type="button" aria-expanded={openMenu === "sources"} onClick={() => setOpenMenu(openMenu === "sources" ? null : "sources")} className="flex items-center gap-2 pr-4"><GlobeIcon />Sources <span className="text-lg leading-none">⌄</span></button>
            {openMenu === "sources" && <div className="absolute bottom-9 left-0 z-10 w-56 rounded-lg border border-navy/15 bg-white p-1 shadow-lg">{["All trusted sources", "University Handbook", "Unit 3 CBA"].map((source) => <button key={source} type="button" onClick={() => { setSourceScope(source); setOpenMenu(null); }} className="block w-full rounded px-3 py-2 text-left hover:bg-cream">{source}{sourceScope === source ? " ✓" : ""}</button>)}</div>}
          </div>
          <span className="h-7 border-l border-navy/15" />
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" onChange={attachFile} className="sr-only" />
          <button type="button" onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 px-5"><PaperclipIcon />Attach</button>
          <button type="submit" disabled={!question.trim()} aria-label="Send question" className="ml-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-blue text-white shadow-md transition hover:bg-brand-bright disabled:cursor-not-allowed disabled:opacity-40"><SendIcon /></button>
        </div>
        <p aria-live="polite" className="mt-2 min-h-5 text-xs text-inkmuted">{attachment || `Searching ${sourceScope.toLowerCase()} for guidance.`}</p>
      </form>

    </section>
  );
}
