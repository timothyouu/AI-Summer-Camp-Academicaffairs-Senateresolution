import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getConflict, getConflictResolutionNote, getConflicts, resolveConflict } from "../api";
import BackButton from "../components/BackButton";
import type { ConflictDetail, ConflictStatus } from "../data/mock";

type ConflictReviewDetail = ConflictDetail & { status: ConflictStatus };

const statusStyles: Record<ConflictStatus, string> = {
  Open: "border-amber-400 bg-amberbg text-amber-800",
  "Under review": "border-blue-300 bg-blue-100 text-blue-800",
  Resolved: "border-green-300 bg-green-100 text-green-800",
};

export default function ConflictReview() {
  const { slug = "service-credit" } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<ConflictReviewDetail | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [generatedSummary, setGeneratedSummary] = useState<string[] | null>(null);
  const [showOptions, setShowOptions] = useState(false);

  useEffect(() => {
    setDetail(null);
    setError("");
    setGeneratedSummary(null);
    setNote(getConflictResolutionNote(slug));
    void Promise.all([getConflict(slug), getConflicts()]).then(([conflictDetail, conflicts]) => {
      const status = conflicts.find((conflict) => conflict.slug === slug)?.status ?? "Open";
      setDetail({ ...conflictDetail, status });
    }).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Unable to load this conflict.");
    });
  }, [slug]);
  if (error && !detail) return <section className="pt-6 text-red-700">{error}</section>;
  if (!detail) return <section className="pt-6 text-inkmuted">Loading conflict…</section>;

  const resolve = async () => {
    if (!note.trim()) { setError("Add a resolution note before marking this conflict resolved."); return; }
    setError(""); setSaving(true);
    try { await resolveConflict(slug, note); navigate("/conflicts", { state: { statusFilter: "Resolved" } }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to resolve this conflict."); }
    finally { setSaving(false); }
  };
  const regenerateSummary = async () => {
    setRegenerating(true); setError("");
    await new Promise<void>((resolveDelay) => window.setTimeout(resolveDelay, 650));
    setGeneratedSummary([
      ...detail.aiSummary,
      "Regenerated for the current policy comparison. Confirm the controlling authority with Faculty Affairs before applying this guidance.",
    ]);
    setRegenerating(false);
  };
  const sourcePanel = (panel: ConflictDetail["left"], icon: string) => <div className="flex-1">
    <h2 className="flex items-center gap-3 text-xl font-semibold text-[#063b9f]"><span className="text-2xl">{icon}</span>{panel.title}</h2>
    <p className="mt-8 max-w-[530px] text-[18px] leading-8">{panel.beforeHighlight}<mark className="rounded bg-[#ffedba] px-1.5 py-0.5 text-navy">{panel.highlight}</mark>{panel.afterHighlight}</p>
    <p className="mt-6 max-w-[540px] text-[18px] leading-8">{panel.supportingText}</p>
  </div>;

  return (
    <section className="mx-auto max-w-[1255px] pb-2 text-navy">
      <BackButton fallback="/conflicts" />
      <nav className="pt-1 text-lg text-inkmuted"><Link to="/conflicts" className="text-brand-blue hover:underline">Conflict log</Link><span className="mx-4">/</span><span>{detail.title}</span></nav>
      <div className="mt-12 flex items-start justify-between border-b border-navy/20 pb-7">
        <div><div className="flex items-center gap-6"><h1 className="text-[42px] font-bold leading-tight tracking-tight">{detail.title}</h1><span className={`rounded-md border px-5 py-2 text-xl ${statusStyles[detail.status]}`}>{detail.status}</span></div><p className="mt-6 text-lg text-inkmuted">{detail.subtitle}</p></div>
        <div className="relative"><button type="button" onClick={() => setShowOptions((value) => !value)} aria-expanded={showOptions} aria-label="More options" className="rounded-lg border border-navy/25 px-4 py-3 text-2xl leading-none text-slate-600">…</button>{showOptions && <div className="absolute right-0 top-14 z-10 w-52 rounded-lg border border-navy/15 bg-white p-1 text-sm shadow-lg"><button type="button" onClick={() => { void navigator.clipboard.writeText(window.location.href); setShowOptions(false); }} className="block w-full rounded px-3 py-2 text-left hover:bg-cream">Copy conflict link</button><Link to="/conflicts" className="block rounded px-3 py-2 hover:bg-cream">Return to conflict log</Link></div>}</div>
      </div>
      <div className="relative flex gap-20 py-10">
        {sourcePanel(detail.left, "📖")}
        <span className="absolute left-1/2 top-[130px] flex h-12 w-12 -translate-x-1/2 items-center justify-center rounded-full border border-navy/20 bg-white text-lg font-semibold">VS</span>
        {sourcePanel(detail.right, "⚖")}
      </div>
      <article className="rounded-lg border border-navy/20 px-8 py-6">
        <div className="flex items-center justify-between gap-4"><h2 className="text-2xl font-semibold"><span className="mr-4 text-brand-blue">✦</span>AI summary</h2><button type="button" disabled={regenerating} onClick={() => void regenerateSummary()} className="rounded-md border border-brand-blue px-4 py-2 text-brand-blue hover:bg-blue-50 disabled:cursor-wait disabled:opacity-60"><span className="mr-3">✦</span>{regenerating ? "Regenerating…" : "Regenerate summary"}</button></div>
        {regenerating ? <div role="status" className="mt-5 animate-pulse rounded-md bg-blue-50 px-4 py-5 text-brand-blue">Reviewing both policy sources…</div> : <div className="mt-5 space-y-2 text-[17px] leading-7">{(generatedSummary ?? detail.aiSummary).map((line) => <p key={line}>{line}</p>)}</div>}
        <p className="mt-5 italic text-inkmuted">{detail.disclaimer}</p>
      </article>
      <div className="mt-7"><label htmlFor="resolution-note" className="text-lg font-medium">Resolution note</label><textarea id="resolution-note" value={note} aria-invalid={Boolean(error)} onChange={(event) => { setNote(event.target.value); if (error) setError(""); }} placeholder="Describe how this conflict was resolved..." className="mt-2 block h-[58px] w-[76%] resize-y rounded-lg border border-navy/30 px-4 py-3 text-lg outline-none placeholder:text-slate-400 focus:border-brand-blue" />{error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}</div>
      <div className="mt-7 flex justify-end gap-12"><Link to="/reviews" className="self-center text-lg text-brand-blue hover:underline">Cancel</Link><button type="button" disabled={saving || detail.status === "Resolved"} onClick={() => void resolve()} className="rounded-md bg-navy px-9 py-3 text-lg font-medium text-white shadow-sm hover:bg-brand-blue disabled:opacity-60">{detail.status === "Resolved" ? "Resolved" : saving ? "Resolving…" : "Mark resolved"}</button></div>
    </section>
  );
}
