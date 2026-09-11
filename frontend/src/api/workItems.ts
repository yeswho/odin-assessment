import type { Status, WorkItem, WorkItemInput, WorkItemList } from "../types/workItem";

const baseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  let body;
  try { body = await response.json(); }
  catch { throw new Error("The server returned an unreadable response. Please try again."); }
  if (!response.ok) throw new Error(body.error?.message || "The request failed. Please try again.");
  return body as T;
}
export const workItemsApi = {
  list: (status: Status | "ALL", offset: number, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: "25", offset: String(offset) });
    if (status !== "ALL") query.set("status", status);
    return request<WorkItemList>(`/work-items?${query}`, { signal });
  },
  get: (id: string, signal?: AbortSignal) => request<WorkItem>(`/work-items/${id}`, { signal }),
  create: (data: WorkItemInput) => request<{ item: WorkItem; created: boolean }>("/work-items", { method: "POST", body: JSON.stringify(data) }),
  analyse: (id: string) => request<WorkItem>(`/work-items/${id}/analyse`, { method: "POST" }),
  retry: (id: string) => request<WorkItem>(`/work-items/${id}/retry`, { method: "POST" }),
  complete: (id: string) => request<WorkItem>(`/work-items/${id}/status`, { method: "PATCH", body: JSON.stringify({ status: "COMPLETED" }) }),
  health: () => request<{ status: string; aiProvider: string }>("/health"),
};
