import React, { useCallback, useEffect, useState } from "react";
import api from "./api";

// ---------------------------------------------------------------------------
// Styles (inline for zero-dep simplicity)
// ---------------------------------------------------------------------------
const S = {
  page:    { maxWidth: 960, margin: "2rem auto", padding: "0 1rem" },
  card:    { border: "1px solid #e2e8f0", borderRadius: 8, padding: "1rem", marginBottom: "1rem", background: "#fff" },
  heading: { borderBottom: "2px solid #e2e8f0", paddingBottom: "0.5rem" },
  input:   { padding: "0.3rem 0.6rem", fontSize: "1rem", marginRight: "0.5rem", border: "1px solid #cbd5e1", borderRadius: 4 },
  btn:     { padding: "0.3rem 0.8rem", fontSize: "1rem", cursor: "pointer", borderRadius: 4, border: "none", background: "#3b82f6", color: "#fff" },
  item:    { marginBottom: "0.5rem", lineHeight: 1.5 },
  dim:     { color: "#64748b", fontSize: "0.9em" },
  tag: (status) => ({
    display: "inline-block",
    padding: "0.1rem 0.5rem",
    borderRadius: 4,
    fontSize: "0.8em",
    fontWeight: "bold",
    marginLeft: "0.5rem",
    background: status === "approved" ? "#d1fae5" : status === "rejected" ? "#fee2e2" : status === "executed" ? "#dbeafe" : "#fef9c3",
    color:      status === "approved" ? "#065f46" : status === "rejected" ? "#991b1b" : status === "executed" ? "#1e3a8a" : "#713f12",
  }),
};

// ---------------------------------------------------------------------------
// Memory panel
// ---------------------------------------------------------------------------
function MemoryPanel() {
  const [session, setSession] = useState("");
  const [draft,   setDraft]   = useState("");
  const [items,   setItems]   = useState([]);
  const [query,   setQuery]   = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const loadSession = useCallback(async () => {
    if (!draft.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.inspect(draft.trim());
      setSession(draft.trim());
      setItems(data);
      setResults([]);
    } catch (e) {
      setError("Failed to load session: " + (e.message || e));
    } finally {
      setLoading(false);
    }
  }, [draft]);

  const doSearch = useCallback(async () => {
    if (!session || !query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.search(session, query.trim());
      setResults(data);
    } catch (e) {
      setError("Search failed: " + (e.message || e));
    } finally {
      setLoading(false);
    }
  }, [session, query]);

  return (
    <div style={S.card}>
      <h2 style={{ marginTop: 0 }}>🧠 Session Memory</h2>
      <div>
        <input
          style={S.input}
          placeholder="Session ID (e.g. my-session-1)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadSession()}
        />
        <button style={S.btn} onClick={loadSession} disabled={loading}>
          {loading ? "Loading…" : "Inspect"}
        </button>
      </div>

      {error && <p style={{ color: "#ef4444" }}>{error}</p>}

      {session && (
        <>
          <h3>
            Global namespace:{" "}
            <code>{session}:global</code>{" "}
            <span style={S.dim}>({items.length} item(s))</span>
          </h3>
          {items.length === 0 ? (
            <p style={S.dim}>No items found.</p>
          ) : (
            <ul>
              {items.map((it, i) => (
                <li key={i} style={S.item}>
                  <strong>{it.agent_id}</strong>: {it.input}
                  {it.summary && (
                    <span style={S.dim}> — {it.summary}</span>
                  )}
                </li>
              ))}
            </ul>
          )}

          <h3>Semantic Search</h3>
          <div>
            <input
              style={S.input}
              placeholder="search query…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doSearch()}
            />
            <button style={S.btn} onClick={doSearch} disabled={loading || !query}>
              Search
            </button>
          </div>
          {results.length > 0 && (
            <ul>
              {results.map((it, i) => (
                <li key={i} style={S.item}>
                  <strong>{it.agent_id}</strong>: {it.input}
                  {it.summary && (
                    <span style={S.dim}> — {it.summary}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Approvals panel
// ---------------------------------------------------------------------------
function ApprovalsPanel() {
  const [items,   setItems]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.listApprovals();
      setItems(data);
    } catch (e) {
      setError("Failed to load approvals: " + (e.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div style={S.card}>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <h2 style={{ margin: 0 }}>🔐 Approval Queue</h2>
        <button style={{ ...S.btn, background: "#64748b" }} onClick={refresh} disabled={loading}>
          {loading ? "…" : "Refresh"}
        </button>
      </div>
      {error && <p style={{ color: "#ef4444" }}>{error}</p>}
      {items.length === 0 && !loading && (
        <p style={S.dim}>No approval requests found.</p>
      )}
      {items.map((it) => (
        <div key={it.id} style={{ ...S.card, marginTop: "0.5rem", marginBottom: 0 }}>
          <strong>{it.action}</strong>
          <span style={S.tag(it.status)}>{it.status.toUpperCase()}</span>
          <span style={{ ...S.dim, marginLeft: "0.5rem", fontSize: "0.75em" }}>
            {it.id}
          </span>
          <pre style={{ background: "#f1f5f9", padding: "0.5rem", borderRadius: 4, fontSize: "0.8em", overflowX: "auto" }}>
            {JSON.stringify(it.payload, null, 2)}
          </pre>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root app
// ---------------------------------------------------------------------------
export default function App() {
  return (
    <div style={S.page}>
      <h1 style={S.heading}>RealAI Dashboard</h1>
      <MemoryPanel />
      <ApprovalsPanel />
    </div>
  );
}
