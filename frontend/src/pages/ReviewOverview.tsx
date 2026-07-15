import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { clearReviewSubmission, getOpenConflicts, getRecentReviews, saveReviewSubmission } from "../api";
import { type OpenConflict, type RecentReview, type ReviewStatus, type ReviewSubmission } from "../data/mock";

function DocumentIcon({ className = "h-6 w-6" }: { className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M6 2.5h8.5L19 7v14.5H6z" /><path d="M14.5 2.5V7H19M9 12h7M9 16h7" /></svg>;
}

function WarningIcon({ className = "h-7 w-7" }: { className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M12 3 2.5 21h19zM12 9v5M12 18h.01" /></svg>;
}

function Chevron() {
  return <svg className="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m7 4 6 6-6 6" /></svg>;
}

const statusStyles: Record<ReviewStatus, string> = {
  Ready: "text-emerald-700",
  "In progress": "text-brand-blue",
  "Needs attention": "text-amber-600",
};

export default function ReviewOverview() {
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);
  const [reviews, setReviews] = useState<RecentReview[]>([]);
  const [openConflicts, setOpenConflicts] = useState<OpenConflict[]>([]);
  const [draftText, setDraftText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    let active = true;
    void Promise.all([getRecentReviews(), getOpenConflicts()]).then(([reviewRows, conflictRows]) => {
      if (active) {
        setReviews(reviewRows);
        setOpenConflicts(conflictRows);
      }
    });
    return () => { active = false; };
  }, []);

  const startReview = () => {
    const text = draftText.trim();
    if (text.length === 0 && fileName === null) {
      clearReviewSubmission();
      setValidationError("Paste draft text, attach a document, or load a calibrated demo sample.");
      return;
    }

    const firstLine = text.split(/\r?\n/, 1)[0]?.trim();
    const submission: ReviewSubmission = {
      title: fileName ?? firstLine?.slice(0, 100) ?? "Untitled resolution",
      text: text || `Uploaded document: ${fileName}`,
      ...(fileName === null ? {} : { fileName }),
    };
    saveReviewSubmission(submission);
    navigate("/review", { state: { submission } });
  };

  const openRecentReview = (review: RecentReview) => {
    const submission: ReviewSubmission = { title: review.title, text: review.title };
    saveReviewSubmission(submission);
    navigate("/review", { state: { submission } });
  };

  return (
    <section className="mx-auto max-w-[1104px] text-navy">
      <div className="text-center">
        <h1 className="text-[40px] font-bold leading-tight tracking-[-0.025em]">Review workspace</h1>
        <p className="mt-3 text-base text-inkmuted">Check proposed policy, resolve conflicts, and maintain trusted sources.</p>
      </div>

      <div className="mx-auto mt-9 max-w-[865px] rounded-xl border border-navy/25 bg-white px-7 py-6 shadow-card">
        <h2 className="text-lg font-semibold">What would you like to review?</h2>
        <textarea value={draftText} onChange={(event) => { setDraftText(event.target.value); setValidationError(""); }} aria-invalid={Boolean(validationError)} aria-label="Draft resolution to review" placeholder="Paste a draft resolution or ask about existing coverage..." className="mt-4 h-[124px] w-full resize-none rounded-lg border border-navy/25 px-4 py-3 text-sm text-navy outline-none placeholder:text-inkmuted focus:border-brand-blue focus:ring-1 focus:ring-brand-blue" />
        <div className="mt-2 flex items-center gap-3 text-xs"><span className="text-inkmuted">Calibrated static samples:</span><button type="button" onClick={() => { setDraftText("Proposed FERP appointment policy: participants may work up to 960 hours each fiscal year, including summer employment."); setFileName(null); setValidationError(""); }} className="font-medium text-brand-blue hover:underline">Load FERP sample</button><button type="button" onClick={() => { setDraftText("Proposed resolution on responsible use of generative AI tools in academic and administrative work."); setFileName(null); setValidationError(""); }} className="font-medium text-brand-blue hover:underline">Load AI sample</button></div>
        <div className="mt-4 flex items-center gap-8">
          <input ref={fileInput} type="file" onChange={(event) => { setFileName(event.target.files?.[0]?.name ?? null); setValidationError(""); }} className="hidden" aria-label="Attach document" />
          <button type="button" onClick={() => fileInput.current?.click()} className="flex items-center gap-2 text-sm font-medium hover:text-brand-blue">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m9 12.5 5.7-5.7a3 3 0 1 1 4.2 4.2l-8.5 8.5a5 5 0 0 1-7.1-7.1l8.2-8.2" /><path d="m7 14.5 7.5-7.5" /></svg>
            {fileName ?? "Attach document"}
          </button>
          <button type="button" className="flex items-center gap-2 text-sm font-medium hover:text-brand-blue">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></svg>
            Sources
            <svg className="ml-1 h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
          </button>
          <button type="button" onClick={startReview} disabled={!draftText.trim() && fileName === null} className="ml-auto flex items-center gap-3 rounded-lg bg-navy px-5 py-3 text-sm font-medium text-white shadow-card transition-colors hover:bg-navy-deep disabled:cursor-not-allowed disabled:opacity-40">
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m21 3-7.5 18-3.8-7.2L3 10.5zM9.7 13.8 21 3" /></svg>
            Start review
          </button>
        </div>
        {validationError && <p role="alert" className="mt-3 text-sm text-red-700">{validationError}</p>}
      </div>

      <div className="mx-auto mt-9 flex max-w-[748px] justify-between gap-5">
        <QuickAction label="Check a new resolution" onClick={() => navigate("/drafts")} icon={<DocumentIcon />} />
        <QuickAction label="Open conflict log" onClick={() => navigate("/conflicts")} icon={<WarningIcon />} />
        <QuickAction label="Upload a source" onClick={() => navigate("/sources")} icon={<svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M12 16V3M7 8l5-5 5 5M4 14v7h16v-7" /></svg>} />
      </div>

      <div className="mt-14 grid grid-cols-2 gap-[70px]">
        <DashboardList title="Recent reviews" onViewAll={() => navigate("/review")}>
          {reviews.map((review) => (
            <button key={review.title} type="button" onClick={() => openRecentReview(review)} className="flex h-[74px] w-full items-center gap-4 border-b border-navy/10 px-5 text-left last:border-b-0 hover:bg-cream/60">
              <DocumentIcon className="h-6 w-6 shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{review.title}</span>
                <span className="mt-0.5 block text-xs text-inkmuted">Draft resolution&nbsp; • &nbsp;{review.updated}</span>
              </span>
              <span className={`whitespace-nowrap text-xs font-medium ${statusStyles[review.status]}`}>{review.status}</span>
              <Chevron />
            </button>
          ))}
        </DashboardList>

        <DashboardList title="Open conflicts" onViewAll={() => navigate("/conflicts")}>
          {openConflicts.map((conflict) => (
            <button key={conflict.slug} type="button" onClick={() => navigate(`/conflicts/${conflict.slug}`)} className="flex h-[74px] w-full items-center gap-4 border-b border-navy/10 px-5 text-left last:border-b-0 hover:bg-amberbg/50">
              <WarningIcon className="h-7 w-7 shrink-0 text-amber-500" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{conflict.title}</span>
                <span className="mt-0.5 block text-xs text-inkmuted">{conflict.overlappingSources} overlapping sources</span>
              </span>
              <span className="flex h-6 min-w-6 items-center justify-center rounded-md bg-amber-200 px-1.5 text-xs font-medium">{conflict.overlappingSources}</span>
              <Chevron />
            </button>
          ))}
        </DashboardList>
      </div>

      <p className="mt-14 text-center text-xs text-inkmuted">6 source records indexed&nbsp;&nbsp; • &nbsp;&nbsp;Last synced 8 minutes ago</p>
    </section>
  );
}

function QuickAction({ label, icon, onClick }: { label: string; icon: React.ReactNode; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="flex h-14 min-w-[220px] items-center justify-center gap-4 rounded-lg border border-navy/25 bg-white px-5 text-sm font-medium shadow-card hover:border-brand-blue hover:text-brand-blue">{icon}{label}</button>;
}

function DashboardList({ title, onViewAll, children }: { title: string; onViewAll: () => void; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-4 flex items-center justify-between px-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button type="button" onClick={onViewAll} className="text-sm font-medium text-brand-blue hover:underline">View all</button>
      </div>
      <div className="overflow-hidden rounded border border-navy/15 bg-white shadow-card">{children}</div>
    </div>
  );
}
