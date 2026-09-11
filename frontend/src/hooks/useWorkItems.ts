import { useCallback, useEffect, useRef, useState } from "react";
import { workItemsApi } from "../api/workItems";
import type { Status, WorkItemList } from "../types/workItem";

export function useWorkItems(status: Status | "ALL", offset: number) {
  const [data, setData] = useState<WorkItemList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const inFlight = useRef<AbortController | null>(null);

  const refresh = useCallback(async (quiet = false) => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    if (!quiet) setLoading(true);
    try {
      const next = await workItemsApi.list(status, offset, controller.signal);
      if (!controller.signal.aborted) { setData(next); setError(""); }
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Could not load work items.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [status, offset]);

  useEffect(() => {
    setData(null);
    void refresh();
    const timer = window.setInterval(() => { void refresh(true); }, 3000);
    return () => { clearInterval(timer); inFlight.current?.abort(); };
  }, [refresh]);
  return { data, loading, error, refresh };
}
