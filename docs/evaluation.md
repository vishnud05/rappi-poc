# Evaluation

Tests judge purchasing behavior and persisted state. They do not compare the model's wording with a reference answer.

## Required cases

All cases use a fixed simulated clock. Incoming shipments arrive before that day's demand.

| Case | Expected decision and quantity | Expected state |
| --- | --- | --- |
| `review-800` | Modify to 400 | One verified order; $2,000 committed |
| `accept-800` | Accept 800 | One verified order when constraints pass |
| `sufficient-stock` | Reject; zero new units | No purchase or budget change |
| `late-incoming` | Modify to 600 | Shipment outside the horizon does not reduce need |
| `budget-limit` | Investigate | No purchase or budget change |
| `storage-limit` | Investigate | No purchase or budget change |
| `missing-demand` | Investigate | Missing information is explicit; no purchase |
| `supplier-shortfall` | Request 400; confirm 200 | $1,000 committed; 200-unit shortage; human review |
| Duplicate purchase call | Recover the same order | One order and one budget deduction |
| `timeout-after-commit` | Recover the existing order | One order and one budget deduction |
| `changed-budget` | Reassess and investigate | No new order after budget falls below the requirement |

The budget and storage cases test whether the complete required purchase is feasible. The agent does not silently reduce quantities to fit a constraint and then claim the need is covered.

## What a pass means

- Evidence coverage: read stock and incoming orders, demand, supplier terms, and constraints before a purchase.
- Decision correctness: choose the expected action and quantity from the scenario's data.
- Constraint compliance: respect minimum order, pack size, delivery timing, budget, and peak storage occupancy.
- Action correctness: persist the expected requested and confirmed quantities, spend, and incoming supply without duplicate writes.
- Verification: independently read actual order state and report whether the purchase covers the need. Partial fulfillment must fail coverage and require review.

Deterministic tests cover policy arithmetic, persistence, transaction behavior, and failure recovery. Live evaluation sends scenario data through the actual model and checks the same observable outcomes. Evaluation labels and expected answers are not model inputs.

## Run the checks

From the repository root:

```sh
uv run python -m unittest discover -s backend/tests -v
pnpm test:frontend
pnpm typecheck
pnpm lint
pnpm build
uv run --env-file .env python -m backend.evaluate --output docs/evaluation-results.json
```

The application tests need no model credential. The final command calls the configured Gemini model and writes a JSON report. Omit `--env-file .env` if credentials are already present in the process environment. Evaluation starts are spaced by at least 65 seconds by default; `--delay-seconds 0` disables pacing when your quota permits it. Select individual cases with repeated `--scenario` arguments. Provider quota exhaustion stops the suite and marks remaining cases as unrun.

## Results

Measured on September 14, 2026:

| Check | Observed result |
| --- | --- |
| Backend unittest suite | 16 tests passed, including all fixture outcomes, forged assessments, duplicate writes, receipt timing, interrupted runs, and the 12-turn limit |
| Frontend HTTP test | Passed success, missing-run, conflict, provider-unavailable, and invalid-proxy-response cases |
| Type checking, ESLint, production build | Passed |
| Browser main workflow | Gemini 2.5 Flash modified 800 to 400, confirmed 400, committed $2,000, and passed all seven verification checks |
| Browser supplier shortfall | Gemini 3.1 Flash-Lite requested 400, confirmed 200, committed $1,000, detected a 200-unit gap, and required buyer review |
| Browser integration | Scenario selection, reset, disabled run controls, production reload recovery, and native keyboard navigation passed; no browser console errors observed |
| Responsive layout | At a 390-pixel viewport the document width was 375 pixels, with no horizontal overflow |

The successful browser runs are retained as [main](demo-assets/main-live-run.json) and [shortfall](demo-assets/shortfall-live-run.json) audit records. The [captured walkthrough](demo.md#captured-live-run) shows actual UI states.

The complete live suite did **not** pass. Gemini 2.5 Flash reached its 20-request daily free-tier quota. A subsequent Gemini 3.1 Flash-Lite evaluation encountered four consecutive provider 503 failures before any tool executed, so six cases were left unrun. [Initial report](evaluation-initial.json).

The final SDK configuration retries 502/503/504 generation failures once, within the 120-second run limit, and does not retry 429 quota failures. A [main-case retry](evaluation-retry.json) created the correct 400-unit order and independently passed all seven checks, but a later provider 503 prevented the model from finishing. The application retained the order and ended as `needs_review`. A [separate alternative-model attempt](evaluation-alternative.json) also received 503 before tool execution. These reports are preserved rather than replaced with claimed passes.

The deterministic suite verifies purchasing behavior across all ten fixtures. Successful live runs establish the main and shortfall workflows; provider availability prevented complete live-model coverage. Re-run the live command with available quota before presenting a fresh live demo, and retain the captured walkthrough as backup.

## Browser acceptance

Check scenario selection, source data, the active-run timeline, purchase details, verification failures, reset, keyboard access, and a narrow viewport. Also run frontend type checking, linting, and a production build. A frontend build passing alone does not prove the purchasing workflow works.
