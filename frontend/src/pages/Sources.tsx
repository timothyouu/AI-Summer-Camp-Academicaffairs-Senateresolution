import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { getSources, pollIngestionStatus, saveUploadedSource, startSourceUpload } from "../api";
import type { KnowledgeSource, SourceStatus } from "../data/mock";

type Tab = "All sources" | "Processing" | "Needs review";
const statusStyles: Record<SourceStatus, string> = {
  Pending: "border border-slate-300 bg-slate-50 text-slate-700",
  Ingesting: "border border-blue-400 bg-white text-brand-blue",
  Ready: "border border-green-300 bg-green-50 text-green-800",
  Failed: "border border-red-300 bg-red-50 text-red-800",
  "Processing 64%": "border border-blue-400 bg-white text-brand-blue",
  "Needs review": "border border-amber-300 bg-amberbg text-amber-700",
};

function Status({ status }: { status: SourceStatus }) {
  const processing = status === "Processing 64%" || status === "Ingesting";
  return <div><span className={`inline-flex rounded-full px-3 py-1 text-base ${statusStyles[status]}`}>{status}</span>{processing && <span className="mt-2 block h-1 w-40 rounded bg-blue-100"><span className={`block h-1 rounded bg-brand-blue ${status === "Ingesting" ? "w-1/2 animate-pulse" : "w-[64%]"}`} /></span>}</div>;
}

export default function Sources() {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [tab, setTab] = useState<Tab>("All sources");
  const [search, setSearch] = useState("");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    let active = true;
    void getSources().then((nextSources) => { if (active) setSources(nextSources); }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Unable to load knowledge sources."); });
    return () => { active = false; mountedRef.current = false; };
  }, []);
  const visible = useMemo(() => sources.filter((source) => (tab === "All sources" || (tab === "Processing" ? source.status.startsWith("Processing") || source.status === "Pending" || source.status === "Ingesting" : source.status === "Needs review")) && source.title.toLowerCase().includes(search.toLowerCase())), [sources, tab, search]);
  const addFile = async (file: File) => {
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!extension || !["pdf", "md", "txt"].includes(extension)) {
      setError("Choose a PDF, Markdown, or TXT file.");
      return;
    }
    const title = file.name.replace(/\.[^.]+$/, "");
    setError("");
    setFeedback(`${file.name} is being indexed…`);
    const uploaded = await startSourceUpload(file);
    setSources((current) => [uploaded.source, ...current.filter((source) => source.title !== title)]);
    setTab("All sources");
    setSearch("");
    setError("");
    setFeedback(`${file.name} uploaded; waiting for ingestion.`);
    void pollIngestionStatus(uploaded.uploadId, (update) => {
      if (!mountedRef.current) return;
      const nextSource = saveUploadedSource({
        ...uploaded.source,
        passages: update.chunksAdded ?? uploaded.source.passages,
        status: update.status === "pending" ? "Pending" : update.status === "ingesting" ? "Ingesting" : update.status === "ready" ? "Ready" : "Failed",
      });
      setSources((current) => [nextSource, ...current.filter((source) => source.title !== title)]);
      if (update.status === "ready") setFeedback(`${file.name} indexed successfully.`);
      if (update.status === "failed") setError(update.error ?? `${file.name} could not be indexed.`);
    }).catch((reason: unknown) => { if (mountedRef.current) setError(reason instanceof Error ? reason.message : "Unable to check ingestion status."); });
  };
  const chooseFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void addFile(file).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to upload this source."));
    event.target.value = "";
  };
  const dropFile = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) void addFile(file).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to upload this source."));
  };

  return <section className="mx-auto max-w-[1260px] pt-1 text-navy">
    <input ref={fileInputRef} type="file" accept=".pdf,.md,.txt" onChange={chooseFile} className="sr-only" />
    <div className="flex items-start justify-between"><div><h1 className="text-[40px] font-bold leading-tight tracking-tight">Knowledge sources</h1><p className="mt-2 text-lg text-inkmuted">Manage the documents used to answer questions and review policy.</p></div><button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-md bg-navy px-7 py-3 text-xl text-white shadow-sm hover:bg-brand-blue">Upload source</button></div>
    <div onDragOver={(event) => event.preventDefault()} onDrop={dropFile} className="mt-7 flex items-center justify-between rounded-xl border border-dashed border-navy/25 px-9 py-7"><div className="flex items-center gap-7"><span className="text-4xl">⇧</span><div><p className="text-xl font-medium">Drop a PDF, Markdown, or TXT file here</p><p className="mt-1 text-lg text-inkmuted">Uploads are indexed after validation.</p></div></div><button type="button" onClick={() => fileInputRef.current?.click()} className="rounded-lg border border-navy/25 px-8 py-3 text-lg text-brand-blue hover:bg-cream">Choose file</button></div>
    <div aria-live="polite" className="mt-3 min-h-6 text-sm">{error ? <p role="alert" className="text-red-700">{error}</p> : <p className="text-brand-blue">{feedback}</p>}</div>
    <div className="mt-9 flex gap-11 border-b border-navy/15">{(["All sources", "Processing", "Needs review"] as Tab[]).map((item) => <button key={item} type="button" onClick={() => setTab(item)} className={`-mb-px border-b-[3px] px-0 pb-3 text-lg ${tab === item ? "border-brand-blue font-medium text-brand-blue" : "border-transparent text-slate-700 hover:text-brand-blue"}`}>{item}</button>)}</div>
    <label className="relative mt-5 block w-[395px]"><span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-xl text-inkmuted">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search source documents..." className="h-[50px] w-full rounded-lg border border-navy/25 pl-12 pr-4 text-lg outline-none placeholder:text-inkmuted focus:border-brand-blue" /></label>
    <table className="mt-4 w-full text-left"><thead className="border-b border-navy/15 text-base font-medium text-slate-600"><tr><th className="py-4">Document</th><th className="py-4">Type</th><th className="py-4">Coverage</th><th className="py-4">Status</th><th className="py-4">Updated</th><th /></tr></thead><tbody>{visible.map((source) => <tr key={source.title} className="border-b border-navy/12 text-[17px]"><td className="py-4 font-medium"><span className="mr-4 text-xl text-slate-500">▱</span>{source.title}</td><td className="py-4 text-slate-600">{source.type}</td><td className="py-4 text-slate-600">{source.passages.toLocaleString()} passages</td><td className="py-4"><Status status={source.status} /></td><td className="py-4 whitespace-nowrap text-slate-600">{source.updated}</td><td className="py-4 text-center"><button type="button" onClick={() => setFeedback(`${source.title}: ${source.status}. ${source.passages.toLocaleString()} indexed passages.`)} aria-label={`View details for ${source.title}`} className="text-2xl tracking-widest text-slate-600">…</button></td></tr>)}</tbody></table>
    {visible.length === 0 && !error && <div className="rounded-lg border border-navy/15 bg-white px-6 py-10 text-center"><p className="font-semibold">No sources found</p><p className="mt-2 text-sm text-inkmuted">Try another tab or search term, or upload a source.</p></div>}
    <aside className="mt-7 rounded-lg border border-amber-300 bg-amberbg/60 px-7 py-4 text-lg"><span className="mr-5 text-2xl">💡</span>New uploads should be reviewed before becoming authoritative.</aside>
  </section>;
}
