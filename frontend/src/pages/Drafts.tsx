import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  compareDraftVersions,
  getDraftResolution,
  getDraftVersions,
  listDrafts,
  restoreDraftVersion,
  reviseDraft,
  saveDraftVersion,
  saveReviewSubmission,
  type DraftComparisonRecord,
  type DraftStatus,
  type DraftSummaryRecord,
  type DraftVersionRecord,
} from "../api";
import type { ReviewSubmission } from "../data/mock";

const statusLabel: Record<DraftStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  archived: "Archived",
};

const templateText = async (): Promise<{ title: string; text: string }> => {
  const template = await getDraftResolution();
  return {
    title: template.title,
    text: template.sections.map((section) => `${section.number}. ${section.title}\n${section.body}`).join("\n\n"),
  };
};

export default function Drafts() {
  const navigate = useNavigate();
  const [drafts, setDrafts] = useState<DraftSummaryRecord[]>([]);
  const [draftId, setDraftId] = useState<string | undefined>();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState<DraftStatus>("draft");
  const [versions, setVersions] = useState<DraftVersionRecord[]>([]);
  const [instruction, setInstruction] = useState("");
  const [comparison, setComparison] = useState<DraftComparisonRecord | null>(null);
  const [compareFrom, setCompareFrom] = useState(1);
  const [compareTo, setCompareTo] = useState(1);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const wordCount = useMemo(() => text.trim().split(/\s+/).filter(Boolean).length, [text]);

  const loadVersions = async (id: string): Promise<DraftVersionRecord[]> => {
    const loaded = await getDraftVersions(id);
    setVersions(loaded);
    if (loaded.length > 0) {
      setCompareFrom(Math.max(1, loaded.length - 1));
      setCompareTo(loaded.length);
    }
    return loaded;
  };

  const openDraft = async (draft: DraftSummaryRecord): Promise<void> => {
    setDraftId(draft.draftId);
    setTitle(draft.title);
    setText(draft.latestText);
    setStatus(draft.status);
    setComparison(null);
    setInstruction("");
    await loadVersions(draft.draftId);
  };

  const refreshDrafts = async (selectedId?: string): Promise<void> => {
    const loaded = await listDrafts();
    setDrafts(loaded);
    const selected = selectedId ? loaded.find((draft) => draft.draftId === selectedId) : undefined;
    if (selected) {
      setTitle(selected.title);
      setStatus(selected.status);
    }
  };

  useEffect(() => {
    let active = true;
    void listDrafts().then(async (loaded) => {
      if (!active) return;
      setDrafts(loaded);
      if (loaded.length > 0) {
        await openDraft(loaded[0]);
      } else {
        const template = await templateText();
        if (active) {
          setTitle(template.title);
          setText(template.text);
        }
      }
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "Unable to load drafts.");
    });
    return () => { active = false; };
  }, []);

  const newDraft = (): void => {
    setDraftId(undefined);
    setTitle("Untitled resolution");
    setText("");
    setStatus("draft");
    setVersions([]);
    setInstruction("");
    setComparison(null);
    setNotice("New draft ready.");
    setError("");
  };

  const save = async (): Promise<DraftVersionRecord | null> => {
    if (!title.trim() || !text.trim()) {
      setError("Add a title and draft text before saving.");
      return null;
    }
    setWorking(true);
    setError("");
    try {
      const saved = await saveDraftVersion({ draftId, title: title.trim(), text, status });
      setDraftId(saved.draftId);
      setNotice(`Saved version ${saved.version}.`);
      await Promise.all([loadVersions(saved.draftId), refreshDrafts(saved.draftId)]);
      return saved;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save this draft.");
      return null;
    } finally {
      setWorking(false);
    }
  };

  const askAi = async (): Promise<void> => {
    if (!title.trim() || !text.trim()) {
      setError("Add a title and draft text before requesting a revision.");
      return;
    }
    setWorking(true);
    setError("");
    try {
      const revision = await reviseDraft(text, draftId, {
        title: title.trim(), instruction: instruction.trim(), status,
      });
      setDraftId(revision.draftId);
      setText(revision.revisedText);
      setInstruction("");
      setNotice(`AI revision saved as version ${revision.version}.`);
      await Promise.all([loadVersions(revision.draftId), refreshDrafts(revision.draftId)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to revise this draft.");
    } finally {
      setWorking(false);
    }
  };

  const restore = async (version: number): Promise<void> => {
    if (!draftId) return;
    setWorking(true);
    setError("");
    try {
      const restored = await restoreDraftVersion(draftId, version);
      setText(restored.text);
      setNotice(`Version ${version} restored as version ${restored.version}.`);
      await Promise.all([loadVersions(draftId), refreshDrafts(draftId)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to restore this version.");
    } finally {
      setWorking(false);
    }
  };

  const compare = async (): Promise<void> => {
    if (!draftId || compareFrom === compareTo) return;
    setWorking(true);
    setError("");
    try {
      setComparison(await compareDraftVersions(draftId, compareFrom, compareTo));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to compare versions.");
    } finally {
      setWorking(false);
    }
  };

  const checkDraft = async (): Promise<void> => {
    const saved = await save();
    if (saved === null) return;
    const submission: ReviewSubmission = { title: title.trim(), text, draftId: saved.draftId };
    saveReviewSubmission(submission);
    navigate("/review", { state: { submission } });
  };

  return (
    <section className="mx-auto max-w-[1380px] text-navy">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h1 className="text-[38px] font-bold tracking-tight">Conversational policy drafting</h1>
          <p className="mt-1 text-inkmuted">Save, resume, revise, compare, and restore conflict-aware policy drafts.</p>
        </div>
        <button type="button" onClick={newDraft} className="rounded-lg border border-brand-blue px-5 py-2.5 text-sm font-semibold text-brand-blue hover:bg-blue-50">New draft</button>
      </div>

      <div className="mt-7 grid grid-cols-[280px_minmax(0,1fr)_310px] gap-6">
        <aside className="rounded-xl border border-navy/15 bg-white p-4 shadow-card">
          <h2 className="font-bold">Saved drafts</h2>
          <div className="mt-3 space-y-2">
            {drafts.map((draft) => (
              <button key={draft.draftId} type="button" onClick={() => { void openDraft(draft); }} className={`w-full rounded-lg border px-3 py-3 text-left ${draft.draftId === draftId ? "border-brand-blue bg-blue-50" : "border-navy/10 hover:bg-cream"}`}>
                <span className="block truncate text-sm font-semibold">{draft.title}</span>
                <span className="mt-1 block text-xs text-inkmuted">v{draft.latestVersion} · {statusLabel[draft.status]}</span>
              </button>
            ))}
            {drafts.length === 0 && <p className="py-6 text-sm text-inkmuted">No saved drafts yet.</p>}
          </div>
        </aside>

        <main className="rounded-xl border border-navy/15 bg-white p-6 shadow-card">
          <div className="flex gap-3">
            <input aria-label="Draft title" value={title} onChange={(event) => setTitle(event.target.value)} className="h-11 min-w-0 flex-1 rounded-lg border border-navy/20 px-4 text-lg font-semibold outline-none focus:border-brand-blue" />
            <select aria-label="Draft status" value={status} onChange={(event) => setStatus(event.target.value as DraftStatus)} className="rounded-lg border border-navy/20 px-3 text-sm">
              {Object.entries(statusLabel).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          <p className="mt-2 text-xs text-inkmuted">{wordCount} words {draftId ? `· ${draftId}` : "· not saved yet"}</p>
          <textarea aria-label="Draft text" value={text} onChange={(event) => setText(event.target.value)} className="mt-4 min-h-[390px] w-full resize-y rounded-lg border border-navy/20 px-4 py-4 text-sm leading-6 outline-none focus:border-brand-blue" />

          <section className="mt-5 rounded-lg border border-brand-blue/20 bg-blue-50/40 p-4">
            <h2 className="font-semibold">Ask the drafting assistant</h2>
            <p className="mt-1 text-xs text-inkmuted">Give a specific instruction. The assistant checks the policy corpus and saves its revision as a new version.</p>
            <textarea aria-label="Revision instruction" value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder="Example: Reconcile this with the CBA while preserving the original intent." className="mt-3 min-h-20 w-full rounded-lg border border-navy/20 bg-white px-3 py-2 text-sm outline-none focus:border-brand-blue" />
            <div className="mt-3 flex flex-wrap gap-2">
              {["Make this less restrictive.", "Reconcile this with the CBA.", "Keep the wording but add an exception."].map((prompt) => (
                <button key={prompt} type="button" onClick={() => setInstruction(prompt)} className="rounded-full border border-brand-blue/30 bg-white px-3 py-1.5 text-xs text-brand-blue hover:bg-blue-50">{prompt}</button>
              ))}
            </div>
          </section>

          {error && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
          {notice && !error && <p aria-live="polite" className="mt-4 text-sm text-brand-blue">{notice}</p>}
          <div className="mt-5 flex justify-end gap-3">
            <button type="button" disabled={working} onClick={() => { void save(); }} className="rounded-lg border border-brand-blue px-5 py-2.5 text-sm font-semibold text-brand-blue disabled:opacity-50">Save version</button>
            <button type="button" disabled={working} onClick={() => { void askAi(); }} className="rounded-lg bg-brand-blue px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{working ? "Working…" : "Revise with AI"}</button>
            <button type="button" disabled={working} onClick={() => { void checkDraft(); }} className="rounded-lg bg-navy px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">Check conflicts</button>
          </div>
        </main>

        <aside className="rounded-xl border border-navy/15 bg-white p-4 shadow-card">
          <h2 className="font-bold">Version history</h2>
          <ol className="mt-3 max-h-[390px] space-y-2 overflow-y-auto">
            {[...versions].reverse().map((version) => (
              <li key={version.version} className="rounded-lg border border-navy/10 p-3">
                <div className="flex items-center justify-between">
                  <button type="button" onClick={() => setText(version.text)} className="text-sm font-semibold text-brand-blue hover:underline">Version {version.version}</button>
                  <span className="text-[11px] text-inkmuted">{new Date(version.createdAt).toLocaleString()}</span>
                </div>
                {version.instruction && <p className="mt-2 text-xs text-inkmuted">Instruction: {version.instruction}</p>}
                {version.restoredFromVersion !== null && <p className="mt-1 text-xs text-inkmuted">Restored from v{version.restoredFromVersion}</p>}
                <button type="button" disabled={working} onClick={() => { void restore(version.version); }} className="mt-2 text-xs font-medium text-brand-blue hover:underline disabled:opacity-50">Restore as new version</button>
              </li>
            ))}
          </ol>

          {versions.length >= 2 && (
            <section className="mt-5 border-t border-navy/10 pt-4">
              <h3 className="text-sm font-semibold">Compare versions</h3>
              <div className="mt-2 flex items-center gap-2">
                <select aria-label="Compare from version" value={compareFrom} onChange={(event) => setCompareFrom(Number(event.target.value))} className="min-w-0 flex-1 rounded border border-navy/20 p-2 text-xs">
                  {versions.map((version) => <option key={version.version} value={version.version}>v{version.version}</option>)}
                </select>
                <span>→</span>
                <select aria-label="Compare to version" value={compareTo} onChange={(event) => setCompareTo(Number(event.target.value))} className="min-w-0 flex-1 rounded border border-navy/20 p-2 text-xs">
                  {versions.map((version) => <option key={version.version} value={version.version}>v{version.version}</option>)}
                </select>
              </div>
              <button type="button" disabled={working || compareFrom === compareTo} onClick={() => { void compare(); }} className="mt-2 w-full rounded border border-brand-blue px-3 py-2 text-xs font-semibold text-brand-blue disabled:opacity-40">Compare</button>
            </section>
          )}
        </aside>
      </div>

      {comparison && (
        <section className="mt-6 rounded-xl border border-navy/15 bg-[#111827] p-5 text-slate-100 shadow-card">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Version {comparison.fromVersion} → {comparison.toVersion}</h2>
            <button type="button" onClick={() => setComparison(null)} className="text-sm text-slate-300 hover:text-white">Close</button>
          </div>
          <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap text-xs leading-5">{comparison.unifiedDiff || "No textual differences."}</pre>
        </section>
      )}
    </section>
  );
}
