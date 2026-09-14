"""Fixed-day scenarios. Evaluation expectations deliberately live elsewhere."""

from copy import deepcopy

BASE = {
    "recommendation_units": 800,
    "inventory_units": 500,
    "daily_demand_units": 100,
    "lead_time_days": 3,
    "review_days": 7,
    "safety_stock_units": 100,
    "moq_units": 100,
    "pack_size_units": 50,
    "unit_cost_cents": 500,
    "budget_cents": 500000,
    "capacity_units": 1500,
    "open_pos": [{"id": "IN-1042", "quantity": 200, "arrival_day": 2, "status": "confirmed"}],
    "supplier_behavior": "confirm",
}


def fixtures():
    definitions = [
        ("review-800", "Review the 800-unit recommendation", "Check inventory, incoming supply, demand and purchasing limits before acting.", "review", {}),
        ("accept-800", "Lower inventory", "Review the same recommendation with fewer units on hand.", "review", {"inventory_units": 100}),
        ("sufficient-stock", "Stock already available", "Determine whether existing stock and incoming supply cover the planning period.", "review", {"inventory_units": 1000}),
        ("late-incoming", "Incoming shipment delayed", "An existing purchase order arrives on day 12. Assess its effect on coverage.", "review", {"open_pos": [{"id": "IN-1042", "quantity": 200, "arrival_day": 12, "status": "confirmed"}]}),
        ("budget-limit", "Budget restriction", "Available purchasing budget has been reduced to $1,000.", "constraint", {"budget_cents": 100000}),
        ("storage-limit", "Storage restriction", "The node has capacity for 750 units.", "constraint", {"capacity_units": 750}),
        ("missing-demand", "Demand data unavailable", "The demand service has no current forecast for this product.", "evidence", {"daily_demand_units": None}),
        ("supplier-shortfall", "Supplier confirmation mismatch", "Compare the supplier's confirmed delivery with the purchase request.", "feedback", {"supplier_behavior": "partial"}),
        ("timeout-after-commit", "Purchase response interrupted", "Recover the actual purchase outcome after the supplier connection times out.", "feedback", {"supplier_behavior": "timeout_after_commit"}),
        ("changed-budget", "Budget changes before purchase", "Another commitment consumes budget after assessment and before execution.", "constraint", {"supplier_behavior": "budget_changed"}),
    ]
    return [dict(deepcopy(BASE), id=sid, title=title, description=description, category=category, **changes)
            for sid, title, description, category, changes in definitions]
