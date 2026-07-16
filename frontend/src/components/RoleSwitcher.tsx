import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { setDemoIdentity } from "../api";
import { signOutCognito } from "../auth/cognito";
import { useRole } from "../state/role";

const cognitoModeEnabled = import.meta.env.VITE_USE_COGNITO === "true";

export default function RoleSwitcher() {
  const { role, setRole } = useRole();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const isChatsHome = location.pathname === "/chats";

  const changeRole = (nextRole: "employee" | "reviewer") => {
    setRole(nextRole);
    setDemoIdentity(nextRole);
    setOpen(false);
    navigate(nextRole === "employee" ? "/chats" : "/reviews");
  };

  if (cognitoModeEnabled) {
    return (
      <div className="flex items-center gap-3">
        <span className="rounded-lg border border-navy/25 bg-white px-4 py-2.5 text-sm font-medium text-navy">
          {role === "employee" ? "Employee / Faculty" : "Policy Reviewer / Writer"}
        </span>
        <button type="button" onClick={signOutCognito} className="rounded-lg border border-navy/25 bg-white px-4 py-2.5 text-sm font-medium text-brand-blue hover:bg-blue-50">
          Sign out
        </button>
      </div>
    );
  }

  if (role === "employee" && isChatsHome) {
    return (
      <button type="button" onClick={() => changeRole("reviewer")} className="rounded-lg border border-navy/25 bg-white px-5 py-3 text-sm font-medium text-brand-blue hover:bg-blue-50">
        Policy Maker view
      </button>
    );
  }

  return (
    <div className="relative">
      <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)} className="flex items-center gap-2 rounded-lg border border-navy/25 bg-white px-4 py-2.5 text-sm font-medium text-navy hover:bg-cream">
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="8" r="3" /><path d="M5 20c0-4 2.5-7 7-7s7 3 7 7" /></svg>
        {role === "employee" ? "Employee / Faculty" : "Policy Reviewer / Writer"}
        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m6 8 4 4 4-4" /></svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-56 rounded-lg border border-navy/15 bg-white p-1.5 shadow-card">
          <button type="button" onClick={() => changeRole("employee")} className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-cream">Employee / Faculty</button>
          <button type="button" onClick={() => changeRole("reviewer")} className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-cream">Policy Reviewer / Writer</button>
        </div>
      )}
    </div>
  );
}
