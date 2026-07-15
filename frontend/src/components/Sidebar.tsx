import { NavLink } from "react-router-dom";
import type { Role } from "../data/mock";
import Logo from "./Logo";

type IconName = "plus" | "search" | "document" | "topics" | "reviews" | "warning" | "globe" | "bell" | "gear";

interface NavItem {
  label: string;
  to: string;
  icon: IconName;
  showActive?: boolean;
}

const employeeItems: NavItem[] = [
  { label: "New chat", to: "/chats", icon: "plus", showActive: false },
  { label: "Search chats", to: "/library", icon: "search" },
  { label: "Topics", to: "/topics", icon: "topics" },
];

const reviewerItems: NavItem[] = [
  { label: "New chat", to: "/chats", icon: "plus", showActive: false },
  { label: "Search chats", to: "/library", icon: "search" },
  { label: "Drafts", to: "/drafts", icon: "document" },
  { label: "Reviews", to: "/reviews", icon: "reviews" },
  { label: "Conflicts", to: "/conflicts", icon: "warning" },
  { label: "Topics", to: "/topics", icon: "topics" },
  { label: "Sources", to: "/sources", icon: "globe" },
];

function Icon({ name }: { name: IconName }) {
  const common = "h-7 w-7";
  if (name === "plus") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 5v14M5 12h14" /></svg>;
  if (name === "search") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>;
  if (name === "document") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M6 2h9l4 4v16H6zM15 2v5h4M9 12h7M9 16h7" /></svg>;
  if (name === "topics") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M9 3 7 21M17 3l-2 18M3 9h18M2 16h18" /></svg>;
  if (name === "reviews") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 5h8M9 3h6v4H9zM6 5H4v17h16V5h-2M8 14l3 3 5-6" /></svg>;
  if (name === "warning") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3 2.5 21h19zM12 9v5M12 18h.01" /></svg>;
  if (name === "globe") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></svg>;
  if (name === "bell") return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M5 18h14l-2-3V9a5 5 0 0 0-10 0v6zM10 21h4" /></svg>;
  return <svg className={common} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="3" /><path d="m19 13.5 2-1.5-2-1.5-.7-1.8.4-2.5-2.5-.4-1.7-1.3L13.5 2 12 4l-1.5-2-1 2.5-1.7 1.3-2.5.4.4 2.5L5 10.5 3 12l2 1.5.7 1.8-.4 2.5 2.5.4 1.7 1.3 1 2.5 1.5-2 1.5 2 1-2.5 1.7-1.3 2.5-.4-.4-2.5z" /></svg>;
}

export default function Sidebar({ role }: { role: Role }) {
  const items = role === "reviewer" ? reviewerItems : employeeItems;
  const navClass = ({ isActive }: { isActive: boolean }) => `relative flex min-h-24 flex-col items-center justify-center gap-1 px-2 text-xs transition-colors ${isActive ? "text-brand-blue before:absolute before:left-0 before:h-10 before:w-0.5 before:bg-brand-blue" : "text-navy hover:text-brand-blue"}`;

  return (
    <aside className="fixed inset-y-0 left-0 z-20 flex w-24 flex-col overflow-y-auto border-r border-navy/10 bg-cream">
      <div className="flex h-24 items-center justify-center"><Logo size={45} /></div>
      <nav className="mt-3" aria-label="Primary navigation">
        {items.map((item, index) => (
          <NavLink key={`${item.label}-${index}`} to={item.to} end={item.to === "/chats"} className={(state) => navClass({ isActive: item.showActive !== false && state.isActive })}>
            <span className={item.icon === "plus" ? "flex h-10 w-10 items-center justify-center rounded-full border border-navy/20" : ""}><Icon name={item.icon} /></span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto mx-5 border-t border-navy/10 py-3">
        <div className="flex flex-col items-center gap-1 py-3 text-xs text-navy"><Icon name="bell" /><span>Notifications</span></div>
        <div className="flex items-center justify-center py-3 text-navy">
          <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-navy text-sm text-white">AB<span className="absolute right-0 top-0 h-3 w-3 rounded-full bg-gold ring-2 ring-cream" /></span>
        </div>
        <div className="flex flex-col items-center gap-1 py-3 text-xs text-navy"><Icon name="gear" /><span>Settings</span></div>
      </div>
    </aside>
  );
}
