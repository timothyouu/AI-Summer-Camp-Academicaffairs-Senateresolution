import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTopics } from "../api";
import type { Topic } from "../data/mock";

const icons = ["⌑", "♙", "◷", "▤", "♿", "⚒", "♧", "⌁"];
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
    <label className="mt-7 flex h-[62px] items-center gap-4 rounded-lg border border-navy/25 bg-white px-5 text-inkmuted"><SearchIcon /><span className="sr-only">Search topics or policy titles</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search topics or policy titles..." className="w-full bg-transparent text-base text-navy outline-none placeholder:text-inkmuted" /></label>
    <div className="mt-6">
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-red-800">{error}</p>}
      {results.map((topic, index) => <button type="button" key={topic.slug} onClick={() => navigate(`/topics/${topic.slug}`)} className="grid w-full grid-cols-[55px_302px_minmax(250px,1fr)_105px_24px] items-center gap-4 border-b border-navy/15 px-4 py-[17px] text-left transition hover:bg-blue-50/50">
        <span className="text-3xl leading-none text-navy" aria-hidden="true">{icons[index]}</span><span className="text-xl font-semibold">{topic.name}</span><span className="text-base text-inkmuted">{topic.description}</span><span className="text-base text-inkmuted">{topic.count} policies</span><span className="text-3xl font-light text-inkmuted">›</span>
      </button>)}
      {!error && topics.length > 0 && results.length === 0 && <p className="rounded-lg border border-navy/15 bg-white px-6 py-10 text-center text-inkmuted">No policy topics match this search.</p>}
    </div>
    <button type="button" onClick={() => navigate("/chats")} className="float-right mt-9 flex items-center gap-3 rounded-lg bg-brand-blue px-5 py-3.5 text-base font-medium text-white shadow-card transition hover:bg-brand-bright"><SendIcon />Ask a question</button>
  </section>;
}
