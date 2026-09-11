import { useEffect, useRef, useState } from "react";
import { workItemsApi } from "../api/workItems";
import type { WorkItem } from "../types/workItem";
import { StatusBadge } from "./StatusBadge";

export function WorkItemDetail({ id, onChange, onClose }: { id: string; onChange: () => void; onClose: () => void }) {
  const [item, setItem] = useState<WorkItem | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  useEffect(() => {
    mounted.current = true;
    let controller: AbortController;
    const load = async () => {
      controller?.abort();
      const current = new AbortController();
      controller = current;
      const epoch = generation.current;
      try {
        const result = await workItemsApi.get(id, current.signal);
        if (mounted.current && !current.signal.aborted && epoch === generation.current) { setItem(result); setLoadError(""); }
      } catch (error) { if (mounted.current && !current.signal.aborted) setLoadError(error instanceof Error ? error.message : "Could not load request."); }
    };
    void load();
    const timer = window.setInterval(() => { void load(); }, 3000);
    return () => { mounted.current = false; clearInterval(timer); controller?.abort(); };
  }, [id]);

  async function act() {
    if (!item || busy) return;
    setBusy(true); setActionError(""); generation.current++;
    try {
      const result = item.status === "RECEIVED" ? await workItemsApi.analyse(id) : item.status === "FAILED" ? await workItemsApi.retry(id) : await workItemsApi.complete(id);
      generation.current++;
      if (mounted.current) setItem(result);
      onChange();
    } catch (error) {
      if (mounted.current) setActionError(error instanceof Error ? error.message : "Action failed. Refresh the request.");
    } finally { if (mounted.current) setBusy(false); }
  }
  return <aside className="detail" aria-label="Request details">
    <div className="detail-heading"><span className="eyebrow">REQUEST DETAILS</span><button className="icon-button" onClick={onClose} aria-label="Close request details">×</button></div>
    {loadError && <p className="error" role="alert">{loadError}</p>}
    {!item ? <p role="status" className="muted">Loading request…</p> : <>
      <span className="reference">{item.externalId}</span><h2>{item.title}</h2>
      <StatusBadge status={item.status} />
      <section><h3>Original request</h3><p className="description">{item.description}</p></section>
      <section className="analysis"><h3>✧ AI analysis</h3>
        {item.analysis ? <>
          <div className="analysis-tags"><span>{item.analysis.category.replaceAll("_", " ").toLowerCase()}</span><span className={`priority priority-${item.analysis.priority}`}>{item.analysis.priority.toLowerCase()} priority</span></div>
          <h4>Summary</h4><p>{item.analysis.summary}</p>
          <h4>Recommended action</h4><p>{item.analysis.recommendedAction}</p>
          <p className="review-note">Verify these suggestions against the original request before completing.</p>
        </> : item.errorMessage ? <div role="alert"><p className="failure-title">Analysis could not be completed</p><p>{item.errorMessage}</p></div> : <p className="muted">{item.status === "ANALYSING" ? "Analysis is in progress. The result will appear automatically." : "Run analysis to get a suggested category, priority and next action."}</p>}
      </section>
      <dl><dt>Analysis attempts</dt><dd>{item.attempts}</dd><dt>Provider</dt><dd>{item.aiProvider ?? "Not analysed"}</dd><dt>Last updated</dt><dd>{new Date(item.updatedAt).toLocaleString()}</dd></dl>
      {actionError && <p className="error" role="alert">{actionError}</p>}
      {item.status === "COMPLETED" ? <p className="completed-note">✓ Completed after review</p> : <button className="primary full-width" disabled={busy || item.status === "ANALYSING"} onClick={() => void act()}>{busy || item.status === "ANALYSING" ? "Analysing / updating…" : item.status === "RECEIVED" ? "Analyse request" : item.status === "FAILED" ? "Retry analysis" : "Complete work item"}</button>}
    </>}
  </aside>;
}
