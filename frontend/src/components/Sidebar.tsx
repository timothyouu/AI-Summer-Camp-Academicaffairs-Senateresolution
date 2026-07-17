import { Link, NavLink } from "react-router-dom";
import type { Role } from "../data/mock";
import Logo from "./Logo";
import SettingsMenu from "./SettingsMenu";

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
  { label: "Sources", to: "/catalog", icon: "globe" },
];

const reviewerItems: NavItem[] = [
  { label: "New chat", to: "/chats", icon: "plus", showActive: false },
  { label: "Search chats", to: "/library", icon: "search" },
  { label: "Drafts", to: "/drafts", icon: "document" },
  { label: "Reviews", to: "/reviews", icon: "reviews" },
  { label: "Conflicts", to: "/conflicts", icon: "warning" },
  { label: "Topics", to: "/topics", icon: "topics" },
  { label: "Catalog", to: "/catalog", icon: "globe" },
  { label: "Sources", to: "/sources", icon: "globe" },
];

function Icon({ name }: { name: IconName }) {
  const common = "h-6 w-6";
  const props = {
    "aria-hidden": true,
    className: common,
    fill: "none",
    focusable: false,
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.8,
    viewBox: "0 0 24 24",
  };

  if (name === "plus") return <svg {...props}><path d="M12 5v14M5 12h14" /></svg>;
  if (name === "search") return <svg {...props}><circle cx="10.75" cy="10.75" r="5.75" /><path d="m15.1 15.1 4.4 4.4" /></svg>;
  if (name === "document") return <svg {...props}><path d="M6.5 3.5h7l4 4v13h-11zM13.5 3.5v4h4M9 12h6M9 15.5h4.5" /></svg>;
  if (name === "topics") return <svg {...props}><path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v15.5H7.5A2.5 2.5 0 0 0 5 21zM5 5.5v15.5M8.5 7h7M8.5 11h7" /></svg>;
  if (name === "reviews") return <svg {...props}><path d="M8 4.5h8M9 3h6v3H9zM6 5.5H4.5v15h15v-15H18M8.5 13l2.1 2.1 4.9-5" /></svg>;
  if (name === "warning") return <svg {...props}><path d="M12 4 3.8 19h16.4zM12 9v4.5M12 16.5h.01" /></svg>;
  if (name === "globe") return <svg {...props}><circle cx="12" cy="12" r="8.5" /><path d="M3.8 12h16.4M12 3.5c2.15 2.3 3.25 5.13 3.25 8.5S14.15 18.2 12 20.5C9.85 18.2 8.75 15.37 8.75 12S9.85 5.8 12 3.5" /></svg>;
  if (name === "bell") return <svg {...props}><path d="M6.5 10a5.5 5.5 0 0 1 11 0c0 6 2.5 6.5 2.5 7.5h-16c0-1 2.5-1.5 2.5-7.5M10 21h4" /></svg>;
  return <svg {...props}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.45 2.45-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.09h-3.46v-.09A1.7 1.7 0 0 0 9.89 19a1.7 1.7 0 0 0-1.88.34l-.06.06-2.45-2.45.06-.06A1.7 1.7 0 0 0 5.9 15a1.7 1.7 0 0 0-1.56-1.03h-.09v-3.46h.09A1.7 1.7 0 0 0 5.9 9.48a1.7 1.7 0 0 0-.34-1.88L5.5 7.54l2.45-2.45.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.09h3.46v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.45 2.45-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.09v3.46h-.09A1.7 1.7 0 0 0 19.4 15Z" /></svg>;
}

export default function Sidebar({ role }: { role: Role }) {
  const items = role === "reviewer" ? reviewerItems : employeeItems;
  const navClass = ({ isActive }: { isActive: boolean }) => `relative mx-2 flex min-h-16 flex-col items-center justify-center gap-1 rounded-xl px-2 text-xs transition-colors ${isActive ? "bg-brand-blue/10 text-brand-blue before:absolute before:-left-2 before:h-9 before:w-0.5 before:rounded-r-full before:bg-brand-blue" : "text-navy hover:bg-navy/5 hover:text-brand-blue"}`;

  return (
    <aside className="fixed inset-y-0 left-0 z-20 flex w-24 flex-col overflow-hidden border-r border-navy/10 bg-cream">
      <div className="flex h-24 items-center justify-center">
        <Link to="/login" aria-label="Return to role selection"><Logo size={45} /></Link>
      </div>
      <nav className="mt-3 flex min-h-0 flex-1 flex-col justify-center" aria-label="Primary navigation">
        {items.map((item, index) => (
          <NavLink key={`${item.label}-${index}`} to={item.to} end={item.to === "/chats"} className={(state) => navClass({ isActive: item.showActive !== false && state.isActive })}>
            <span className={item.icon === "plus" ? "flex h-10 w-10 items-center justify-center rounded-full bg-navy text-white shadow-sm" : "flex h-9 w-9 items-center justify-center rounded-lg bg-navy/5"}><Icon name={item.icon} /></span>
            <span className="text-center">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="mx-5 shrink-0 border-t border-navy/10 py-3">
        <div className="flex items-center justify-center py-3 text-navy">
          <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-navy text-sm text-white">AB<span className="absolute right-0 top-0 h-3 w-3 rounded-full bg-gold ring-2 ring-cream" /></span>
        </div>
        <SettingsMenu />
      </div>
    </aside>
  );
}
