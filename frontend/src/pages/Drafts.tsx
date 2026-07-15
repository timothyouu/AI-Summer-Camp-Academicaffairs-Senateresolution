import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getDraftResolution, saveReviewSubmission } from "../api";
import type { DraftResolution, ReviewSubmission } from "../data/mock";

const Icon = ({ name }: { name: "list" | "link" | "comment" | "upload" | "clipboard" | "info" }) => {
  const className = "h-5 w-5";
  if (name === "list") return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4" cy="6" r="1" fill="currentColor" stroke="none"/><circle cx="4" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="4" cy="18" r="1" fill="currentColor" stroke="none"/></svg>;
  if (name === "link") return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m10 13 4-4M7.5 15.5l-1 1a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 5 0M16.5 8.5l1-1a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-5 0"/></svg>;
  if (name === "comment") return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 4h16v13H9l-5 4z"/></svg>;
  if (name === "upload") return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 16V3m0 0L7 8m5-5 5 5M4 14v7h16v-7"/></svg>;
  if (name === "clipboard") return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 5H5v17h14V5h-3M9 2h6v5H9z"/></svg>;
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/></svg>;
};

export default function Drafts() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DraftResolution | null>(null);
  useEffect(() => { void getDraftResolution().then(setDraft); }, []);

  const checkDraft = () => {
    if (draft === null) return;
    const submission: ReviewSubmission = {
      title: draft.title.trim() || "Untitled resolution",
      text: draft.sections.map((section) => `${section.number}. ${section.title}\n${section.body}`).join("\n\n"),
    };
    saveReviewSubmission(submission);
    navigate("/review", { state: { submission } });
  };

  return (
    <section className="-mt-16 text-navy-text">
      <div className="flex h-12 items-center text-sm">
        <Link to="/reviews" className="font-medium text-brand-blue hover:underline">Drafts</Link>
        <span className="mx-4 text-inkmuted">/</span><span className="text-inkmuted">New review</span>
        <span className="ml-auto mr-[310px] flex items-center gap-2 text-inkmuted"><span className="text-lg">✓</span> Saved</span>
      </div>

      <h1 className="mb-4 mt-4 text-center text-[32px] font-bold tracking-tight text-navy">Review a draft policy</h1>
      <div className="mx-auto max-w-[1040px] rounded-xl border border-navy/20 bg-white px-5 py-4 shadow-card">
        <input aria-label="Resolution title" disabled={draft === null} value={draft?.title ?? ""} onChange={(event) => setDraft((value) => value ? { ...value, title: event.target.value } : value)} className="h-12 w-full rounded-lg border border-navy/20 px-4 text-xl text-navy outline-none focus:border-brand-blue disabled:cursor-wait disabled:bg-slate-50" />
        <p className="py-3 text-sm text-inkmuted">Draft resolution <span className="px-2">•</span> {draft?.wordCount ?? 612} words</p>
        <div className="flex h-12 items-center gap-7 border-y border-navy/15 px-3 text-inkmuted">
          <button type="button" className="text-xl font-bold" aria-label="Bold">B</button>
          <button type="button" className="font-serif text-xl font-bold italic" aria-label="Italic">I</button>
          <button type="button" aria-label="Numbered list"><Icon name="list" /></button>
          <button type="button" aria-label="Insert link"><Icon name="link" /></button>
          <button type="button" aria-label="Add comment"><Icon name="comment" /></button>
        </div>
        <div className="space-y-4 px-7 py-5 text-[15px] leading-6">
          {draft?.sections.map((section) => (
            <div key={section.number} className="grid grid-cols-[22px_1fr] gap-3">
              <span className="font-semibold">{section.number}.</span>
              <div><h2 className="font-bold">{section.title}.</h2><p className={section.number === 3 ? "-mx-1 bg-blue-100 px-1" : ""}>{section.body}</p></div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 text-sm font-medium text-brand-blue">
          <button type="button" className="flex items-center gap-2"><Icon name="upload" />Upload PDF</button>
          <span className="h-5 border-l border-navy/20" />
          <button type="button" className="flex items-center gap-2"><Icon name="clipboard" />Replace text</button>
        </div>
      </div>

      <div className="-mx-10 mt-2 flex min-h-[82px] items-center border-t border-navy/15 px-10">
        <p className="flex items-center gap-3 text-sm text-inkmuted"><Icon name="info" />Analysis compares this draft with the University Handbook, CBA, PolicyStat, and Senate resolutions.</p>
        <div className="ml-auto flex gap-4">
          <button type="button" className="rounded-lg border border-brand-blue px-8 py-3 text-sm font-semibold text-brand-blue hover:bg-blue-50">Save draft</button>
          <button type="button" disabled={draft === null} onClick={checkDraft} className="rounded-lg bg-navy px-8 py-3 text-sm font-semibold text-white shadow-card hover:bg-navy-deep disabled:opacity-60">Check for overlap and conflicts</button>
        </div>
      </div>
    </section>
  );
}
