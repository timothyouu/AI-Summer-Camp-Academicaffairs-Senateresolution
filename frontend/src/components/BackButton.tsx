import { useNavigate } from "react-router-dom";

export default function BackButton({ fallback }: { fallback: string }) {
  const navigate = useNavigate();
  const goBack = () => {
    if (window.history.length > 1) navigate(-1);
    else navigate(fallback);
  };
  return (
    <button type="button" onClick={goBack} aria-label="Go back"
      className="mb-4 inline-flex items-center gap-2 text-sm font-medium text-brand-blue hover:underline">
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 19 8 12l7-7" /></svg>
      Back
    </button>
  );
}
