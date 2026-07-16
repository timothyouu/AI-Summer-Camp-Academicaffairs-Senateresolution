import { useEffect, useMemo, useState } from "react";
import { getRegistrySources, type RegistrySource } from "../api";
import BackButton from "../components/BackButton";
import sourcesHero from "../assets/sources-hero.png";
import { useRole } from "../state/role";

const sourceTypeLabels: Record<string, string> = { catalog: "Catalogs", policy: "Policies", handbook: "Handbooks", resolution: "Resolutions" };

function sourceTypeLabel(sourceType: string): string {
  return sourceTypeLabels[sourceType.toLowerCase()] ?? sourceType;
}

export default function Catalog() {
  const { role } = useRole();
  const [sources, setSources] = useState<RegistrySource[]>([]);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [type, setType] = useState("All");

  useEffect(() => {
    void getRegistrySources().then(setSources).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : "Unable to load sources.");
    });
  }, []);

  const visible = useMemo(() => sources.filter((source) => (role === "reviewer" || source.status === "active")
    && source.title.toLowerCase().includes(search.toLowerCase())
    && (type === "All" || sourceTypeLabel(source.sourceType) === type)), [sources, role, search, type]);
  const types = useMemo(() => ["All", ...Array.from(new Set(sources.map((source) => sourceTypeLabel(source.sourceType))))], [sources]);

  return (
    <section className="mx-auto max-w-[1240px] pt-1 text-navy">
      <BackButton fallback="/topics" />
      <div className="relative mt-2 overflow-hidden rounded-3xl bg-navy px-7 py-8 text-white shadow-sm sm:px-10 sm:py-11">
        <img src={sourcesHero} alt="" className="absolute inset-0 h-full w-full object-cover object-right opacity-55" />
        <div className="absolute inset-0 bg-gradient-to-r from-navy via-navy/90 to-navy/30" />
        <div className="relative max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-gold">Academic Affairs</p>
          <h1 className="mt-3 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">Sources for your work</h1>
          <p className="mt-4 max-w-xl text-base leading-7 text-white/85 sm:text-lg">Browse the policies, catalogs, handbooks, and resolutions that inform Academic Affairs decisions.</p>
          <label className="relative mt-7 block max-w-xl"><span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-xl text-slate-500">?</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search sources by title?" className="h-14 w-full rounded-xl bg-white pl-12 pr-4 text-base text-navy shadow-lg outline-none placeholder:text-slate-500 focus:ring-4 focus:ring-white/25" /></label>
        </div>
      </div>
      {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
      <div className="mt-8 flex flex-wrap items-end justify-between gap-4"><div><h2 className="text-2xl font-bold">Explore the collection</h2><p className="mt-1 text-inkmuted">{visible.length} {visible.length === 1 ? "source" : "sources"} available to browse</p></div><div className="flex flex-wrap gap-2" aria-label="Filter sources by type">{types.map((item) => <button key={item} type="button" onClick={() => setType(item)} className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${type === item ? "bg-navy text-white" : "border border-navy/15 bg-white text-navy hover:border-brand-blue hover:text-brand-blue"}`}>{item}</button>)}</div></div>
      <ul className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {visible.map((source) => <li key={source.id} className="group flex min-h-64 flex-col rounded-2xl border border-navy/10 bg-white p-6 shadow-sm transition duration-200 hover:-translate-y-1 hover:border-brand-blue/35 hover:shadow-lg"><div className="flex items-start justify-between gap-4"><span className="rounded-xl bg-blue-50 px-3 py-2 text-xs font-bold uppercase tracking-wider text-brand-blue">{sourceTypeLabel(source.sourceType)}</span>{role === "reviewer" && <span className={`rounded-full px-3 py-1 text-xs font-medium ${source.status === "active" ? "border border-green-300 bg-green-50 text-green-800" : "border border-slate-300 bg-slate-50 text-slate-700"}`}>{source.status}</span>}</div><div className="mt-5 min-w-0 flex-1"><h3 className="text-xl font-bold leading-7 text-navy">{source.title}{source.editionYear !== null && !source.isCurrent && <span className="ml-3 rounded-full bg-slate-100 px-3 py-0.5 text-xs text-slate-600">{source.editionYear} edition</span>}</h3></div><div className="mt-6 flex items-center justify-between gap-3 border-t border-navy/10 pt-4"><span className="text-xs font-medium text-inkmuted">Updated {source.updated}</span>{source.canonicalUrl !== "" && <a href={source.canonicalUrl} target="_blank" rel="noreferrer" className="font-semibold text-brand-blue hover:underline">View source ?</a>}</div></li>)}
        {visible.length === 0 && !error && <li className="col-span-full rounded-2xl border border-dashed border-navy/20 bg-white px-6 py-12 text-center text-inkmuted">No sources match that search. Try a different term or filter.</li>}
      </ul>
    </section>
  );
}
