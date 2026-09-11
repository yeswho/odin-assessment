import type { WorkItem } from "../types/workItem";
import { StatusBadge } from "./StatusBadge";

export function WorkItemTable({ items, selectedId, onSelect }: { items: WorkItem[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return <div className="table-scroll"><table>
    <thead><tr><th>Work item</th><th>Status</th><th>Priority</th><th>Received</th></tr></thead>
    <tbody>{items.map(item => <tr key={item.id} className={item.id === selectedId ? "selected" : ""}>
      <td><button className="item-button" onClick={() => onSelect(item.id)} aria-pressed={item.id === selectedId}><span className="reference">{item.externalId}</span><strong>{item.title}</strong></button></td>
      <td><StatusBadge status={item.status} /></td>
      <td>{item.analysis ? <span className={`priority priority-${item.analysis.priority}`}>{item.analysis.priority.toLowerCase()}</span> : <span className="muted">—</span>}</td>
      <td className="date">{new Date(item.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</td>
    </tr>)}</tbody>
  </table></div>;
}
