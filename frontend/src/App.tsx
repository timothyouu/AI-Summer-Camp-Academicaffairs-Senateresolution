import { useEffect, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import type { Role } from "./data/mock";
import ChatAnswer from "./pages/ChatAnswer";
import Chats from "./pages/Chats";
import ConflictLog from "./pages/ConflictLog";
import ConflictReview from "./pages/ConflictReview";
import Drafts from "./pages/Drafts";
import Library from "./pages/Library";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import ReviewOverview from "./pages/ReviewOverview";
import ReviewResults from "./pages/ReviewResults";
import Sources from "./pages/Sources";
import TopicDetail from "./pages/TopicDetail";
import TopicList from "./pages/TopicList";
import { RoleProvider, useRole } from "./state/role";

/** Renders under whatever role is currently active (does not force one). Used for routes shared by both roles. */
function SharedRoute({ children }: { children: ReactNode }) {
  const { role } = useRole();
  return <AppLayout role={role}>{children}</AppLayout>;
}

/** Forces the given role. Used for maker-only routes an employee has no sidebar links to. */
function WorkspaceRoute({ role, children }: { role: Role; children: ReactNode }) {
  const { role: currentRole, setRole } = useRole();
  useEffect(() => {
    if (currentRole !== role) setRole(role);
  }, [currentRole, role, setRole]);
  return <AppLayout role={role}>{children}</AppLayout>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/chats" element={<SharedRoute><Chats /></SharedRoute>} />
      <Route path="/chats/:conversationId" element={<SharedRoute><ChatAnswer /></SharedRoute>} />
      <Route path="/library" element={<SharedRoute><Library /></SharedRoute>} />
      <Route path="/topics" element={<SharedRoute><TopicList /></SharedRoute>} />
      <Route path="/topics/:slug" element={<SharedRoute><TopicDetail /></SharedRoute>} />
      <Route path="/reviews" element={<WorkspaceRoute role="reviewer"><ReviewOverview /></WorkspaceRoute>} />
      <Route path="/drafts" element={<WorkspaceRoute role="reviewer"><Drafts /></WorkspaceRoute>} />
      <Route path="/review" element={<WorkspaceRoute role="reviewer"><ReviewResults /></WorkspaceRoute>} />
      <Route path="/conflicts" element={<WorkspaceRoute role="reviewer"><ConflictLog /></WorkspaceRoute>} />
      <Route path="/conflicts/:slug" element={<WorkspaceRoute role="reviewer"><ConflictReview /></WorkspaceRoute>} />
      <Route path="/sources" element={<WorkspaceRoute role="reviewer"><Sources /></WorkspaceRoute>} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default function App() {
  return <RoleProvider><AppRoutes /></RoleProvider>;
}
