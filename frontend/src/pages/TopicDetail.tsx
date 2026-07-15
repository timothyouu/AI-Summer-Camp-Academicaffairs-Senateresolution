import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getTopic } from "../api";
import type { TopicDetail as TopicDetailData } from "../data/mock";

const canonicalConversationId = "service-credit";

export default function TopicDetail() {
  const { slug = "tenure-promotion" } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<TopicDetailData | null>(null);
  const [filter, setFilter] = useState("All sources");
  const [error, setError] = useState("");
  useEffect(() => {
    setFilter("All sources");
    setDetail(null);
    setError("");
    void getTopic(slug).then(setDetail).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load this policy topic."));
  }, [slug]);
  const policies = useMemo(() => detail?.policies.filter((policy) => filter === "All sources" || (filter === "Handbook" ? policy.source.includes("Handbook") : policy.source === filter)) ?? [], [detail, filter]);
  const askAboutPolicy = (title: string) => {
    navigate(`/chats/${canonicalConversationId}`, { state: { question: `What does ${title} say?` } });
  };
  if (error) return <section className="mx-auto max-w-[1136px] pt-2"><div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-red-800"><p className="font-semibold">Unable to load this topic</p><p className="mt-1 text-sm">{error}</p></div></section>;
  if (detail === null) return <section className="mx-auto max-w-[1136px] pt-2"><p role="status" className="text-inkmuted">Loading policy topic…</p></section>;
  return <section className="mx-auto max-w-[1136px] pt-2 text-navy">
    <nav aria-label="Breadcrumb" className="flex gap-3 text-lg"><Link to="/topics" className="font-medium text-brand-blue hover:underline">Topics</Link><span>/</span><span className="text-navy/85">{detail.topic.name}</span></nav>
    <h1 className="mt-11 text-[58px] font-bold leading-none tracking-[-0.04em]">{detail.topic.name}</h1>
    <p className="mt-4 text-xl text-inkmuted">{detail.topic.description}</p>
    <div className="mt-7 flex gap-4">{detail.sourceFilters.map((source) => <button type="button" key={source} onClick={() => setFilter(source)} className={`rounded-lg border px-4 py-2 text-base ${filter === source ? "border-brand-blue text-brand-blue" : "border-navy/20 text-navy hover:border-brand-blue"}`}>{source}</button>)}</div>
    <div className="mt-12"><div className="flex items-center gap-4"><span className="text-2xl" aria-hidden="true">💬</span><h2 className="text-xl font-semibold">Common questions</h2></div><div className="mt-3 grid grid-cols-3 gap-4">{detail.commonQuestions.map((question) => <button type="button" key={question} onClick={() => navigate(`/chats/${canonicalConversationId}`, { state: { question } })} className="rounded-lg border border-brand-blue px-5 py-3 text-base font-medium text-brand-blue hover:bg-blue-50">{question}</button>)}</div></div>
    <h2 className="mt-10 text-2xl font-semibold">{detail.topic.count} policies</h2>
    <div className="mt-4"><div className="grid grid-cols-[minmax(370px,1fr)_216px_175px_150px_24px] gap-4 border-b border-navy/25 px-1 pb-2 text-base text-navy/80"><span>Policy</span><span>Source</span><span>Section</span><span>Last updated</span><span /></div>
      {policies.map((policy) => <div key={policy.title} className="grid min-h-[67px] grid-cols-[minmax(370px,1fr)_216px_175px_150px_24px] items-center gap-4 border-b border-navy/15 px-1 text-base"><span className="flex items-center gap-3"><button type="button" onClick={() => askAboutPolicy(policy.title)} className="text-left text-lg text-brand-blue hover:underline">{policy.title}</button>{policy.badge && <span className="shrink-0 rounded border border-amber-500 px-2 py-0.5 text-sm text-amber-600">{policy.badge}</span>}</span><span>{policy.source}</span><span>{policy.section}</span><span>{policy.updated}</span><button type="button" aria-label={`Ask about ${policy.title}`} onClick={() => askAboutPolicy(policy.title)} className="text-3xl leading-none text-brand-blue">›</button></div>)}
    </div>
    <button type="button" onClick={() => setFilter("All sources")} className="mx-auto mt-4 block text-base font-medium text-brand-blue hover:underline">View all {detail.topic.count} policies</button>
  </section>;
}
