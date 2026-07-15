import { useState } from "react";
import { reviseDraft, type DraftRevision } from "../api";
import { useRole } from "../state/role";

interface DraftAssistantProps {
  draftText: string;
  onAdoptRevision: (revisedText: string) => void;
}

export default function DraftAssistant({ draftText, onAdoptRevision }: DraftAssistantProps) {
  const { role } = useRole();
  const [revision, setRevision] = useState<DraftRevision | null>(null);
  const [history, setHistory] = useState<DraftRevision[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  if (role !== "reviewer") return null;

  const suggest = async (): Promise<void> => {
    setWorking(true);
    setError("");
    try {
      const next = await reviseDraft(draftText, revision?.draftId);
      setRevision(next);
      setHistory((current) => [next, ...current]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to draft a revision.");
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="mt-10 rounded-xl border border-navy/20 bg-white p-6 shadow-card">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-navy">Draft with AI</h2>
          <p className="mt-1 text-sm text-inkmuted">Iterate on this draft against the conflicting policies until it comes back clean.</p>
        </div>
        <button
          type="button"
          disabled={working}
          onClick={() => { void suggest(); }}
          className="rounded-lg bg-navy px-5 py-2.5 text-sm font-semibold text-white hover:bg-navy-deep disabled:opacity-50"
        >
          {working ? "Revising…" : revision === null ? "Suggest a revision" : "Revise again"}
        </button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      {revision && (
        <div className="mt-5">
          <p className="rounded-md border border-brand-blue/20 bg-blue-50 px-4 py-2 text-xs font-medium text-brand-blue">
            Version {revision.version} — {revision.findings.length} finding(s) referenced
          </p>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-navy-text">{revision.revisedText}</p>
          <p className="mt-3 text-sm text-inkmuted"><span className="font-semibold text-navy">Why: </span>{revision.rationale}</p>
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              onClick={() => onAdoptRevision(revision.revisedText)}
              className="rounded-md border border-navy/25 px-4 py-2 text-sm text-brand-blue hover:bg-cream"
            >
              Adopt revision and re-check
            </button>
          </div>
          {history.length > 1 && (
            <ol className="mt-5 border-t border-navy/10 pt-3 text-xs text-inkmuted">
              {history.map((item) => (
                <li key={`${item.draftId}-${item.version}`} className="py-1">
                  v{item.version} — {item.findings.length} finding(s) · {item.recommendation.slice(0, 90)}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
