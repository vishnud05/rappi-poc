# Implementation contract

The browser calls `/api/*` through Next.js rewrites to FastAPI on port 8000.
All quantities are integer units and all money is integer cents. Scenario time
is fixed; day 1 is the next simulated day. Receipts arrive before daily demand.

## HTTP endpoints

- `GET /api/health`: `{status, model, model_configured}`. Never return secrets.
- `GET /api/scenarios`: an array of scenario summaries.
- `GET /api/scenarios/{id}`: full scenario data below.
- `POST /api/runs`: JSON `{scenario_id}`; returns HTTP 202 with a Run.
- `GET /api/runs/{id}`: Run, including persisted events.
- `POST /api/scenarios/{id}/reset`: reset that scenario and return its detail.
- Errors: JSON `{detail: string}` with an appropriate HTTP status.
- One active run globally. Concurrent start or reset while active returns 409.

## Scenario

Summary: `id`, `title`, `description`, `category`, `recommendation_units`.
Detail adds `inventory_units`, `daily_demand_units` (nullable),
`lead_time_days`, `review_days`, `safety_stock_units`, `moq_units`,
`pack_size_units`, `unit_cost_cents`, `budget_cents`, `capacity_units`,
`open_pos`: array of `{id, quantity, arrival_day, status}`,
`supplier_behavior`, and `purchase_orders`: array of PurchaseOrder.
Categories: `review`, `constraint`, `feedback`, `evidence`.
Main fixture ID: `review-800`. Model tools must never receive evaluation
expectations, scenario descriptions that reveal expected answers, or test labels.

## Run

`id`, `scenario_id`, `status`: `running | validated | needs_review | failed`,
`decision`: nullable `accept | modify | reject | investigate`,
`quantity`: nullable integer, `summary`: string, `model`: string,
`created_at`, `finished_at`: nullable timestamp, `error`: nullable string,
`events`: Event[], `purchase_order`: nullable PurchaseOrder,
`validation`: nullable Validation.

Event: `seq`, `kind`: `tool_call | tool_result | decision | action | validation | error | info`,
`name`, `detail`: arbitrary JSON, `created_at`.

PurchaseOrder: `id`, `requested_units`, `confirmed_units`, `unit_cost_cents`,
`total_cost_cents`, `arrival_day`, `status`.

Validation: `passed`: boolean, `checks`: array of `{name, passed, detail}`,
`shortage_units`: integer.

## Behavior

Main fixture: inventory 500, demand 100/day, incoming 200 on day 2,
lead 3 days, review 7 days, safety stock 100, MOQ 100, pack 50,
unit cost 500 cents, remaining budget 500000 cents, capacity 1500.
Expected new purchase is 400 units. Initial recommendation is 800.
Only confirmed incoming receipts within the horizon count toward need.
Existing commitments are already excluded from remaining budget.
Persist orders and budget changes atomically and make purchase calls idempotent.
Partial supplier confirmation is final for this mock order, so charge only the
confirmed quantity. Its unfulfilled remainder must be reported for human review.

The LLM investigates via tools, proposes an assessment, executes a valid
assessment, and receives independent post-action verification. Application code
enforces evidence completeness and constraints. A run cannot claim successful
purchasing without verification. No scripted fallback may masquerade as AI.

Use `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-3.1-flash-lite`),
`DATABASE_PATH` (default `data/purchasing.db`), and frontend-only server setting
`BACKEND_URL` (default `http://127.0.0.1:8000`).
