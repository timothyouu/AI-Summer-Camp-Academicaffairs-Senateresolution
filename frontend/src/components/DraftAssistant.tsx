import { useEffect, useState } from "react";
import { getDraftVersions, reviseDraft, type DraftRevision, type DraftVersionRecord } from "../api";
import { useRole } from "../state/role";

interface DraftAssistantProps {
  draftTitle?: string;
  draftId?: string;
  draftText: string;
  onAdoptRevision: (revisedText: string) => void;
}

export default function DraftAssistant({ draftTitle = "Policy revision", draftId, draftText, onAdoptRevision }: DraftAssistantProps) {
  const { role } = useRole();
  const [revision, setRevision] = useState<DraftRevision | null>(null);
  const [versions, setVersions] = useState<DraftVersionRecord[]>([]);
  const [instruction, setInstruction] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!draftId) return;
    void getDraftVersions(draftId).then(setVersions).catch(() => {
      setError("The draft loaded, but its version history is temporarily unavailable.");
    });
  }, [draftId]);

  if (role !== "reviewer") return null;

  const suggest = async (): Promise<void> => {
    setWorking(true);
    setError("");
    try {
      const next = await reviseDraft(revision?.revisedText ?? draftText, revision?.draftId ?? draftId, {
        title: draftTitle,
        instruction: instruction.trim(),
      });
      setRevision(next);
      setInstruction("");
      setVersions(await getDraftVersions(next.draftId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to draft a revision.");
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="mt-10 rounded-xl border border-navy/20 bg-white p-6 shadow-card">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-bold text-navy">Draft with AI</h2>
          <p className="mt-1 text-sm text-inkmuted">Describe the change you want. Every AI revision is saved and can be reopened from Drafts.</p>
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
      <label className="mt-5 block text-sm font-semibold text-navy" htmlFor="draft-assistant-instruction">
        Revision instruction
      </label>
      <textarea
        id="draft-assistant-instruction"
        rows={3}
        value={instruction}
        onChange={(event) => setInstruction(event.target.value)}
        placeholder="For example: make the approval timeline explicit and use more concise language."
        className="mt-2 w-full rounded-lg border border-navy/20 px-3 py-2 text-sm text-navy-text outline-none focus:border-brand-blue"
      />
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
          {versions.length > 0 && (
            <ol className="mt-5 border-t border-navy/10 pt-3 text-xs text-inkmuted">
              {[...versions].reverse().map((item) => (
                <li key={`${item.draftId}-${item.version}`} className="py-1">
                  v{item.version} — {item.instruction || "Initial revision"} · {new Date(item.createdAt).toLocaleString()}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
