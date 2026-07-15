import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { createConflict, getConflicts } from "../api";
import type { Conflict, ConflictStatus } from "../data/mock";

const statusStyles: Record<ConflictStatus, string> = {
  Open: "border border-amber-200 bg-amberbg text-amber-900",
  "Under review": "bg-blue-100 text-blue-800",
  Resolved: "bg-green-100 text-green-800",
};

function Chevron() {
  return <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m5 7 5 5 5-5" /></svg>;
}

export default function ConflictLog() {
  const location = useLocation();
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ConflictStatus | "All">(
    location.state?.statusFilter === "Resolved" ? "Resolved" : "Open",
  );
  const [topicFilter, setTopicFilter] = useState("All");
  const [sourceFilter, setSourceFilter] = useState("All");
  const [showAdd, setShowAdd] = useState(false);
  const [newConflict, setNewConflict] = useState({ title: "", sourceA: "", sourceB: "", topic: "" });
  const [error, setError] = useState("");

  useEffect(() => { void getConflicts().then(setConflicts).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load conflicts.")); }, []);
  const topics = [...new Set(conflicts.map((conflict) => conflict.topic))];
  const sources = [...new Set(conflicts.flatMap((conflict) => conflict.sources.split(" ↔ ")))] ;
  const visible = conflicts.filter((conflict) =>
    conflict.topic.toLowerCase().includes(search.toLowerCase())
    && (statusFilter === "All" || conflict.status === statusFilter)
    && (topicFilter === "All" || conflict.topic === topicFilter)
    && (sourceFilter === "All" || conflict.sources.split(" ↔ ").includes(sourceFilter)),
  );
  const exportLog = () => {
    const escapeCsv = (value: string) => `"${value.split('"').join('""')}"`;
    const rows = [["Conflict", "Sources", "Topic", "Status", "Updated"], ...visible.map((conflict) => [conflict.topic, conflict.sources, conflict.owner, conflict.status, conflict.detected])];
    const blob = new Blob([rows.map((row) => row.map(escapeCsv).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "policy-conflict-log.csv";
    link.click();
    URL.revokeObjectURL(url);
  };
  const addConflict = async (event: FormEvent) => {
    event.preventDefault();
    try {
      const conflict = await createConflict(newConflict);
      setConflicts((current) => [conflict, ...current.filter((item) => item.slug !== conflict.slug)]);
      setStatusFilter("Open"); setTopicFilter("All"); setSourceFilter("All"); setSearch(""); setError(""); setShowAdd(false);
      setNewConflict({ title: "", sourceA: "", sourceB: "", topic: "" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add this conflict.");
    }
  };

  return (
    <section className="mx-auto max-w-[1390px] pt-1 text-navy">
      <div className="flex items-start justify-between gap-8">
        <div>
          <h1 className="text-[40px] font-bold leading-tight tracking-tight">Conflict log</h1>
          <p className="mt-3 text-lg text-inkmuted">Track contradictions and overlapping guidance across policy sources.</p>
        </div>
        <div className="flex shrink-0 gap-4 pt-1">
          <button type="button" onClick={exportLog} className="flex items-center gap-3 rounded-lg border border-navy/30 bg-white px-5 py-4 text-lg hover:bg-cream">
            <span className="text-xl">⇧</span> Export log
          </button>
          <button type="button" onClick={() => { setShowAdd(true); setError(""); }} className="flex items-center gap-3 rounded-lg border-2 border-brand-blue bg-white px-5 py-[14px] text-lg font-medium text-brand-blue hover:bg-blue-50">
            <span className="text-3xl font-light leading-4">+</span> Add conflict
          </button>
        </div>
      </div>

      <div className="mt-10 flex gap-6">
        <label className="relative block flex-1">
          <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-inkmuted">⌕</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search conflicts..." className="h-[54px] w-full rounded-lg border border-navy/30 bg-white pl-14 pr-4 text-lg outline-none placeholder:text-inkmuted focus:border-brand-blue" />
        </label>
        <label className="relative block w-52">
          <select aria-label="status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as ConflictStatus | "All")} className="h-[54px] w-full appearance-none rounded-lg border border-navy/30 bg-white px-4 text-lg outline-none focus:border-brand-blue">
            <option value="Open">Status: Open</option><option value="All">All statuses</option><option value="Under review">Status: Under review</option><option value="Resolved">Status: Resolved</option>
          </select>
          <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2"><Chevron /></span>
        </label>
        <label className="relative block w-52">
          <select aria-label="topic" value={topicFilter} onChange={(event) => setTopicFilter(event.target.value)} className="h-[54px] w-full appearance-none rounded-lg border border-navy/30 bg-white px-4 text-lg outline-none focus:border-brand-blue">
            <option value="All">Topic: All</option>{topics.map((topic) => <option key={topic} value={topic}>{topic}</option>)}
          </select>
          <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2"><Chevron /></span>
        </label>
        <label className="relative block w-52">
          <select aria-label="source" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} className="h-[54px] w-full appearance-none rounded-lg border border-navy/30 bg-white px-4 text-lg outline-none focus:border-brand-blue">
            <option value="All">Source: All</option>{sources.map((source) => <option key={source} value={source}>{source}</option>)}
          </select>
            <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2"><Chevron /></span>
        </label>
      </div>

      <div className="mt-8 overflow-x-auto">
        {error && !showAdd && <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-red-800">{error}</p>}
        <table className="w-full min-w-[1050px] text-left">
          <thead className="border-b border-navy/20 text-lg font-semibold">
            <tr><th className="px-4 py-4">Conflict</th><th className="px-4 py-4">Sources</th><th className="px-4 py-4">Owner</th><th className="px-4 py-4">Status</th><th className="px-4 py-4">Updated <span className="ml-1 text-2xl font-normal">↓</span></th><th className="w-10" /></tr>
          </thead>
          <tbody>
            {visible.map((conflict) => {
              const [firstSource, secondSource] = conflict.sources.split(" ↔ ");
              return <tr key={conflict.slug} className="border-b border-navy/15 text-[17px]">
                <td className="px-4 py-5"><div className="flex items-center gap-5"><span className="h-3.5 w-3.5 shrink-0 rounded-full bg-gold" />{conflict.slug.startsWith("local-") ? <span className="font-medium text-navy">{conflict.topic}</span> : <Link to={`/conflicts/${conflict.slug}`} className="font-medium text-brand-blue hover:underline">{conflict.topic}</Link>}</div></td>
                <td className="px-4 py-5 whitespace-nowrap text-slate-700">{firstSource} <span className="mx-2 text-xl text-inkmuted">⟷</span> {secondSource}</td>
                <td className="px-4 py-5 whitespace-nowrap text-slate-700">{conflict.owner}</td>
                <td className="px-4 py-5"><span className={`inline-flex whitespace-nowrap rounded-md px-3 py-1.5 text-base ${statusStyles[conflict.status]}`}>{conflict.status}</span></td>
                <td className="px-4 py-5 whitespace-nowrap text-slate-700">{conflict.detected}</td>
                <td className="py-5 text-center text-2xl tracking-widest text-slate-500">⋮</td>
              </tr>;
            })}
          </tbody>
        </table>
        {!error && visible.length === 0 && <div className="rounded-lg border border-navy/15 bg-white px-6 py-10 text-center"><p className="font-semibold">No conflicts match these filters</p><p className="mt-2 text-sm text-inkmuted">Change a filter or add a conflict to the log.</p></div>}
      </div>
      {showAdd && <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/40 p-6"><form onSubmit={addConflict} role="dialog" aria-modal="true" aria-labelledby="add-conflict-title" className="w-full max-w-xl rounded-xl bg-white p-7 shadow-xl"><div className="flex items-center justify-between"><h2 id="add-conflict-title" className="text-2xl font-bold">Add conflict</h2><button type="button" onClick={() => setShowAdd(false)} aria-label="Close add conflict dialog" className="text-2xl">×</button></div><p className="mt-2 text-sm text-inkmuted">Add a locally tracked conflict for this customer demo.</p><div className="mt-6 grid gap-4"><label className="text-sm font-medium">Conflict title<input value={newConflict.title} onChange={(event) => setNewConflict((current) => ({ ...current, title: event.target.value }))} className="mt-1 block w-full rounded-md border border-navy/25 px-3 py-2 text-base" /></label><label className="text-sm font-medium">First source<input value={newConflict.sourceA} onChange={(event) => setNewConflict((current) => ({ ...current, sourceA: event.target.value }))} className="mt-1 block w-full rounded-md border border-navy/25 px-3 py-2 text-base" /></label><label className="text-sm font-medium">Second source<input value={newConflict.sourceB} onChange={(event) => setNewConflict((current) => ({ ...current, sourceB: event.target.value }))} className="mt-1 block w-full rounded-md border border-navy/25 px-3 py-2 text-base" /></label><label className="text-sm font-medium">Topic<input value={newConflict.topic} onChange={(event) => setNewConflict((current) => ({ ...current, topic: event.target.value }))} className="mt-1 block w-full rounded-md border border-navy/25 px-3 py-2 text-base" /></label></div>{error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}<div className="mt-6 flex justify-end gap-3"><button type="button" onClick={() => setShowAdd(false)} className="rounded-md border border-navy/25 px-5 py-2">Cancel</button><button type="submit" className="rounded-md bg-navy px-5 py-2 text-white">Add conflict</button></div></form></div>}
    </section>
  );
}
