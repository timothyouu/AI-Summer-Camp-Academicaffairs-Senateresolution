import { useEffect, useState } from "react";
import { getPermissions, savePermission, type Permission } from "../api";
import { currentUserIsSourceAdmin } from "../auth/cognito";

const SOURCE_TYPES: Permission["sourceType"][] = ["handbook", "cba", "policystat", "catalog", "uploads"];

export default function SourcePermissions() {
  const isAdmin = currentUserIsSourceAdmin();
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (isAdmin) void getPermissions().then(setPermissions).catch(() => setPermissions([]));
  }, [isAdmin]);

  if (!isAdmin) return null;

  const users = [...new Set(permissions.map((item) => item.userEmail))];
  const cell = (user: string, sourceType: Permission["sourceType"]): Permission =>
    permissions.find((item) => item.userEmail === user && item.sourceType === sourceType)
      ?? { userEmail: user, sourceType, canAdd: false, canEdit: false };

  const toggle = async (
    user: string,
    sourceType: Permission["sourceType"],
    field: "canAdd" | "canEdit",
  ): Promise<void> => {
    const current = cell(user, sourceType);
    try {
      const saved = await savePermission({ ...current, [field]: !current[field] });
      setPermissions((existing) => [
        saved,
        ...existing.filter((item) => !(item.userEmail === user && item.sourceType === sourceType)),
      ]);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save the permission.");
    }
  };

  const addUser = async (): Promise<void> => {
    const clean = email.trim().toLowerCase();
    if (!clean.includes("@")) {
      setError("Enter a campus email address.");
      return;
    }
    try {
      const saved = await savePermission({
        userEmail: clean,
        sourceType: "uploads",
        canAdd: true,
        canEdit: false,
      });
      setPermissions((existing) => [
        saved,
        ...existing.filter((item) => !(item.userEmail === clean && item.sourceType === "uploads")),
      ]);
      setEmail("");
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to add this user.");
    }
  };

  return (
    <section className="mt-12 rounded-xl border border-navy/15 bg-white p-7 shadow-card">
      <h2 className="text-2xl font-bold text-navy">Source access permissions</h2>
      <p className="mt-1 text-inkmuted">Grant reviewers and writers the ability to add or edit sources, per source type.</p>
      <div className="mt-5 flex gap-3">
        <input
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="reviewer email…"
          className="h-11 w-80 rounded-lg border border-navy/25 px-4 outline-none focus:border-brand-blue"
        />
        <button
          type="button"
          onClick={() => { void addUser(); }}
          className="rounded-md bg-navy px-5 text-white hover:bg-brand-blue"
        >
          Grant upload access
        </button>
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <table className="mt-6 w-full text-left text-sm">
        <thead className="border-b border-navy/15 text-slate-600">
          <tr>
            <th className="py-3">User</th>
            {SOURCE_TYPES.map((sourceType) => <th key={sourceType} className="py-3 capitalize">{sourceType}</th>)}
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user} className="border-b border-navy/10">
              <td className="py-3 font-medium text-navy">{user}</td>
              {SOURCE_TYPES.map((sourceType) => {
                const permission = cell(user, sourceType);
                return (
                  <td key={sourceType} className="py-3">
                    <label className="mr-3 inline-flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={permission.canAdd}
                        onChange={() => { void toggle(user, sourceType, "canAdd"); }}
                      />
                      add
                    </label>
                    <label className="inline-flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={permission.canEdit}
                        onChange={() => { void toggle(user, sourceType, "canEdit"); }}
                      />
                      edit
                    </label>
                  </td>
                );
              })}
            </tr>
          ))}
          {users.length === 0 && (
            <tr>
              <td colSpan={6} className="py-6 text-inkmuted">
                No grants yet — the backend seeds the demo reviewer automatically.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
