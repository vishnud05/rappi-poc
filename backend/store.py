"""SQLite owns state transitions, the audit trail and purchasing atomicity."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from backend.fixtures import fixtures
from backend.policy import assess, projection


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self, recover=True):
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL,
                    status TEXT NOT NULL, data TEXT NOT NULL, baseline TEXT NOT NULL);
                -- ponytail: one active buyer globally; use scoped leases for multiple buyers.
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(status) WHERE status='running';
                CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
                    detail TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assessments (id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                    data TEXT NOT NULL, snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
                    scenario_id TEXT NOT NULL, data TEXT NOT NULL);
            """)
            for fixture in fixtures():
                db.execute("INSERT OR IGNORE INTO scenarios VALUES (?, ?)", (fixture["id"], json.dumps(fixture)))
        if recover:
            with self.connection() as db:
                interrupted = [row[0] for row in db.execute("SELECT id FROM runs WHERE status='running'")]
            for rid in interrupted:
                po = self.order(rid)
                if po:
                    self.verify(rid)
                self.event(rid, "error", "interrupted", {"message": "Server restarted during this run. Review persisted state before starting another purchase."})
                self.update_run(rid, status="needs_review", decision="investigate", finished_at=now(),
                                error="Run interrupted by server restart.", summary="Run interrupted. Any persisted order was retained and checked; buyer review is required.")

    def scenario(self, sid, db=None):
        if db is None:
            with self.connection() as conn:
                return self.scenario(sid, conn)
        row = db.execute("SELECT data FROM scenarios WHERE id=?", (sid,)).fetchone()
        if not row:
            raise NotFound("Scenario not found.")
        data = json.loads(row[0])
        data["purchase_orders"] = [json.loads(row[0]) for row in db.execute("SELECT data FROM orders WHERE scenario_id=? ORDER BY rowid", (sid,))]
        return data

    def scenarios(self):
        keys = ("id", "title", "description", "category", "recommendation_units")
        with self.connection() as db:
            return [{key: data[key] for key in keys} for row in db.execute("SELECT data FROM scenarios ORDER BY rowid") for data in [json.loads(row[0])]]

    def reset(self, sid):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
                raise Conflict("A run is active. Wait for it to finish before resetting.")
            fixture = next((s for s in fixtures() if s["id"] == sid), None)
            if not fixture:
                raise NotFound("Scenario not found.")
            db.execute("UPDATE scenarios SET data=? WHERE id=?", (json.dumps(fixture), sid))
            db.execute("DELETE FROM orders WHERE scenario_id=?", (sid,))
        return self.scenario(sid)

    def start_run(self, sid, model):
        rid = str(uuid4())
        run = {"id": rid, "scenario_id": sid, "status": "running", "decision": None,
               "quantity": None, "summary": "Gathering purchasing evidence.", "model": model,
               "created_at": now(), "finished_at": None, "error": None,
               "events": [], "purchase_order": None, "validation": None}
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            baseline = self.scenario(sid, db)
            if db.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
                raise Conflict("Another purchasing run is active. Wait for it to finish.")
            db.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?)", (rid, sid, "running", json.dumps(run), json.dumps(baseline)))
        self.event(rid, "info", "run_started", {"message": "Live agent started. Purchasing services are simulated; model calls are real."})
        return self.run(rid)

    def run(self, rid):
        with self.connection() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (rid,)).fetchone()
            if not row:
                raise NotFound("Run not found.")
            data = json.loads(row[0])
            data["events"] = [dict(row, detail=json.loads(row["detail"])) for row in db.execute("SELECT seq,kind,name,detail,created_at FROM events WHERE run_id=? ORDER BY seq", (rid,))]
            return data

    def update_run(self, rid, **updates):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM runs WHERE id=?", (rid,)).fetchone()
            if not row:
                raise NotFound("Run not found.")
            data = json.loads(row[0])
            data.update(updates)
            db.execute("UPDATE runs SET status=?,data=? WHERE id=?", (data["status"], json.dumps(data), rid))

    def event(self, rid, kind, name, detail):
        with self.connection() as db:
            db.execute("INSERT INTO events (run_id,kind,name,detail,created_at) VALUES (?, ?, ?, ?, ?)", (rid, kind, name, json.dumps(detail), now()))

    def save_assessment(self, rid, result, snapshot):
        aid = str(uuid4())
        with self.connection() as db:
            db.execute("INSERT INTO assessments VALUES (?, ?, ?, ?)", (aid, rid, json.dumps(result), json.dumps(snapshot, sort_keys=True)))
        return dict(result, assessment_id=aid)

    def order(self, rid, db=None):
        if db is None:
            with self.connection() as conn:
                return self.order(rid, conn)
        row = db.execute("SELECT data FROM orders WHERE run_id=?", (rid,)).fetchone()
        return json.loads(row[0]) if row else None

    def purchase(self, rid, aid):
        """The run ID is the server-issued idempotency key, enforced by UNIQUE."""
        timeout = False
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = self.order(rid, db)
            if existing:
                return {"purchase_order": existing, "recovered_existing": True}
            runrow = db.execute("SELECT scenario_id,status FROM runs WHERE id=?", (rid,)).fetchone()
            if not runrow or runrow["status"] != "running":
                return {"error": "This run is no longer active."}
            row = db.execute("SELECT data,snapshot FROM assessments WHERE id=? AND run_id=?", (aid, rid)).fetchone()
            if not row:
                return {"error": "Unknown assessment. Assess the purchase first."}
            assessment = json.loads(row["data"])
            if not assessment.get("evidence_complete") or not assessment["executable"]:
                return {"error": "This assessment does not authorize a purchase."}
            sid = runrow["scenario_id"]
            current = self.scenario(sid, db)
            if current["supplier_behavior"] == "budget_changed":
                current["budget_cents"] = 100000
                current["supplier_behavior"] = "confirm"
                current.pop("purchase_orders", None)
                db.execute("UPDATE scenarios SET data=? WHERE id=?", (json.dumps(current), sid))
                return {"error": "Budget changed before execution. No purchase was created. Refresh constraints and reassess."}
            if json.dumps(current, sort_keys=True) != row["snapshot"]:
                return {"error": "Purchasing data changed. Refresh evidence and reassess before buying."}
            checked = assess(current)
            if not checked["executable"] or checked["quantity"] != assessment["quantity"]:
                return {"error": "Current constraints no longer allow this purchase.", "assessment": checked}
            quantity = checked["quantity"]
            confirmed = quantity // 2 if current["supplier_behavior"] == "partial" else quantity
            po = {"id": "PO-" + uuid4().hex[:8].upper(), "requested_units": quantity,
                  "confirmed_units": confirmed, "unit_cost_cents": current["unit_cost_cents"],
                  "total_cost_cents": confirmed * current["unit_cost_cents"],
                  "arrival_day": current["lead_time_days"],
                  "status": "partially_confirmed" if confirmed < quantity else "confirmed"}
            db.execute("INSERT INTO orders VALUES (?, ?, ?, ?)", (po["id"], rid, sid, json.dumps(po)))
            current["budget_cents"] -= po["total_cost_cents"]
            current["open_pos"].append({"id": po["id"], "quantity": confirmed, "arrival_day": po["arrival_day"], "status": "confirmed"})
            current.pop("purchase_orders", None)
            db.execute("UPDATE scenarios SET data=? WHERE id=?", (json.dumps(current), sid))
            timeout = current["supplier_behavior"] == "timeout_after_commit"
        self.update_run(rid, purchase_order=po)
        self.event(rid, "action", "purchase_persisted", {"purchase_order": po})
        if timeout:
            return {"error": "Supplier request timed out; creation outcome is unknown. Call lookup_purchase before any retry.", "outcome_unknown": True}
        return {"purchase_order": po, "recovered_existing": False}

    def verify(self, rid):
        """Read actual committed state; never trust a model's purchase result."""
        with self.connection() as db:
            row = db.execute("SELECT scenario_id,baseline FROM runs WHERE id=?", (rid,)).fetchone()
            if not row:
                raise NotFound("Run not found.")
            current = self.scenario(row["scenario_id"], db)
            baseline = json.loads(row["baseline"])
            po = self.order(rid, db)
        checks = []
        def check(name, passed, detail):
            checks.append({"name": name, "passed": bool(passed), "detail": detail})
        check("Order persisted", po is not None, po["id"] if po else "No purchase order exists for this run.")
        shortage = 0
        if po:
            required = assess(baseline)
            terms_match = (required["executable"] and po["requested_units"] == required["quantity"]
                           and po["unit_cost_cents"] == baseline["unit_cost_cents"]
                           and po["arrival_day"] == baseline["lead_time_days"]
                           and po["requested_units"] >= baseline["moq_units"]
                           and po["requested_units"] % baseline["pack_size_units"] == 0
                           and 0 <= po["confirmed_units"] <= po["requested_units"])
            check("Purchase terms", terms_match, "Requested quantity, unit price, delivery day and order increments must match the assessed purchasing terms.")
            check("Supplier confirmation", po["requested_units"] == po["confirmed_units"], f"Requested {po['requested_units']} units; supplier confirmed {po['confirmed_units']}.")
            expected_cost = po["confirmed_units"] * baseline["unit_cost_cents"]
            check("Spend reconciled", po["total_cost_cents"] == expected_cost and current["budget_cents"] == baseline["budget_cents"] - expected_cost and current["budget_cents"] >= 0,
                  f"Committed {po['total_cost_cents']} cents; remaining budget {current['budget_cents']} cents.")
            receipts = [p for p in current["open_pos"] if p["id"] == po["id"]]
            check("Incoming supply persisted", len(receipts) == 1 and receipts[0]["quantity"] == po["confirmed_units"] and receipts[0]["arrival_day"] == po["arrival_day"] and receipts[0]["status"] == "confirmed", "Confirmed supply must appear exactly once in incoming inventory.")
            if current["daily_demand_units"] is not None:
                projected = projection(current)
                shortage = max(0, current["safety_stock_units"] - projected["ending_units"])
                check("Demand coverage", shortage == 0 and not projected["stockout_days"], f"End stock {projected['ending_units']}; target safety stock {current['safety_stock_units']}; shortage {shortage} units.")
                check("Storage capacity", projected["peak_units"] <= current["capacity_units"], f"Peak {projected['peak_units']} units; capacity {current['capacity_units']}.")
            else:
                check("Demand coverage", False, "Demand forecast unavailable during verification.")
        result = {"passed": all(c["passed"] for c in checks), "checks": checks, "shortage_units": shortage}
        self.update_run(rid, validation=result, purchase_order=po)
        self.event(rid, "validation", "verify_outcome", result)
        return result
