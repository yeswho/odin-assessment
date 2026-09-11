import { useCallback, useEffect, useState } from "react";
import { workItemsApi } from "../api/workItems";
import { CreateWorkItem } from "../components/CreateWorkItem";
import { WorkItemDetail } from "../components/WorkItemDetail";
import { WorkItemTable } from "../components/WorkItemTable";
import { useWorkItems } from "../hooks/useWorkItems";
import { statuses, statusLabels, type Status } from "../types/workItem";

export function WorkIntakePage() {
  const [filter, setFilter] = useState<Status | "ALL">("ALL");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const { data, loading, error, refresh } = useWorkItems(filter, offset);
  useEffect(() => { workItemsApi.health().then(result => setProvider(result.aiProvider)).catch(() => setProvider(null)); }, []);
  useEffect(() => { if (data && offset > 0 && offset >= data.total) setOffset(Math.max(0, offset - 25)); }, [data, offset]);
  const changed = useCallback(() => { void refresh(true); }, [refresh]);
  const counts = data?.counts;
  const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : null;

  return <>
    <header className="topbar"><a className="brand" href="/"><span className="brand-mark">O</span> ODIN ASSESSMENT <span className="workspace-name">AI-Assisted Work Intake System</span></a><span className="provider-indicator">{provider ? `${provider === "mock" ? "Mock" : "Anthropic"} AI` : "Work intake"}</span></header>
    <main>
      <div className="page-heading"><div><p className="eyebrow">WORK MANAGEMENT</p><h1>Work intake</h1><p className="muted">Incoming requests, ready for the next step.</p></div><button className="primary" onClick={() => setCreateOpen(true)}>＋ New work item</button></div>
      <section className="stats" aria-label="Queue overview">{[
        ["Total work items", total], ["Ready for review", counts?.READY_FOR_REVIEW],
        ["Completed", counts?.COMPLETED], ["Needs attention", counts?.FAILED],
      ].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value ?? "—"}</strong></article>)}</section>
      {notice && <p className="notice" role="status">{notice}<button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice("")}>×</button></p>}
      <div className={selectedId ? "work-area with-detail" : "work-area"}>
        <section className="queue" aria-label="Request queue">
          <div className="queue-heading"><h2>Request queue</h2><button onClick={() => void refresh()} disabled={loading}>↻ Refresh</button></div>
          <div className="queue-tools"><label htmlFor="status-filter">Status<select id="status-filter" value={filter} onChange={e => { setFilter(e.target.value as Status | "ALL"); setOffset(0); }}><option value="ALL">All items</option>{statuses.map(status => <option key={status} value={status}>{statusLabels[status]}</option>)}</select></label><span className="muted">Updates every 3 seconds</span></div>
          {error && <p role="alert" className="error">{error} <button onClick={() => void refresh()}>Try again</button></p>}
          {loading && !data ? <div className="empty" role="status"><span className="spinner" /> Loading work items…</div> : data?.items.length ? <WorkItemTable items={data.items} selectedId={selectedId} onSelect={setSelectedId} /> : !error && <div className="empty"><span className="empty-symbol">↓</span><h3>{filter === "ALL" ? "Your queue starts here" : "No items in this stage"}</h3><p className="muted">{filter === "ALL" ? "Add a request to start analysis and review." : "Try another status or check back later."}</p>{filter === "ALL" && <button onClick={() => setCreateOpen(true)}>Add work item</button>}</div>}
          <div className="pagination"><span>{data?.total ? `${offset + 1}–${Math.min(offset + 25, data.total)} of ${data.total}` : "0 items"}</span><div><button disabled={offset === 0 || loading} onClick={() => setOffset(v => v - 25)}>Previous</button><button disabled={!data || offset + 25 >= data.total || loading} onClick={() => setOffset(v => v + 25)}>Next</button></div></div>
        </section>
        {selectedId && <WorkItemDetail key={selectedId} id={selectedId} onChange={changed} onClose={() => setSelectedId(null)} />}
      </div>
      <footer>Submitted By: Yeshu Anand Shah</footer>
    </main>
    <CreateWorkItem open={createOpen} onClose={() => setCreateOpen(false)} onCreated={created => { setNotice(created ? "New work item received." : "This work item already exists. No duplicate was created."); setFilter("ALL"); setOffset(0); void refresh(true); }} />
  </>;
}
