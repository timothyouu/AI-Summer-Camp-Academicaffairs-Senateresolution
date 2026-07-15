import { useState } from "react";
import type { AgentName, AgentTraceStep } from "../api";

const agentStyle: Record<AgentName, { color: string; icon: string }> = {
  orchestrator: { color: "bg-navy text-white", icon: "◈" },
  retrieval: { color: "bg-blue-100 text-brand-blue", icon: "⌕" },
  extractor: { color: "bg-violet-100 text-violet-700", icon: "≡" },
  conflict: { color: "bg-amber-100 text-amber-800", icon: "!" },
  verifier: { color: "bg-emerald-100 text-emerald-800", icon: "✓" },
  escalation: { color: "bg-rose-100 text-rose-700", icon: "↗" },
};

const statusStyle: Record<AgentTraceStep["status"], string> = {
  pending: "bg-slate-100 text-slate-600",
  running: "bg-blue-100 text-brand-blue",
  complete: "bg-emerald-50 text-emerald-800",
  warning: "bg-amberbg text-amber-800",
  failed: "bg-red-50 text-red-700",
};

export default function AgentActivity({ steps }: { steps: AgentTraceStep[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <section aria-label="Agent activity" className="mt-8 overflow-hidden rounded-xl border border-navy/15 bg-white shadow-card">
      <div className="flex items-center justify-between border-b border-navy/10 px-5 py-4">
        <div><h2 className="text-base font-bold text-navy">Agent activity</h2><p className="mt-0.5 text-xs text-inkmuted">Grounded review trace</p></div>
        <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-brand-blue">{steps.length} steps</span>
      </div>
      <ol className="divide-y divide-navy/10">
        {steps.map((step, index) => {
          const expanded = openIndex === index;
          const style = agentStyle[step.agent];
          return <li key={`${step.agent}-${step.label}`}>
            <button type="button" aria-expanded={expanded} onClick={() => setOpenIndex(expanded ? null : index)} className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-cream/70">
              <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold ${style.color}`}>{style.icon}</span>
              <span className="min-w-0 flex-1"><span className="block text-sm font-medium text-navy">{step.label}</span><span className="block text-xs capitalize text-inkmuted">{step.agent}</span></span>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold capitalize ${statusStyle[step.status]}`}>{step.status}</span>
              <span className="text-lg text-inkmuted">{expanded ? "−" : "+"}</span>
            </button>
            {expanded && <div className="bg-cream/60 px-5 pb-4 pl-16 text-sm leading-5 text-inkmuted">
              {step.detail && <p>{step.detail}</p>}
              {step.citations && step.citations.length > 0 && <ul className="mt-3 space-y-1.5 border-l-2 border-brand-blue/30 pl-3 text-xs">
                {step.citations.map((citation) => <li key={`${citation.id}-${citation.title}`}><span className="font-semibold text-navy">{citation.title}</span> · {citation.section}</li>)}
              </ul>}
            </div>}
          </li>;
        })}
      </ol>
    </section>
  );
}
