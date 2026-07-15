import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api";
import { startCognitoLogin } from "../auth/cognito";
import Logo from "../components/Logo";
import type { Role } from "../data/mock";
import { useRole } from "../state/role";

const cognitoModeEnabled = import.meta.env.VITE_USE_COGNITO === "true";

function GraduationCapIcon() {
  return (
    <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="h-11 w-11 shrink-0">
      <path d="m4 18 20-11 20 11-20 11L4 18Z" />
      <path d="M12 23v10c5.8 6 18.2 6 24 0V23M42 20v12" />
    </svg>
  );
}

function PolicyDocumentIcon() {
  return (
    <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="h-11 w-11 shrink-0">
      <path d="M10 5h18l10 10v27H10V5Z" />
      <path d="M28 5v11h10M20 30l4 4 8-9" />
      <circle cx="31" cy="32" r="10" fill="#f7f5f1" />
      <path d="m26.5 32 3 3 5.5-6" />
    </svg>
  );
}

function HelpIcon() {
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true" className="h-9 w-9">
      <circle cx="16" cy="16" r="14" />
      <path d="M12.7 12.2a3.6 3.6 0 1 1 5.6 3c-1.5 1-2.4 1.6-2.4 3.5M16 23h.01" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AccessibilityIcon() {
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="h-9 w-9">
      <circle cx="16" cy="16" r="14" />
      <circle cx="16" cy="9.2" r="1.5" />
      <path d="M9 13.5h14M16 11v13M16 16l-4.5 8M16 16l4.5 8" />
    </svg>
  );
}

export default function Login() {
  const { role, setRole } = useRole();
  const [selected, setSelected] = useState<Role>(role);
  const [isContinuing, setIsContinuing] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const continueToWorkspace = async (nextRole = selected) => {
    if (isContinuing) return;
    setIsContinuing(true);
    setError("");
    try {
      const result = await login(nextRole);
      setRole(result.role);
      navigate(result.role === "employee" ? "/chats" : "/reviews");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to open the selected workspace.");
      setIsContinuing(false);
    }
  };

  const chooseRole = (nextRole: Role) => {
    if (nextRole === selected) {
      void continueToWorkspace(nextRole);
      return;
    }
    setSelected(nextRole);
  };

  const optionClass = (option: Role) => `flex min-h-[100px] flex-1 items-center justify-center gap-5 rounded-[20px] border px-5 py-6 text-left text-[20px] font-medium tracking-[-0.025em] transition-colors sm:px-8 ${
    selected === option
      ? "border-navy/45 bg-slate-100/75 shadow-[inset_0_0_0_1px_rgba(22,48,94,0.04)]"
      : "border-transparent hover:bg-navy/[0.035]"
  }`;

  return (
    <main className="flex min-h-screen flex-col bg-cream px-5 py-8 text-navy sm:px-11 sm:py-9">
      <header className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Logo size={44} />
          <span className="text-[23px] font-semibold tracking-[-0.04em] sm:text-[27px]">Policy Intelligence</span>
        </div>
        <nav aria-label="Utility links" className="flex gap-7 text-[15px] sm:gap-10">
          <a href="#help" className="flex flex-col items-center gap-0.5 hover:underline"><HelpIcon /><span>Help</span></a>
          <a href="#accessibility" className="flex flex-col items-center gap-0.5 hover:underline"><AccessibilityIcon /><span>Accessibility</span></a>
        </nav>
      </header>

      <section className="mx-auto flex w-full max-w-[1048px] flex-1 flex-col items-center justify-center pb-14 pt-10 sm:pb-24">
        <h1 className="text-center text-[48px] font-bold leading-none tracking-[-0.045em] sm:text-[68px]">How can we help?</h1>
        <p className="mt-5 text-center text-[22px] tracking-[-0.025em] sm:text-[27px]">Choose your workspace.</p>

        {!cognitoModeEnabled && <div className="mt-8 flex w-full flex-col rounded-[27px] border border-navy/20 bg-white/80 p-3 shadow-card sm:flex-row sm:items-center">
          <button type="button" aria-pressed={selected === "employee"} onClick={() => chooseRole("employee")} className={optionClass("employee")}>
            <GraduationCapIcon />
            <span>Employee / Faculty</span>
          </button>
          <button type="button" aria-pressed={selected === "reviewer"} onClick={() => chooseRole("reviewer")} className={optionClass("reviewer")}>
            <PolicyDocumentIcon />
            <span>Policy Reviewer / Writer</span>
          </button>
          <div className="my-3 h-px bg-navy/20 sm:my-0 sm:ml-3 sm:h-[72px] sm:w-px" />
          <button type="button" aria-label="Continue to selected workspace" disabled={isContinuing} onClick={() => void continueToWorkspace()} className="mx-auto flex h-[67px] w-[67px] shrink-0 items-center justify-center rounded-full bg-brand-blue text-white transition-colors hover:bg-brand-bright disabled:opacity-70 sm:mx-4">
            <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="h-9 w-9"><path d="M4 16h23M19 8l8 8-8 8" /></svg>
          </button>
        </div>}

        {cognitoModeEnabled && <button type="button" onClick={() => void startCognitoLogin().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to start CSUB SSO sign-in."))} className="mt-5 rounded-lg bg-navy px-6 py-3 text-sm font-semibold text-white shadow-card hover:bg-navy-deep">Sign in with CSUB SSO</button>}

        <p className="mt-10 text-center text-[18px] tracking-[-0.025em]">Ask questions, browse trusted policy, and verify guidance.</p>
        {error && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 px-5 py-3 text-red-800">{error}</p>}
      </section>

      <footer className="text-center text-[15px] text-navy/75">California State University, Bakersfield</footer>
    </main>
  );
}
