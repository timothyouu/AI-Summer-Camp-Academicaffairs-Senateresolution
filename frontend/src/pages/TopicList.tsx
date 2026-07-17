import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getTopics } from "../api";
import type { Topic } from "../data/mock";

function TopicIcon({ slug }: { slug: string }) {
  const shared = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const paths: Record<string, React.ReactNode> = {
    "tenure-promotion": <><path d="m15.477 12.89 1.515 8.526a.5.5 0 0 1-.81.47l-3.58-2.687a1 1 0 0 0-1.197 0l-3.586 2.686a.5.5 0 0 1-.81-.469l1.514-8.526" /><circle cx="12" cy="8" r="6" /></>,
    "hiring-appointments": <><path d="M2 21a8 8 0 0 1 13.292-6" /><circle cx="10" cy="8" r="5" /><path d="M19 16v6M22 19h-6" /></>,
    workload: <><path d="m12 14 4-4" /><path d="M3.34 19a10 10 0 1 1 17.32 0" /></>,
    curriculum: <><path d="M12 21V7" /><path d="m16 12 2 2 4-4" /><path d="M22 6V4a1 1 0 0 0-1-1h-5a4 4 0 0 0-4 4 4 4 0 0 0-4-4H3a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h6a3 3 0 0 1 3 3 3 3 0 0 1 3-3h6a1 1 0 0 0 1-1v-1.3" /></>,
    accessibility: <><circle cx="16" cy="4" r="1" /><path d="m18 19 1-7-6 1" /><path d="m5 8 3-3 5.5 3-2.36 3.5" /><path d="M4.24 14.5a5 5 0 0 0 6.88 6M13.76 17.5a5 5 0 0 0-6.88-6" /></>,
    "senate-procedures": <><path d="M10 18v-7M14 18v-7M18 18v-7M6 18v-7M3 22h18" /><path d="M11.119 2.205a2 2 0 0 1 1.762 0l7.84 3.846A.5.5 0 0 1 20.5 7h-17a.5.5 0 0 1-.22-.949z" /></>,
    committees: <><path d="M18 21a8 8 0 0 0-16 0" /><circle cx="10" cy="8" r="5" /><path d="M22 20c0-3.37-2-6.5-4-8a5 5 0 0 0-.45-8.3" /></>,
    "cba-labor": <><path d="M12 3v18M7 21h10" /><path d="m19 8 3 8a5 5 0 0 1-6 0zV7M3 7h1a17 17 0 0 0 8-2 17 17 0 0 0 8 2h1M5 8l-3 8a5 5 0 0 0 6 0zV7" /></>,
  };

  return <svg className="h-7 w-7" viewBox="0 0 24 24" aria-hidden="true" {...shared}>{paths[slug]}</svg>;
}
function SearchIcon() { return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>; }
function SendIcon() { return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m3 11 18-8-8 18-2-8zM11 13l4-4" /></svg>; }

export default function TopicList() {
  const navigate = useNavigate();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { void getTopics().then(setTopics).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load policy topics.")); }, []);
  const results = useMemo(() => topics.filter((topic) => `${topic.name} ${topic.description}`.toLowerCase().includes(query.toLowerCase())), [query, topics]);
  return <section className="mx-auto max-w-[1168px] pt-2 text-navy">
    <h1 className="text-[42px] font-bold leading-tight tracking-[-0.025em]">Browse policy by topic</h1>
    <p className="mt-3 text-base text-inkmuted">Explore trusted guidance from the University Handbook, CBA, and PolicyStat.</p>
    <Link to="/catalog" className="mt-2 inline-block text-brand-blue hover:underline">Browse the full resource catalog →</Link>
    <label className="mt-7 flex h-[62px] items-center gap-4 rounded-lg border border-navy/25 bg-white px-5 text-inkmuted"><SearchIcon /><span className="sr-only">Search topics or policy titles</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search topics or policy titles..." className="w-full bg-transparent text-base text-navy outline-none placeholder:text-inkmuted" /></label>
    <div className="mt-6">
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-red-800">{error}</p>}
      {results.map((topic) => <button type="button" key={topic.slug} onClick={() => navigate(`/topics/${topic.slug}`)} className="grid w-full grid-cols-[55px_302px_minmax(250px,1fr)_105px_24px] items-center gap-4 border-b border-navy/15 px-4 py-[17px] text-left transition hover:bg-blue-50/50">
        <span className="text-navy"><TopicIcon slug={topic.slug} /></span><span className="text-xl font-semibold">{topic.name}</span><span className="text-base text-inkmuted">{topic.description}</span><span className="text-base text-inkmuted">{topic.count} policies</span><span className="text-3xl font-light text-inkmuted">›</span>
      </button>)}
      {!error && topics.length > 0 && results.length === 0 && <p className="rounded-lg border border-navy/15 bg-white px-6 py-10 text-center text-inkmuted">No policy topics match this search.</p>}
    </div>
    <button type="button" onClick={() => navigate("/chats")} className="float-right mt-9 flex items-center gap-3 rounded-lg bg-brand-blue px-5 py-3.5 text-base font-medium text-white shadow-card transition hover:bg-brand-bright"><SendIcon />Ask a question</button>
  </section>;
}
