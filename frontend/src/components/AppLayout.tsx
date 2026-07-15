import type { ReactNode } from "react";
import type { Role } from "../data/mock";
import RoleSwitcher from "./RoleSwitcher";
import Sidebar from "./Sidebar";

interface AppLayoutProps {
  children: ReactNode;
  role: Role;
}

export default function AppLayout({ children, role }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-white">
      <Sidebar role={role} />
      <div className="min-h-screen ml-24">
        <header className="flex h-24 items-center justify-end px-10"><RoleSwitcher /></header>
        <main className="px-10 pb-12">{children}</main>
      </div>
    </div>
  );
}
