export const statuses = ["RECEIVED", "ANALYSING", "READY_FOR_REVIEW", "COMPLETED", "FAILED"] as const;
export type Status = (typeof statuses)[number];
export const statusLabels: Record<Status, string> = {
  RECEIVED: "Received", ANALYSING: "Analysing", READY_FOR_REVIEW: "Ready for review",
  COMPLETED: "Completed", FAILED: "Failed",
};
export interface WorkItemInput { externalId: string; title: string; description: string }
export interface Analysis {
  category: "DOCUMENT_REQUEST" | "BILLING" | "TECHNICAL_SUPPORT" | "GENERAL";
  priority: "LOW" | "MEDIUM" | "HIGH";
  summary: string;
  recommendedAction: string;
}
export interface WorkItem extends WorkItemInput {
  id: string;
  status: Status;
  analysis: Analysis | null;
  aiProvider: string | null;
  attempts: number;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}
export interface WorkItemList {
  items: WorkItem[]; total: number; limit: number; offset: number;
  counts: Record<Status, number>;
}
