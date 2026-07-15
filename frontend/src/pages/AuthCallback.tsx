import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { completeCognitoLogin } from "../auth/cognito";
import { useRole } from "../state/role";

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { setRole } = useRole();
  const [error, setError] = useState("");
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const oauthError = params.get("error");
    const code = params.get("code");
    if (oauthError || !code) {
      setError(oauthError ? `CSUB SSO sign-in was cancelled: ${oauthError}.` : "CSUB SSO did not return an authorization code.");
      return;
    }
    void completeCognitoLogin(code, params.get("state")).then((role) => {
      setRole(role);
      navigate(role === "reviewer" ? "/reviews" : "/chats", { replace: true });
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to complete CSUB SSO sign-in."));
  }, [navigate, params, setRole]);

  return <main className="flex min-h-screen items-center justify-center bg-cream p-6 text-navy"><section className="w-full max-w-md rounded-xl border border-navy/15 bg-white p-8 text-center shadow-card"><h1 className="text-2xl font-bold">Completing CSUB SSO sign-in</h1>{error ? <><p role="alert" className="mt-4 text-sm text-red-700">{error}</p><Link to="/login" className="mt-6 inline-block text-sm font-medium text-brand-blue hover:underline">Return to sign in</Link></> : <p className="mt-4 text-sm text-inkmuted">Verifying your session and selecting your workspace…</p>}</section></main>;
}
