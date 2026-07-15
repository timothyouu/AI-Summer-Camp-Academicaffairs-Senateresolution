import { useEffect, useRef, useState } from "react";
import { useTheme } from "../state/theme";

export default function SettingsMenu() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div ref={containerRef} className="relative flex flex-col items-center">
      <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-haspopup="menu"
        className="flex flex-col items-center gap-1 py-3 text-xs text-navy hover:text-brand-blue">
        <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="12" r="3" /><path d="m19 13.5 2-1.5-2-1.5-.7-1.8.4-2.5-2.5-.4-1.7-1.3L13.5 2 12 4l-1.5-2-1 2.5-1.7 1.3-2.5.4.4 2.5L5 10.5 3 12l2 1.5.7 1.8-.4 2.5 2.5.4 1.7 1.3 1 2.5 1.5-2 1.5 2 1-2.5 1.7-1.3 2.5-.4-.4-2.5z" /></svg>
        <span>Settings</span>
      </button>
      {open && (
        <div role="menu" className="absolute bottom-14 left-16 z-30 w-52 rounded-xl border border-navy/15 bg-white p-4 shadow-card">
          <p className="text-xs font-semibold uppercase tracking-wide text-inkmuted">Appearance</p>
          <button type="button" role="menuitem" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="mt-2 flex w-full items-center justify-between rounded-md px-2 py-2 text-sm text-navy hover:bg-cream">
            <span>Dark mode</span>
            <span className={`flex h-5 w-9 items-center rounded-full px-0.5 transition-colors ${theme === "dark" ? "justify-end bg-brand-blue" : "bg-slate-300"}`}>
              <span className="h-4 w-4 rounded-full bg-white shadow" />
            </span>
          </button>
        </div>
      )}
    </div>
  );
}
