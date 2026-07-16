import { useEffect, useMemo, useState } from "react";
import { getRegistrySources, type RegistrySource } from "../api";
import BackButton from "../components/BackButton";
import { useRole } from "../state/role";

export default function Catalog() {
  const { role } = useRole();
  const [sources, setSources] = useState<RegistrySource[]>([]);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    void getRegistrySources()
      .then(setSources)
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Unable to load the resource catalog.");
      });
  }, []);

  const visible = useMemo(
    () => sources.filter((source) => (role === "reviewer" || source.status === "active")
      && source.title.toLowerCase().includes(search.toLowerCase())),
    [sources, role, search],
  );

  return (
    <section className="mx-auto max-w-[1100px] pt-1 text-navy">
      <BackButton fallback="/topics" />
      <h1 className="text-[40px] font-bold leading-tight tracking-tight">Resource catalog</h1>
      <p className="mt-2 text-lg text-inkmuted">Every indexed source, with a link back to the canonical document.</p>
      <label className="relative mt-6 block w-[395px]">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search resources…"
          className="h-[50px] w-full rounded-lg border border-navy/25 px-4 text-lg outline-none placeholder:text-inkmuted focus:border-brand-blue"
        />
      </label>
      {error && <p role="alert" className="mt-4 text-red-700">{error}</p>}
      <ul className="mt-6 divide-y divide-navy/10">
        {visible.map((source) => (
          <li key={source.id} className="flex items-center justify-between py-4">
            <div className="min-w-0 flex-1">
              <p className="text-lg font-medium">
                {source.title}
                {source.editionYear !== null && !source.isCurrent && (
                  <span className="ml-3 rounded-full bg-slate-100 px-3 py-0.5 text-xs text-slate-600">{source.editionYear} edition</span>
                )}
              </p>
              <p className="text-sm text-inkmuted">{source.sourceType.toUpperCase()} · {source.passages.toLocaleString()} passages</p>
              {source.owner && <p className="mt-1 text-xs text-inkmuted">Owner: {source.owner}</p>}
              {Object.entries(source.sectionIndex).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  {Object.entries(source.sectionIndex).map(([section, url]) => (
                    <a key={section} href={url} target="_blank" rel="noreferrer" className="text-xs text-brand-blue hover:underline">
                      {section} ↗
                    </a>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-4">
              {role === "reviewer" && (
                <span className={`rounded-full px-3 py-1 text-sm ${source.status === "active" ? "border border-green-300 bg-green-50 text-green-800" : "border border-slate-300 bg-slate-50 text-slate-700"}`}>
                  {source.status}
                </span>
              )}
              {source.canonicalUrl !== "" && (
                <a href={source.canonicalUrl} target="_blank" rel="noreferrer" className="text-brand-blue hover:underline">Open source ↗</a>
              )}
            </div>
          </li>
        ))}
        {visible.length === 0 && !error && (
          <li className="py-8 text-inkmuted">No indexed resources yet — start the backend to load the registry.</li>
        )}
      </ul>
    </section>
  );
}
