"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDownRight, ArrowRight, ArrowUpRight, Box, Check, CheckCheck,
  CheckCircle2, ChevronDown, ChevronRight, Circle, CircleAlert, ClipboardCheck,
  Clock3, Database, FileText, Layers3, Loader2, PackageCheck, Play,
  RotateCcw, Search, ShieldCheck, ShoppingBasket, Sparkles, Truck, Wallet, X,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { api, ApiError, type Health, type PurchaseOrder, type Run, type RunEvent, type Scenario, type ScenarioSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const number = new Intl.NumberFormat("en-US");
const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 2 });
const money = (cents: number) => currency.format(cents / 100);
const humanize = (value: string) => value.replaceAll("_", " ").replaceAll("-", " ").replace(/^./, (letter) => letter.toUpperCase());
const message = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please retry.";
const statusText = { running: "Review in progress", validated: "Verified", needs_review: "Buyer review needed", failed: "Run interrupted" };

function StatusBadge({ run }: { run: Run | null }) {
  return <Badge variant="outline" className={cn("gap-1.5 rounded-full px-2.5 py-1 font-medium", !run ? "bg-white text-muted-foreground" : run.status === "validated" ? "border-[#cbe4d3] bg-[#f0f8f2] text-[#277447]" : run.status === "running" ? "border-[#f2d0c8] bg-[#fff4f0] text-[#ba4b39]" : "border-[#ead8b2] bg-[#fff9eb] text-[#91661e]")}>
    {run?.status === "running" ? <Loader2 className="size-3 animate-spin" /> : run?.status === "validated" ? <CheckCircle2 className="size-3" /> : run ? <CircleAlert className="size-3" /> : <Circle className="size-2 fill-current" />}
    {run ? statusText[run.status] : "Ready to review"}
  </Badge>;
}

function Metric({ label, value, unit, detail, icon: Icon }: { label: string; value: string; unit?: string; detail: string; icon: typeof Box }) {
  return <div className="min-w-0 border-b border-border p-5 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0">
    <div className="mb-3 flex items-center justify-between gap-2 text-muted-foreground"><span className="text-xs font-medium">{label}</span><Icon aria-hidden className="size-4 text-[#9b9d93]" /></div>
    <div className="flex items-baseline gap-1.5"><span className="text-[27px] font-semibold leading-none tracking-tight tabular-nums">{value}</span><span className="text-xs text-muted-foreground">{unit}</span></div>
    <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{detail}</p>
  </div>;
}

function EvidenceRow({ label, value, warning = false }: { label: string; value: React.ReactNode; warning?: boolean }) {
  return <div className="flex items-start justify-between gap-4 py-2 text-xs"><dt className="text-muted-foreground">{label}</dt><dd className={cn("text-right font-medium tabular-nums", warning && "text-amber-700")}>{value}</dd></div>;
}

function EvidencePanel({ scenario }: { scenario: Scenario }) {
  return <section aria-labelledby="evidence-title" className="overflow-hidden rounded-xl border bg-white">
    <div className="flex items-center justify-between border-b px-5 py-4"><h2 id="evidence-title" className="flex items-center gap-2 text-sm font-semibold"><Database aria-hidden className="size-4 text-muted-foreground" />Source evidence</h2><span className="eyebrow text-muted-foreground">Current state</span></div>
    <div className="px-5 py-3">
      <div className="mb-1 mt-1 flex items-center gap-2 text-xs font-semibold"><Box aria-hidden className="size-3.5 text-muted-foreground" />Inventory & demand</div>
      <dl><EvidenceRow label="Available stock" value={`${number.format(scenario.inventory_units)} units`} /><EvidenceRow label="Forecast demand" value={scenario.daily_demand_units === null ? "Missing evidence" : `${number.format(scenario.daily_demand_units)} units / day`} warning={scenario.daily_demand_units === null} /><EvidenceRow label="Safety stock" value={`${number.format(scenario.safety_stock_units)} units`} /><EvidenceRow label="Review period" value={`${scenario.review_days} days`} /></dl>
      <Separator className="my-3" />
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold"><Truck aria-hidden className="size-3.5 text-muted-foreground" />Supplier terms</div>
      <dl><EvidenceRow label="Lead time" value={`${scenario.lead_time_days} days`} /><EvidenceRow label="Unit cost" value={money(scenario.unit_cost_cents)} /><EvidenceRow label="Minimum order" value={`${number.format(scenario.moq_units)} units`} /><EvidenceRow label="Pack size" value={`${number.format(scenario.pack_size_units)} units`} /></dl>
      <Separator className="my-3" />
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold"><ShieldCheck aria-hidden className="size-3.5 text-muted-foreground" />Purchasing limits</div>
      <dl><EvidenceRow label="Remaining budget" value={money(scenario.budget_cents)} /><EvidenceRow label="Storage capacity" value={`${number.format(scenario.capacity_units)} units`} /></dl>
    </div>
    <details className="group border-t px-5 py-3.5">
      <summary className="flex items-center justify-between gap-3 text-xs font-medium"><span>Existing incoming orders <span className="ml-1 text-muted-foreground">{scenario.open_pos.length}</span></span><ChevronDown aria-hidden className="size-3.5 text-muted-foreground transition-transform group-open:rotate-180" /></summary>
      <div className="space-y-2 pt-3">{scenario.open_pos.length ? scenario.open_pos.map((order) => <div key={order.id} className="rounded-lg bg-muted px-3 py-2"><div className="flex items-center justify-between gap-3 text-xs"><span className="truncate font-mono text-[10px]">{order.id}</span><span className="whitespace-nowrap font-semibold">{number.format(order.quantity)} units</span></div><div className="mt-1 flex justify-between text-[10px] text-muted-foreground"><span>Arrives day {order.arrival_day}</span><span>{humanize(order.status)}</span></div></div>) : <p className="text-xs text-muted-foreground">No existing incoming orders.</p>}</div>
    </details>
  </section>;
}

function EventItem({ event }: { event: RunEvent }) {
  const result = event.kind === "tool_result";
  const detail = event.detail && typeof event.detail === "object" ? event.detail as Record<string, unknown> : null;
  const failure = event.kind === "error" || Boolean(detail?.error) || detail?.passed === false;
  return <details className="group border-b last:border-b-0">
    <summary className="flex list-none items-center gap-3 px-5 py-3 hover:bg-muted/60">
      <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-full", failure ? "bg-red-50 text-red-700" : result || event.kind === "validation" ? "bg-[#eef5ed] text-[#54805d]" : "bg-muted text-muted-foreground")}>{failure ? <X aria-hidden className="size-3" /> : result ? <Check aria-hidden className="size-3" /> : event.kind === "tool_call" ? <Search aria-hidden className="size-3" /> : <FileText aria-hidden className="size-3" />}</span>
      <div className="min-w-0 flex-1"><p className="truncate text-xs font-medium">{humanize(event.name)}</p><p className="mt-0.5 text-[10px] text-muted-foreground">{humanize(event.kind)}</p></div>
      <time className="text-[10px] tabular-nums text-muted-foreground" dateTime={event.created_at}>{new Date(event.created_at).toLocaleTimeString("en-US", { hour12: false })}</time>
      <ChevronRight aria-hidden className="size-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
    </summary>
    <div className="border-t border-dashed bg-[#fafaf8] px-5 py-3"><pre className="event-json rounded-md text-[11px] leading-relaxed text-[#62665a]">{typeof event.detail === "string" ? event.detail : JSON.stringify(event.detail, null, 2)}</pre></div>
  </details>;
}

function OrderDetails({ order }: { order: PurchaseOrder }) {
  return <div className="mt-4 rounded-lg border bg-[#fafbf8] p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><span className="flex items-center gap-1.5 text-xs font-semibold"><PackageCheck aria-hidden className="size-3.5 text-[#547258]" />Persisted purchase order</span><Badge variant="outline" className="bg-white text-[10px] font-normal">{humanize(order.status)}</Badge></div>
    <p className="mb-3 break-all font-mono text-[10px] text-muted-foreground">{order.id}</p>
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">{[["Requested", `${number.format(order.requested_units)} units`], ["Confirmed", `${number.format(order.confirmed_units)} units`], ["Committed", money(order.total_cost_cents)], ["Arrival", `Day ${order.arrival_day}`]].map(([label, value]) => <div key={label}><p className="text-[10px] text-muted-foreground">{label}</p><p className="mt-1 text-xs font-semibold tabular-nums">{value}</p></div>)}</div>
  </div>;
}

function DecisionPanel({ scenario, run }: { scenario: Scenario; run: Run | null }) {
  const done = run && run.status !== "running";
  const quantity = run?.quantity;
  const difference = quantity !== null && quantity !== undefined ? quantity - scenario.recommendation_units : null;
  return <section aria-labelledby="decision-title" className="overflow-hidden rounded-xl border bg-white">
    <div className="flex items-center justify-between gap-3 border-b px-5 py-4"><h2 id="decision-title" className="flex items-center gap-2 text-sm font-semibold"><Sparkles aria-hidden className="size-4 text-primary" />Agent decision</h2><StatusBadge run={run} /></div>
    <div className="p-5">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-xl border border-[#efeee8] bg-[#fafaf8] p-5">
        <div><p className="text-[11px] text-muted-foreground">Original recommendation</p><p className="mt-2 text-[30px] font-semibold leading-none tracking-tight tabular-nums">{number.format(scenario.recommendation_units)} <span className="text-xs font-normal text-muted-foreground">units</span></p></div>
        <ArrowRight aria-hidden className="size-5 text-[#b2b4a9]" />
        <div className="pl-2"><p className="text-[11px] text-muted-foreground">{run?.decision === "reject" ? "New purchase" : "Agent recommendation"}</p><p className={cn("mt-2 text-[30px] font-semibold leading-none tracking-tight tabular-nums", quantity !== null && quantity !== undefined ? "text-primary" : "text-[#b2b4a9]")}>{quantity !== null && quantity !== undefined ? number.format(quantity) : "—"} <span className="text-xs font-normal text-muted-foreground">units</span></p></div>
      </div>
      {run?.decision ? <div className="mt-4 flex flex-wrap items-center gap-2"><Badge variant="secondary" className="font-medium">{humanize(run.decision)}</Badge>{difference !== null && difference !== 0 ? <span className="flex items-center gap-1 text-xs text-muted-foreground">{difference < 0 ? <ArrowDownRight aria-hidden className="size-3.5" /> : <ArrowUpRight aria-hidden className="size-3.5" />}{number.format(Math.abs(difference))} units {difference < 0 ? "below" : "above"} original</span> : null}</div> : null}
      <div className="mt-4" aria-live="polite">
        <p className="text-sm leading-relaxed text-[#55594f]">{run?.summary || (run?.status === "running" ? "The agent is gathering stock, demand, supplier terms, and purchasing limits before making a decision." : "Run the review to check this recommendation against actual demand, incoming stock, and purchasing limits.")}</p>
      </div>
      {run?.purchase_order ? <OrderDetails order={run.purchase_order} /> : done ? <div className="mt-4 flex items-center gap-2 rounded-lg border border-dashed p-3 text-xs text-muted-foreground"><ShoppingBasket aria-hidden className="size-4" />No purchase order was created in this run.</div> : null}
      {!run ? <div className="mt-5 flex items-start gap-2 border-t pt-4 text-[11px] leading-relaxed text-muted-foreground"><ShieldCheck aria-hidden className="mt-0.5 size-3.5 shrink-0" />The agent can create a mock purchase. Budget, storage, and required evidence are checked before execution.</div> : null}
    </div>
  </section>;
}

function ValidationPanel({ run }: { run: Run | null }) {
  const validation = run?.validation;
  return <section aria-labelledby="validation-title" className="overflow-hidden rounded-xl border bg-white">
    <div className="flex items-center justify-between border-b px-5 py-4"><h2 id="validation-title" className="flex items-center gap-2 text-sm font-semibold"><CheckCheck aria-hidden className="size-4 text-muted-foreground" />Outcome validation</h2>{validation ? <Badge variant="outline" className={validation.passed ? "border-[#cbe4d3] bg-[#f0f8f2] text-[#277447]" : "border-[#ead8b2] bg-[#fff9eb] text-[#91661e]"}>{validation.passed ? "Checks passed" : "Action needed"}</Badge> : <span className="text-[10px] text-muted-foreground">{run?.status === "running" ? "Awaiting execution" : "No result yet"}</span>}</div>
    {validation ? <div className="p-5">{validation.shortage_units > 0 ? <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3"><p className="text-xs font-semibold text-amber-800">{number.format(validation.shortage_units)} units still uncovered</p><p className="mt-1 text-xs leading-relaxed text-amber-800">A buyer must resolve the remaining shortage. {run?.purchase_order ? "The confirmed order is shown above." : "No purchase was created; resolve the constraint before buying."}</p></div> : null}<ul className="space-y-3">{validation.checks.map((check, index) => <li key={`${check.name}-${index}`} className="flex items-start gap-2.5">{check.passed ? <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-[#478655]" /> : <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-amber-600" />}<div><p className="text-xs font-medium">{humanize(check.name)} <span className="sr-only">{check.passed ? "passed" : "failed"}</span></p><p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{check.detail}</p></div></li>)}</ul></div> : <div className="flex items-start gap-3 p-5"><div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted"><ClipboardCheck aria-hidden className="size-4 text-[#969b8a]" /></div><div><p className="text-xs font-medium">The result gets checked, too.</p><p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">After purchasing, the application rereads the saved order and checks supplier confirmation, spend, and stock coverage.</p></div></div>}
  </section>;
}

export function BuyerConsole() {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const actionLock = useRef(false);
  const isRunning = run?.status === "running";

  useEffect(() => {
    const controller = new AbortController();
    async function initialize() {
      try {
        const [list, service] = await Promise.all([api<ScenarioSummary[]>("/scenarios", { signal: controller.signal }), api<Health>("/health", { signal: controller.signal })]);
        const savedId = sessionStorage.getItem("buyer-active-run");
        let savedRun: Run | null = null;
        if (savedId) {
          try { savedRun = await api<Run>(`/runs/${encodeURIComponent(savedId)}`, { signal: controller.signal }); }
          catch (error) {
            if (!(error instanceof ApiError) || error.status !== 404) throw error;
            if (!controller.signal.aborted) sessionStorage.removeItem("buyer-active-run");
          }
        }
        const id = savedRun?.scenario_id || list.find((item) => item.id === "review-800")?.id || list[0]?.id;
        if (!id) throw new Error("No demo scenarios are available. Seed the purchasing service and retry.");
        const detail = await api<Scenario>(`/scenarios/${encodeURIComponent(id)}`, { signal: controller.signal });
        if (!controller.signal.aborted) { setScenarios(list); setHealth(service); setScenario(detail); setRun(savedRun); setError(null); }
      } catch (error) { if (!controller.signal.aborted) setError(message(error)); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void initialize();
    return () => controller.abort();
  }, [retry]);

  const activeRunId = isRunning ? run.id : null;
  useEffect(() => {
    if (!activeRunId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const nextRun = await api<Run>(`/runs/${encodeURIComponent(activeRunId!)}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setPollError(null);
        if (nextRun.status !== "running") {
          const detail = await api<Scenario>(`/scenarios/${encodeURIComponent(nextRun.scenario_id)}`, { signal: controller.signal });
          if (!controller.signal.aborted) { setScenario(detail); setRun(nextRun); }
          return;
        }
        setRun(nextRun);
      } catch (error) { if (!controller.signal.aborted) setPollError(`Progress connection lost. ${message(error)} Retrying automatically.`); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 1000);
    }
    timer = setTimeout(poll, 1000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [activeRunId]);

  const loadScenario = useCallback(async (id: string) => {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy(true); setError(null);
    try { const detail = await api<Scenario>(`/scenarios/${encodeURIComponent(id)}`); setScenario(detail); setRun(null); setPollError(null); sessionStorage.removeItem("buyer-active-run"); }
    catch (error) { setError(message(error)); }
    finally { actionLock.current = false; setBusy(false); }
  }, []);

  async function startRun() {
    if (!scenario || actionLock.current || isRunning) return;
    actionLock.current = true;
    setBusy(true); setError(null); setPollError(null);
    try {
      const nextRun = await api<Run>("/runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scenario_id: scenario.id }) });
      sessionStorage.setItem("buyer-active-run", nextRun.id);
      setRun(nextRun);
    } catch (error) { setError(message(error)); }
    finally { actionLock.current = false; setBusy(false); }
  }

  async function resetScenario() {
    if (!scenario || actionLock.current || isRunning) return;
    actionLock.current = true;
    setBusy(true); setError(null);
    try {
      const detail = await api<Scenario>(`/scenarios/${encodeURIComponent(scenario.id)}/reset`, { method: "POST" });
      setScenario(detail); setRun(null); setPollError(null); sessionStorage.removeItem("buyer-active-run");
    } catch (error) { setError(message(error)); }
    finally { actionLock.current = false; setBusy(false); }
  }

  const incoming = scenario?.open_pos.filter((order) => order.status === "confirmed").reduce((sum, order) => sum + order.quantity, 0) || 0;
  const completed = run?.status === "validated";
  const stage = !run ? 0 : run.validation ? 4 : run.purchase_order ? 3 : run.decision ? 2 : 1;

  return <div className="min-h-screen">
    <a href="#review" className="sr-only z-50 rounded bg-white p-3 focus:not-sr-only focus:fixed focus:left-4 focus:top-4">Skip to purchase review</a>
    <header className="border-b bg-white">
      <div className="mx-auto flex h-[72px] max-w-[1500px] items-center justify-between gap-3 px-5 lg:px-9">
        <div className="flex items-center gap-3"><div className="flex size-9 items-center justify-center rounded-xl bg-primary text-white"><ShoppingBasket aria-hidden className="size-5" /></div><span className="text-lg font-bold tracking-tight">buyer<span className="font-normal text-primary">.</span></span><span className="mx-1 hidden h-5 w-px bg-border sm:block" /><span className="hidden text-xs text-muted-foreground sm:block">Purchasing workspace</span></div>
        <div className="flex items-center gap-3"><span className="hidden items-center gap-1.5 text-[11px] text-muted-foreground sm:flex"><span className={cn("size-1.5 rounded-full", health?.model_configured ? "bg-[#6a9462]" : "bg-[#b9bcb0]")} />{health?.model_configured ? "Model configured" : health ? "Model not configured" : "Connecting to service"}</span><Badge variant="outline" className="rounded-md bg-[#fafaf8] px-2 py-1 text-[10px] font-medium text-muted-foreground">Mock purchasing</Badge></div>
      </div>
    </header>

    <div className="mx-auto grid max-w-[1500px] lg:grid-cols-[240px_minmax(0,1fr)] xl:grid-cols-[268px_minmax(0,1fr)]">
      <aside aria-label="Review controls" className="border-b bg-[#f3f3ef] p-5 lg:min-h-[calc(100vh-73px)] lg:border-r lg:border-b-0 lg:px-6 lg:py-8">
        <div className="flex items-center gap-2 rounded-lg border border-[#ead9d2] bg-[#f9eae4] px-3 py-2.5 text-xs font-semibold text-[#a64332]"><Layers3 aria-hidden className="size-4" />Recommendation review</div>
        <div className="mt-7"><label htmlFor="scenario" className="eyebrow mb-2 block text-muted-foreground">Demo scenario</label><div className="relative"><select id="scenario" className="w-full appearance-none rounded-lg border bg-white py-2.5 pr-8 pl-3 text-xs font-medium disabled:cursor-wait disabled:opacity-60" value={scenario?.id || ""} disabled={loading || busy || isRunning} onChange={(event) => void loadScenario(event.target.value)}><option value="" disabled>{loading ? "Loading scenarios…" : "Select a scenario"}</option>{scenarios.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChevronDown aria-hidden className="pointer-events-none absolute top-3 right-3 size-3.5 text-muted-foreground" /></div><p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground">{scenario?.description || "Select a purchasing situation to inspect its recommendation and supporting data."}</p></div>
        <div className="mt-7 hidden lg:block"><p className="eyebrow mb-4 text-muted-foreground">Review workflow</p><ol className="space-y-0">{[{ label: "Gather evidence", detail: "Stock, demand & supplier", icon: Search }, { label: "Make a decision", detail: "Check quantity & constraints", icon: Sparkles }, { label: "Execute purchase", detail: "Persist a valid order", icon: ShoppingBasket }, { label: "Verify outcome", detail: "Confirm actual results", icon: CheckCheck }].map((step, index) => <li key={step.label} className="relative flex gap-3 pb-6 last:pb-0">{index < 3 ? <span aria-hidden className="absolute top-7 bottom-0 left-3.5 w-px bg-[#dfe2d7]" /> : null}<span className={cn("relative flex size-7 shrink-0 items-center justify-center rounded-full border", stage > index + 1 || completed ? "border-[#d2dfcb] bg-[#e9f0e3] text-[#58814a]" : stage === index + 1 ? "border-[#ecc7bb] bg-[#f8e4dc] text-primary" : "border-[#ddded4] bg-[#f9f9f6] text-[#91968a]")}>{stage > index + 1 || completed ? <Check aria-hidden className="size-3.5" /> : <step.icon aria-hidden className="size-3.5" />}</span><div className="pt-0.5"><p className="text-[11px] font-semibold">{index === 2 && run && !isRunning && !run.purchase_order ? "No purchase created" : step.label}</p><p className="mt-1 text-[10px] text-muted-foreground">{index === 2 && run && !isRunning && !run.purchase_order ? "Execution skipped" : step.detail}</p></div></li>)}</ol></div>
        <div className="mt-8 hidden rounded-lg border border-[#e0e2d8] bg-[#f9faf6] p-3 lg:block"><div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold"><ShieldCheck aria-hidden className="size-3.5 text-[#789367]" />Guardrails on</div><p className="text-[10px] leading-relaxed text-muted-foreground">Purchases require complete evidence and must fit the available budget and storage.</p></div>
      </aside>

      <main id="review" className="min-w-0 px-5 py-7 lg:px-8 lg:py-8 xl:px-10">
        <div className="mb-2 flex items-center gap-1.5 text-[10px] text-muted-foreground"><span>Procurement</span><ChevronRight aria-hidden className="size-3" /><span className="text-[#55594f]">Purchase review</span></div>
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><h1 className="text-[28px] font-semibold tracking-[-.035em]">Purchase review</h1><p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">A recommendation is the starting point. Check the evidence, then buy.</p></div><div className="flex items-center gap-2"><Button variant="outline" size="sm" className="h-9 bg-white text-xs" onClick={() => void resetScenario()} disabled={!scenario || loading || busy || isRunning}><RotateCcw aria-hidden className="size-3.5" />Reset demo</Button><Button size="sm" className="h-9 gap-2 px-4 text-xs shadow-sm" onClick={() => void startRun()} disabled={!scenario || loading || busy || isRunning || !health?.model_configured}>{isRunning || busy ? <Loader2 aria-hidden className="size-3.5 animate-spin" /> : <Play aria-hidden className="size-3.5 fill-current" />}{isRunning ? "Reviewing…" : "Run agent review"}</Button></div></div>

        {error ? <Alert variant="destructive" className="mb-5 bg-white"><CircleAlert /><AlertTitle>Unable to complete the request</AlertTitle><AlertDescription><p>{error}</p><Button variant="outline" size="sm" className="mt-2 text-xs" disabled={busy || isRunning} onClick={() => { setLoading(true); setRetry((value) => value + 1); }}>Reconnect</Button></AlertDescription></Alert> : null}
        {pollError ? <Alert className="mb-5 border-amber-200 bg-amber-50 text-amber-900"><CircleAlert /><AlertTitle>Reconnecting to your run</AlertTitle><AlertDescription>{pollError}</AlertDescription></Alert> : null}
        {health && !health.model_configured ? <Alert className="mb-5 border-amber-200 bg-amber-50 text-amber-900"><CircleAlert /><AlertTitle>Model connection required</AlertTitle><AlertDescription>The purchasing service needs a configured model credential before a review can run.</AlertDescription></Alert> : null}

        {loading && !scenario ? <Card className="min-h-[300px] justify-center border-dashed shadow-none"><CardContent className="flex flex-col items-center gap-3 text-sm text-muted-foreground"><Loader2 aria-hidden className="size-6 animate-spin" /><p role="status">Loading purchasing evidence…</p></CardContent></Card> : scenario ? <>
          <section aria-label="Purchasing snapshot" className="mb-6 grid grid-cols-1 overflow-hidden rounded-xl border bg-white sm:grid-cols-4"><Metric label="Available inventory" value={number.format(scenario.inventory_units)} unit="units" detail={`${number.format(scenario.safety_stock_units)} units safety stock`} icon={Box} /><Metric label="Forecast demand" value={scenario.daily_demand_units === null ? "Missing" : number.format(scenario.daily_demand_units)} unit={scenario.daily_demand_units === null ? undefined : "/ day"} detail={`${scenario.lead_time_days + scenario.review_days}-day planning horizon`} icon={Layers3} /><Metric label="Existing incoming" value={number.format(incoming)} unit="units" detail={`${scenario.open_pos.length} existing purchase order${scenario.open_pos.length === 1 ? "" : "s"}`} icon={Truck} /><Metric label="Available budget" value={money(scenario.budget_cents)} detail="Existing commitments excluded" icon={Wallet} /></section>
          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,1fr)]"><div className="min-w-0 space-y-5"><DecisionPanel scenario={scenario} run={run} /><ValidationPanel run={run} />{run?.error ? <Alert variant="destructive" className="bg-white"><CircleAlert /><AlertTitle>Run needs attention</AlertTitle><AlertDescription>{run.error}</AlertDescription></Alert> : null}
            <section aria-labelledby="activity-title" className="overflow-hidden rounded-xl border bg-white"><div className="flex items-center justify-between gap-3 border-b px-5 py-4"><h2 id="activity-title" className="flex items-center gap-2 text-sm font-semibold"><Clock3 aria-hidden className="size-4 text-muted-foreground" />Agent activity</h2><span className="text-[10px] text-muted-foreground">{run?.events.length ? `${run.events.length} events` : "Live audit trail"}</span></div>{run?.events.length ? <div className="max-h-[450px] overflow-y-auto">{run.events.map((event) => <EventItem key={event.seq} event={event} />)}</div> : <div className="flex items-start gap-3 px-5 py-6"><span className="mt-1 flex size-5 items-center justify-center rounded-full border border-dashed"><Circle aria-hidden className="size-1.5 fill-[#adb1a3] text-[#adb1a3]" /></span><div><p className="text-xs font-medium">{isRunning ? "Starting the investigation" : "Ready when you are"}</p><p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{isRunning ? "Tool calls and results will appear as the agent works." : "Every tool call, decision, and verification result appears here after you start a review."}</p></div></div>}{isRunning ? <div role="status" className="flex items-center gap-2 border-t bg-[#fff9f5] px-5 py-3 text-[11px] text-[#b66348]"><span className="agent-pulse size-1.5 rounded-full bg-primary" />Agent is working. Results update automatically.</div> : null}</section>
          </div><div className="min-w-0 space-y-5"><EvidencePanel scenario={scenario} />{scenario.purchase_orders.length > 0 && !run?.purchase_order ? <section className="rounded-xl border bg-white p-5"><h2 className="text-sm font-semibold">Scenario purchase orders</h2><p className="mt-1 text-[11px] text-muted-foreground">Orders already persisted for this scenario.</p>{scenario.purchase_orders.map((order) => <OrderDetails key={order.id} order={order} />)}</section> : null}<div className="flex items-start gap-2.5 px-1 text-[10px] leading-relaxed text-muted-foreground"><Clock3 aria-hidden className="mt-0.5 size-3.5 shrink-0" /><p>Fixed-clock demo. Day 1 is the next simulated day. Incoming stock arrives before that day’s demand.</p></div></div></div>
          <footer className="mt-7 flex flex-wrap items-center justify-between gap-2 border-t pt-4 text-[10px] text-muted-foreground"><span>Buyer agent · Evidence before execution</span><span className="flex min-w-0 items-center gap-1.5"><span className="size-1 rounded-full bg-[#8c9580]" /><span className="truncate">{run?.model || health?.model || "Model pending"}</span>{run ? <span className="ml-2 font-mono" title={run.id}>Run {run.id.slice(0, 8)}</span> : null}</span></footer>
        </> : null}
      </main>
    </div>
  </div>;
}
