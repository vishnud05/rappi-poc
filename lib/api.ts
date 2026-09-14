export type ScenarioSummary = {
  id: string;
  title: string;
  description: string;
  category: string;
  recommendation_units: number;
};

export type PurchaseOrder = {
  id: string;
  requested_units: number;
  confirmed_units: number;
  unit_cost_cents: number;
  total_cost_cents: number;
  arrival_day: number;
  status: string;
};

export type Scenario = ScenarioSummary & {
  inventory_units: number;
  daily_demand_units: number | null;
  lead_time_days: number;
  review_days: number;
  safety_stock_units: number;
  moq_units: number;
  pack_size_units: number;
  unit_cost_cents: number;
  budget_cents: number;
  capacity_units: number;
  open_pos: { id: string; quantity: number; arrival_day: number; status: string }[];
  supplier_behavior: string;
  purchase_orders: PurchaseOrder[];
};

export type RunEvent = {
  seq: number;
  kind: "tool_call" | "tool_result" | "decision" | "action" | "validation" | "error" | "info";
  name: string;
  detail: unknown;
  created_at: string;
};

export type Run = {
  id: string;
  scenario_id: string;
  status: "running" | "validated" | "needs_review" | "failed";
  decision: "accept" | "modify" | "reject" | "investigate" | null;
  quantity: number | null;
  summary: string;
  model: string;
  created_at: string;
  finished_at: string | null;
  error: string | null;
  events: RunEvent[];
  purchase_order: PurchaseOrder | null;
  validation: {
    passed: boolean;
    checks: { name: string; passed: boolean; detail: string }[];
    shortage_units: number;
  } | null;
};

export type Health = { status: string; model: string; model_configured: boolean };

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { cache: "no-store", ...options });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(typeof payload?.detail === "string" ? payload.detail : "The purchasing service is unavailable. Check that the backend is running, then retry.", response.status);
  }
  if (payload === null) throw new Error("The purchasing service returned an empty response. Please retry.");
  return payload as T;
}
