import { statusLabels, type Status } from "../types/workItem";

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge badge-${status}`}>
    {status === "ANALYSING" && <span className="spinner" aria-hidden="true" />}
    {statusLabels[status]}
  </span>;
}
