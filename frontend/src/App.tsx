import { useEffect, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
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
import { cognitoSessionExpiredEvent, getCognitoAuthorizationToken, roleFromIdToken } from "./auth/cognito";

const cognitoModeEnabled = import.meta.env.VITE_USE_COGNITO === "true";

function CognitoWorkspaceGate({ children }: { children: ReactNode }) {
  const [hasSession, setHasSession] = useState<boolean | null>(cognitoModeEnabled ? null : true);
  const { role, setRole } = useRole();

  useEffect(() => {
    if (!cognitoModeEnabled) return;
    let active = true;
    void getCognitoAuthorizationToken().then(
      (token) => {
        if (!active) return;
        if (token === null) {
          setHasSession(false);
          return;
        }
        const tokenRole = roleFromIdToken(token);
        if (role !== tokenRole) setRole(tokenRole);
        setHasSession(true);
      },
      () => { if (active) setHasSession(false); },
    );
    return () => { active = false; };
  }, [role, setRole]);

  if (hasSession === null) return null;
  if (!hasSession) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** Renders under whatever role is currently active (does not force one). Used for routes shared by both roles. */
function SharedRoute({ children }: { children: ReactNode }) {
  const { role } = useRole();
  return <CognitoWorkspaceGate><AppLayout role={role}>{children}</AppLayout></CognitoWorkspaceGate>;
}

/** Forces the given role. Used for maker-only routes an employee has no sidebar links to.
 * In Cognito mode the role comes from the verified token instead — an
 * authenticated employee must not be elevated by simply visiting a maker URL. */
function WorkspaceRoute({ role, children }: { role: Role; children: ReactNode }) {
  const { role: currentRole, setRole } = useRole();
  const [tokenRole, setTokenRole] = useState<Role | null | undefined>(cognitoModeEnabled ? undefined : role);
  useEffect(() => {
    if (!cognitoModeEnabled) return;
    let cancelled = false;
    void getCognitoAuthorizationToken().then((token) => {
      if (!cancelled) setTokenRole(token !== null ? roleFromIdToken(token) : null);
    }).catch(() => {
      if (!cancelled) setTokenRole(null);
    });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (tokenRole !== undefined && tokenRole !== null && currentRole !== tokenRole) setRole(tokenRole);
  }, [currentRole, setRole, tokenRole]);
  if (cognitoModeEnabled) {
    if (tokenRole === undefined) return null;
    if (tokenRole === null) return <Navigate to="/login" replace />;
    if (tokenRole !== role) return <Navigate to="/chats" replace />;
  }
  return <CognitoWorkspaceGate><AppLayout role={role}>{children}</AppLayout></CognitoWorkspaceGate>;
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
  return <RoleProvider><CognitoSessionRedirect /><AppRoutes /></RoleProvider>;
}

function CognitoSessionRedirect() {
  const navigate = useNavigate();

  useEffect(() => {
    const redirectToLogin = () => navigate("/login", { replace: true });
    window.addEventListener(cognitoSessionExpiredEvent, redirectToLogin);
    return () => window.removeEventListener(cognitoSessionExpiredEvent, redirectToLogin);
  }, [navigate]);

  return null;
}
