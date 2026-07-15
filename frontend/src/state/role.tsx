import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { Role } from "../data/mock";

interface RoleContextValue {
  role: Role;
  setRole: (role: Role) => void;
}

const STORAGE_KEY = "policy-intelligence-role";
const RoleContext = createContext<RoleContextValue | null>(null);

function storedRole(): Role {
  const value = window.localStorage.getItem(STORAGE_KEY);
  return value === "reviewer" ? "reviewer" : "employee";
}

export function RoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<Role>(storedRole);

  const value = useMemo<RoleContextValue>(() => ({
    role,
    setRole: (nextRole) => {
      window.localStorage.setItem(STORAGE_KEY, nextRole);
      setRoleState(nextRole);
    },
  }), [role]);

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const context = useContext(RoleContext);
  if (context === null) {
    throw new Error("useRole must be used within RoleProvider");
  }
  return context;
}
