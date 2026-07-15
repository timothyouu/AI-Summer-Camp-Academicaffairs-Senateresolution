import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "policy-intelligence-theme";
const ThemeContext = createContext<{ theme: Theme; setTheme: (theme: Theme) => void } | null>(null);

function storedTheme(): Theme {
  return window.localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(storedTheme);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);
  const value = useMemo(() => ({
    theme,
    setTheme: (next: Theme) => { window.localStorage.setItem(STORAGE_KEY, next); setThemeState(next); },
  }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): { theme: Theme; setTheme: (theme: Theme) => void } {
  const context = useContext(ThemeContext);
  if (context === null) throw new Error("useTheme must be used within ThemeProvider");
  return context;
}
