"""Purchasing arithmetic is deterministic and independent of the model."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Incoming(BaseModel):
    id: str
    quantity: int = Field(ge=0, strict=True)
    arrival_day: int = Field(ge=1, strict=True)
    status: str


class PurchasingInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    inventory_units: int = Field(ge=0, strict=True)
    daily_demand_units: int | None = Field(ge=0, strict=True)
    lead_time_days: int = Field(ge=1, le=365, strict=True)
    review_days: int = Field(ge=0, le=365, strict=True)
    safety_stock_units: int = Field(ge=0, strict=True)
    moq_units: int = Field(ge=1, strict=True)
    pack_size_units: int = Field(ge=1, strict=True)
    unit_cost_cents: int = Field(gt=0, strict=True)
    budget_cents: int = Field(ge=0, strict=True)
    capacity_units: int = Field(ge=0, strict=True)
    open_pos: list[Incoming]


def projection(data: dict, new_quantity: int = 0) -> dict:
    """Receipts arrive before demand. Negative stock carries unmet demand forward."""
    horizon = data["lead_time_days"] + data["review_days"]
    receipts = {}
    for po in data["open_pos"]:
        if po["status"] == "confirmed" and po["arrival_day"] <= horizon:
            receipts[po["arrival_day"]] = receipts.get(po["arrival_day"], 0) + po["quantity"]
    if new_quantity:
        day = data["lead_time_days"]
        receipts[day] = receipts.get(day, 0) + new_quantity
    inventory = data["inventory_units"]
    peak = inventory
    stockout_days = []
    daily = []
    for day in range(1, horizon + 1):
        receipt = receipts.get(day, 0)
        inventory += receipt
        peak = max(peak, inventory)
        inventory -= data["daily_demand_units"]
        if inventory < 0:
            stockout_days.append(day)
        daily.append({"day": day, "received_units": receipt, "closing_units": inventory})
    return {"horizon_days": horizon, "ending_units": inventory, "peak_units": peak,
            "stockout_days": stockout_days, "daily": daily}


def assess(data: dict) -> dict:
    try:
        validated = PurchasingInput.model_validate(data)
    except ValidationError:
        return {"quantity": 0, "executable": False, "blockers": ["Purchasing evidence is invalid or incomplete."], "projection": None}
    if validated.daily_demand_units is None:
        return {"quantity": 0, "executable": False, "blockers": ["Current demand forecast is missing."], "projection": None}
    horizon = data["lead_time_days"] + data["review_days"]
    incoming = sum(po["quantity"] for po in data["open_pos"]
                   if po["status"] == "confirmed" and po["arrival_day"] <= horizon)
    raw = max(0, data["daily_demand_units"] * horizon + data["safety_stock_units"] - data["inventory_units"] - incoming)
    pack = data["pack_size_units"]
    quantity = ((max(raw, data["moq_units"]) + pack - 1) // pack) * pack if raw else 0
    projected = projection(data, quantity)
    cost = quantity * data["unit_cost_cents"]
    blockers = []
    if cost > data["budget_cents"]:
        blockers.append(f"Purchase costs {cost} cents; only {data['budget_cents']} cents remain.")
    if projected["peak_units"] > data["capacity_units"]:
        blockers.append(f"Peak inventory {projected['peak_units']} exceeds capacity {data['capacity_units']}.")
    if projected["stockout_days"]:
        blockers.append(f"Stockout projected on day {projected['stockout_days'][0]}; the purchase cannot prevent every stockout.")
    return {"quantity": quantity, "unrounded_units": raw, "eligible_incoming_units": incoming,
            "total_cost_cents": cost, "executable": not blockers and quantity > 0,
            "blockers": blockers, "projection": projected}
