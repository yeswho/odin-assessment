import { useEffect, useRef, useState, type FormEvent } from "react";
import { workItemsApi } from "../api/workItems";

interface Props { open: boolean; onClose: () => void; onCreated: (created: boolean) => void }
export function CreateWorkItem({ open, onClose, onCreated }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [form, setForm] = useState({ externalId: "", title: "", description: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
    if (!open && dialog.current?.open) dialog.current?.close();
  }, [open]);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await workItemsApi.create(form);
      setForm({ externalId: "", title: "", description: "" });
      onCreated(result.created); onClose();
    } catch (error) { setError(error instanceof Error ? error.message : "Could not save this request."); }
    finally { setBusy(false); }
  }
  return <dialog ref={dialog} aria-labelledby="create-title" onCancel={event => { if (busy) event.preventDefault(); else onClose(); }}>
    <form onSubmit={submit}>
      <div className="dialog-heading"><h2 id="create-title">New work item</h2><button type="button" className="icon-button" onClick={onClose} disabled={busy} aria-label="Close form">×</button></div>
      <p className="muted">Enter the request as received from the external system.</p>
      <label htmlFor="external-id">External ID<input id="external-id" autoFocus required maxLength={100} value={form.externalId} onChange={e => setForm({ ...form, externalId: e.target.value })} placeholder="CRM-12345" /></label>
      <label htmlFor="title">Title<input id="title" required maxLength={200} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Missing income document" /></label>
      <label htmlFor="description">Description<textarea id="description" required maxLength={10000} rows={5} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="Describe the request and any relevant context…" /></label>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="dialog-actions"><button type="button" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" disabled={busy}>{busy ? "Saving…" : "Create work item"}</button></div>
    </form>
  </dialog>;
}
