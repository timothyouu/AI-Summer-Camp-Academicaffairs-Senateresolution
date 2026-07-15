import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { checkResolution, getReviewSubmission, saveReviewSubmission } from "../api";
import AgentActivity from "../components/AgentActivity";
import BackButton from "../components/BackButton";
import DraftAssistant from "../components/DraftAssistant";
import type { ReviewAnalysis, ReviewSubmission } from "../data/mock";

function DocumentIcon() { return <svg className="h-10 w-10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M6 2h8l4 4v16H6zM14 2v5h4M9 12h6M9 16h6"/></svg>; }
function SmallIcon({ kind }: { kind: "upload" | "paste" }) { return kind === "upload" ? <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 16V3m0 0L7 8m5-5 5 5M4 14v7h16v-7"/></svg> : <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M8 5H5v17h14V5h-3M9 2h6v5H9z"/></svg>; }

function FindingIcon({ type }: { type: string }) {
  if (type === "Overlap") return <svg className="h-7 w-7 text-gold" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="12" height="12" rx="2"/><rect x="9" y="9" width="12" height="12" rx="2" fill="white"/></svg>;
  if (type === "Possible duplicate") return <svg className="h-7 w-7 text-[#e9a800]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3 2 21h20zM12 9v5M12 18h.01"/></svg>;
  return <svg className="h-7 w-7 text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/></svg>;
}

export default function ReviewResults() {
  const navigate = useNavigate();
  const location = useLocation();
  const [submission, setSubmission] = useState<ReviewSubmission | null>(null);
  const [analysis, setAnalysis] = useState<ReviewAnalysis | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const routeSubmission = typeof location.state === "object" && location.state !== null && "submission" in location.state
      ? location.state.submission as ReviewSubmission
      : null;
    const nextSubmission = routeSubmission ?? getReviewSubmission();
    setSubmission(nextSubmission);
    setAnalysis(null);
    setError("");
    if (nextSubmission === null) return;
    void checkResolution(nextSubmission.text).then(setAnalysis).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to analyze this draft."));
  }, [location.state]);
  const rerun = () => {
    if (running || submission === null) return;
    setRunning(true);
    setError("");
    setAnalysis((value) => value ? { ...value, steps: value.steps.map((step) => ({ ...step, complete: false })) } : value);
    window.setTimeout(() => { void checkResolution(submission.text).then(setAnalysis).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to analyze this draft.")).finally(() => setRunning(false)); }, 550);
  };

  return (
    <section className="mx-auto -mt-1 max-w-[780px] pb-4 text-navy-text">
      <BackButton fallback="/reviews" />
      <h1 className="text-center text-[32px] font-bold tracking-tight text-navy">Check a resolution</h1>
      <p className="mt-1 text-center text-sm text-inkmuted">Find overlap, duplicate coverage, and policy conflicts before drafting.</p>

      {submission === null && <div className="mt-10 rounded-xl border border-amber-300 bg-amberbg p-8 text-center"><h2 className="text-xl font-bold text-navy">Choose content before running a review</h2><p className="mt-2 text-sm text-inkmuted">The demo will not substitute the default AI sample for a blank review.</p><button type="button" onClick={() => navigate("/reviews")} className="mt-5 rounded-md bg-navy px-5 py-2.5 text-white">Return to review workspace</button></div>}

      {submission !== null && <><div className="mt-10 rounded-xl border border-navy/25 bg-white p-5 shadow-card">
        <div className="flex items-start gap-5">
          <div className="flex h-[76px] w-[68px] shrink-0 items-center justify-center rounded-lg bg-cream text-navy"><DocumentIcon /></div>
          <div className="min-w-0"><h2 className="mt-1 break-words text-lg font-bold text-navy">Draft — {submission.title}</h2><p className="mt-1 max-h-24 max-w-[620px] overflow-auto whitespace-pre-wrap text-sm leading-5 text-inkmuted">{submission.text}</p></div>
        </div>
        <div className="mt-5 flex justify-end gap-4 text-sm font-medium text-brand-blue"><button type="button" onClick={() => navigate("/reviews")} className="flex items-center gap-2"><SmallIcon kind="upload"/>Replace file</button><span className="h-5 border-l border-navy/20"/><button type="button" onClick={() => navigate("/reviews")} className="flex items-center gap-2"><SmallIcon kind="paste"/>Paste text</button></div>
      </div>

      <div className="mt-6 text-center"><button type="button" disabled={running} onClick={rerun} className="rounded-lg bg-navy px-7 py-3 text-sm font-semibold text-white shadow-card hover:bg-navy-deep disabled:opacity-50">{running ? "Analyzing…" : "Analyze resolution"}</button></div>
      {error && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-5 py-3 text-center text-sm text-red-800">{error}</p>}

      <div className="mt-9 grid grid-cols-4">
        {(analysis?.steps ?? []).map((step, index, steps) => <div key={step.label} className="relative text-center">
          {index < steps.length - 1 && <div className="absolute left-[58%] right-[-42%] top-3 h-px bg-navy/40"/>}
          <span className={`relative z-10 mx-auto flex h-6 w-6 items-center justify-center rounded-full border text-xs ${step.complete ? "border-brand-blue bg-brand-blue text-white" : "border-navy/50 bg-white"}`}>{step.complete ? "✓" : ""}</span>
          <p className="mt-2 text-xs text-inkmuted">{step.label}</p>
        </div>)}
      </div>

      {analysis && <AgentActivity steps={analysis.agentTrace} />}

      <div className="mt-12">
        {analysis && <p className="mb-4 rounded-md border border-brand-blue/20 bg-blue-50 px-4 py-2 text-xs font-medium text-brand-blue">{analysis.demoLabel}</p>}
        <div className="flex items-center gap-4"><h2 className="text-lg font-bold text-navy">{analysis?.coverageLabel ?? "Preparing calibrated analysis…"}</h2>{analysis && <span className="rounded-md bg-slate-100 px-3 py-1 text-xs font-medium text-navy">{analysis.confidence}% confidence</span>}</div>
        <p className="mt-3 text-sm leading-6 text-inkmuted">Results are selected from disclosed static demo scenarios, not generated from a live policy index.<br/>Review the findings below to determine next steps.</p>
        <div className="mt-4 border-t border-navy/15">
          {analysis?.findings.map((finding) => {
            const conflict = finding.type === "Conflict";
            const actionable = conflict && Boolean(finding.conflictSlug);
            return <button key={`${finding.type}-${finding.source}`} type="button" disabled={!actionable} onClick={() => conflict && finding.conflictSlug && navigate(`/conflicts/${finding.conflictSlug}`)} className={`grid h-16 w-full grid-cols-[42px_170px_1fr_20px] items-center border-b border-navy/15 px-2 text-left ${actionable ? "hover:bg-cream" : "cursor-default"}`}>
              <FindingIcon type={finding.type}/><span className="text-sm font-semibold text-navy">{finding.type}</span><span className="text-sm text-inkmuted">{finding.source}</span><span className="text-2xl font-light text-inkmuted">{actionable ? "›" : ""}</span>
            </button>;
          })}
          {analysis && analysis.findings.length === 0 && <p className="border-b border-navy/15 px-4 py-6 text-sm text-inkmuted">No findings were generated for this uncalibrated text.</p>}
        </div>
        {analysis && <div className="mt-5 flex items-center gap-4 rounded-lg border border-gold/60 bg-amberbg px-4 py-3 text-sm"><span className="text-xl text-[#e9a800]">♧</span><span>{analysis.recommendation}</span></div>}
      </div>
      {submission !== null && analysis !== null && (
        <DraftAssistant draftText={submission.text} onAdoptRevision={(revisedText) => {
          const next = { ...submission, text: revisedText };
          saveReviewSubmission(next);
          setSubmission(next);
          setAnalysis(null);
          setError("");
          void checkResolution(revisedText)
            .then(setAnalysis)
            .catch((reason: unknown) => {
              setError(reason instanceof Error ? reason.message : "Unable to analyze this draft.");
            });
        }} />
      )}
      </>}
    </section>
  );
}
