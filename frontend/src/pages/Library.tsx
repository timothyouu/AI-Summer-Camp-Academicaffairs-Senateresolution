import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getLibrary } from "../api";
import type { LibraryItem } from "../data/mock";

const groups: LibraryItem["group"][] = ["Today", "Yesterday", "Earlier"];

function SearchIcon() {
  return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>;
}

function ItemIcon({ kind }: { kind: LibraryItem["kind"] }) {
  return kind === "Answer"
    ? <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.6 8.6 0 0 1-3.2-.6L4 20l1.5-4A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01" strokeWidth="2.2" /></svg>
    : <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M6 3h8l4 4v14H6zM14 3v5h4M9 13h6M9 17h6" /></svg>;
}

function BookmarkIcon({ filled }: { filled: boolean }) {
  return <svg className="h-5 w-5" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8"><path d="M6 3.5h12v17l-6-3.5-6 3.5z" /></svg>;
}

function TrashIcon() {
  return <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5M14 11v5" /></svg>;
}

export default function Library() {
  const navigate = useNavigate();
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [query, setQuery] = useState("");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { void getLibrary().then(setItems).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load chat history.")); }, []);
  const visibleItems = useMemo(() => items.filter((item) => {
    return item.title.toLowerCase().includes(query.toLowerCase());
  }), [items, query]);
  const openItem = (item: LibraryItem) => navigate(item.kind === "Answer" ? `/chats/${item.id}` : `/topics/${item.id === "accessibility" ? "accessibility" : "tenure-promotion"}`);
  const toggleBookmark = (id: string) => setItems((current) => current.map((item) => item.id === id ? { ...item, bookmarked: !item.bookmarked } : item));
  const removeItem = (id: string) => { setItems((current) => current.filter((item) => item.id !== id)); setOpenMenuId(null); };

  return (
    <section className="mx-auto max-w-[988px] pt-2 text-navy">
      <h1 className="text-[40px] font-bold leading-tight tracking-[-0.025em]">Search chats</h1>
      <p className="mt-1 text-lg text-inkmuted">Find and reopen your past policy conversations.</p>

      <label className="mt-8 flex h-[51px] items-center gap-3 rounded-lg border border-navy/25 bg-white px-4 text-inkmuted">
        <SearchIcon /><span className="sr-only">Search chats</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search chats..." className="w-full bg-transparent text-base text-navy outline-none placeholder:text-inkmuted" />
      </label>

      <div className="mt-7">
        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-red-800">{error}</p>}
        {groups.map((group) => {
          const groupItems = visibleItems.filter((item) => item.group === group);
          if (groupItems.length === 0) return null;
          return <div key={group} className="mb-5"><h2 className="border-b border-navy/15 pb-3 text-base font-semibold text-navy/85">{group}</h2>
            {groupItems.map((item) => <div key={item.id} className="grid min-h-[70px] grid-cols-[48px_minmax(220px,1fr)_96px_138px_100px_34px_28px] items-center gap-4 border-b border-navy/15 px-1">
              <button type="button" aria-label={`Open ${item.title}`} onClick={() => openItem(item)} className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-navy hover:bg-blue-50"><ItemIcon kind={item.kind} /></button>
              <button type="button" onClick={() => openItem(item)} className="min-w-0 text-left text-[15px] font-medium text-navy hover:text-brand-blue">{item.title}</button>
              <span className={`w-fit rounded px-2.5 py-1 text-sm ${item.kind === "Answer" ? "bg-blue-50 text-navy" : "bg-amberbg text-[#a65b00]"}`}>{item.kind}</span>
              <span className="text-sm text-inkmuted">{item.time}</span><span className="text-sm text-inkmuted">{item.sourceCount} {item.sourceCount === 1 ? "source" : "sources"}</span>
              <button type="button" onClick={() => toggleBookmark(item.id)} aria-label={item.bookmarked ? "Remove bookmark" : "Add bookmark"} aria-pressed={item.bookmarked} className={item.bookmarked ? "text-brand-blue" : "text-inkmuted"}><BookmarkIcon filled={item.bookmarked} /></button>
              <span className="relative"><button type="button" onClick={() => setOpenMenuId(openMenuId === item.id ? null : item.id)} aria-label={`More options for ${item.title}`} aria-expanded={openMenuId === item.id} className="text-xl leading-none text-inkmuted">⋮</button>{openMenuId === item.id && <span className="absolute right-0 top-7 z-10 w-40 rounded-lg border border-navy/15 bg-white p-1 shadow-lg"><button type="button" onClick={() => openItem(item)} className="block w-full rounded px-3 py-2 text-left text-sm hover:bg-cream">Open</button><button type="button" onClick={() => removeItem(item.id)} className="block w-full rounded px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50">Remove from history</button></span>}</span>
            </div>)}</div>;
        })}
        {!error && visibleItems.length === 0 && <div className="rounded-lg border border-navy/15 bg-white px-6 py-10 text-center"><p className="font-semibold">{items.length === 0 ? "Your history is clear" : "No matching conversations"}</p><p className="mt-2 text-sm text-inkmuted">{items.length === 0 ? "New policy questions will appear here." : "Try a different search phrase."}</p></div>}
      </div>
      {items.length > 0 && !confirmClear && <button type="button" onClick={() => setConfirmClear(true)} className="mx-auto mt-10 flex items-center gap-2 text-sm font-medium text-brand-blue hover:underline"><TrashIcon />Clear history</button>}
      {confirmClear && <div role="alertdialog" aria-modal="true" aria-labelledby="clear-history-title" className="mx-auto mt-8 max-w-md rounded-lg border border-navy/20 bg-white p-5 text-center shadow-card"><p id="clear-history-title" className="font-semibold">Clear all chat and policy history?</p><p className="mt-1 text-sm text-inkmuted">This demo action cannot be undone.</p><div className="mt-4 flex justify-center gap-3"><button type="button" onClick={() => setConfirmClear(false)} className="rounded-md border border-navy/25 px-4 py-2">Cancel</button><button type="button" onClick={() => { setItems([]); setConfirmClear(false); }} className="rounded-md bg-red-700 px-4 py-2 text-white">Clear history</button></div></div>}
    </section>
  );
}
