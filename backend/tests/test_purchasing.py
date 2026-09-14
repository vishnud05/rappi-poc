import asyncio
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.agent import AgentTools, EVIDENCE, NIM_BASE_URL, run_agent
from backend.fixtures import fixtures
from backend.policy import assess, projection
from backend.store import Conflict, Store


class PurchasingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.db")
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def prepared(self, sid="review-800"):
        run = self.store.start_run(sid, "test-model")
        tools = AgentTools(self.store, run["id"])
        for name in sorted(EVIDENCE):
            tools.call(name, {})
        result = tools.call("assess_purchase", {"proposed_quantity": 800, "rationale": "Review current recommendation."})
        return run["id"], tools, result

    def purchase(self, sid="review-800"):
        rid, tools, assessment = self.prepared(sid)
        decision = "accept" if assessment["quantity"] == 800 else "modify"
        result = tools.call("record_decision", {"assessment_id": assessment["assessment_id"], "decision": decision,
                        "quantity": assessment["quantity"], "rationale": "Calculated against current evidence."})
        self.assertTrue(result["recorded"])
        result = tools.call("create_purchase", {"assessment_id": assessment["assessment_id"]})
        return rid, tools, assessment, result

    def test_policy_outcomes(self):
        expected = {"review-800": (400, True), "accept-800": (800, True), "sufficient-stock": (0, False),
                    "late-incoming": (600, True), "budget-limit": (400, False), "storage-limit": (400, False),
                    "missing-demand": (0, False)}
        for data in fixtures():
            if data["id"] in expected:
                with self.subTest(scenario=data["id"]):
                    result = assess(data)
                    self.assertEqual((result["quantity"], result["executable"]), expected[data["id"]])

    def test_order_rounding_and_unconfirmed_receipts(self):
        data = self.store.scenario("review-800")
        data["inventory_units"] = 549
        self.assertEqual(assess(data)["quantity"], 400)
        data["inventory_units"] = 899
        self.assertEqual(assess(data)["quantity"], 100)
        data["open_pos"][0]["status"] = "pending"
        self.assertEqual(assess(data)["quantity"], 250)

    def test_receipt_timing_blocks_stockout_despite_sufficient_total(self):
        data = self.store.scenario("review-800")
        data["inventory_units"] = 0
        data["open_pos"] = [{"id": "late", "quantity": 1500, "arrival_day": 10, "status": "confirmed"}]
        result = assess(data)
        self.assertEqual(result["quantity"], 0)
        self.assertTrue(result["blockers"])
        self.assertEqual(result["projection"]["stockout_days"][0], 1)

    def test_invalid_evidence_and_missing_demand_block(self):
        data = self.store.scenario("review-800")
        for field, value in [("pack_size_units", 0), ("daily_demand_units", None), ("unit_cost_cents", -5), ("inventory_units", "500")]:
            with self.subTest(field=field):
                changed = dict(data, **{field: value})
                self.assertFalse(assess(changed)["executable"])

    def test_purchase_atomicity_verification_and_idempotency(self):
        rid, tools, assessment, result = self.purchase()
        self.assertEqual(result["purchase_order"]["confirmed_units"], 400)
        repeat = tools.call("create_purchase", {"assessment_id": assessment["assessment_id"]})
        self.assertEqual(repeat["purchase_order"]["id"], result["purchase_order"]["id"])
        state = self.store.scenario("review-800")
        self.assertEqual(state["budget_cents"], 300000)
        self.assertEqual(len(state["purchase_orders"]), 1)
        self.assertEqual(len(state["open_pos"]), 2)
        self.assertTrue(tools.call("verify_outcome", {})["passed"])
        self.assertEqual(tools.call("finish_run", {"summary": "Purchased and verified 400 units."})["status"], "validated")
        # A second review sees the committed incoming receipt and buys nothing.
        rid2, tools2, result2 = self.prepared()
        self.assertEqual(result2["quantity"], 0)
        self.assertEqual(projection(self.store.scenario("review-800"))["ending_units"], 100)

    def test_supplier_shortfall_and_actual_spend(self):
        rid, tools, assessment, result = self.purchase("supplier-shortfall")
        self.assertEqual(result["purchase_order"]["confirmed_units"], 200)
        self.assertEqual(self.store.scenario("supplier-shortfall")["budget_cents"], 400000)
        verified = tools.call("verify_outcome", {})
        self.assertFalse(verified["passed"])
        self.assertEqual(verified["shortage_units"], 200)
        self.assertEqual(tools.call("finish_run", {"summary": "Supplier confirmed 200; 200 units still missing."})["status"], "needs_review")

    def test_timeout_requires_lookup_and_never_duplicates(self):
        rid, tools, assessment, result = self.purchase("timeout-after-commit")
        self.assertTrue(result["outcome_unknown"])
        self.assertIn("error", tools.call("create_purchase", {"assessment_id": assessment["assessment_id"]}))
        found = tools.call("lookup_purchase", {})
        repeated = tools.call("create_purchase", {"assessment_id": assessment["assessment_id"]})
        self.assertEqual(found["purchase_order"]["id"], repeated["purchase_order"]["id"])
        self.assertEqual(self.store.scenario("timeout-after-commit")["budget_cents"], 300000)
        self.assertTrue(tools.call("verify_outcome", {})["passed"])

    def test_changed_budget_stops_write_and_requires_reassessment(self):
        rid, tools, assessment, result = self.purchase("changed-budget")
        self.assertIn("error", result)
        self.assertIsNone(self.store.order(rid))
        tools.call("read_constraints", {})
        revised = tools.call("assess_purchase", {"proposed_quantity": 400, "rationale": "Reassess after budget changed."})
        self.assertFalse(revised["executable"])
        self.assertTrue(revised["blockers"])

    def test_forged_assessment_and_missing_evidence_cannot_purchase(self):
        run = self.store.start_run("review-800", "test-model")
        tools = AgentTools(self.store, run["id"])
        self.assertIn("error", tools.call("assess_purchase", {"proposed_quantity": 400, "rationale": "Guess."}))
        self.assertIn("error", tools.call("create_purchase", {"assessment_id": "forged"}))
        self.assertIn("error", self.store.purchase(run["id"], "forged"))
        self.assertIn("error", tools.call("finish_run", {"summary": "Success."}))
        self.assertIsNone(self.store.order(run["id"]))

    def test_cannot_finish_purchase_before_verification(self):
        rid, tools, assessment, result = self.purchase()
        self.assertIn("error", tools.call("finish_run", {"summary": "Success."}))
        self.assertEqual(self.store.run(rid)["status"], "running")
        tools.call("verify_outcome", {})
        self.assertIn("error", tools.call("finish_run", {"summary": "Success."}, feedback_pending=True))
        self.assertEqual(self.store.run(rid)["status"], "running")
        self.assertEqual(tools.call("finish_run", {"summary": "Verified 400 confirmed units."})["status"], "validated")

    def test_purchase_decision_cannot_be_rewritten_after_execution(self):
        rid, tools, assessment, result = self.purchase()
        next_assessment = tools.call("assess_purchase", {"proposed_quantity": 0, "rationale": "Incoming supply includes our new order."})
        changed = tools.call("record_decision", {"assessment_id": next_assessment["assessment_id"], "decision": "reject",
                                               "quantity": 0, "rationale": "No additional units needed."})
        self.assertIn("error", changed)
        self.assertEqual(self.store.run(rid)["decision"], "modify")
        self.assertEqual(self.store.run(rid)["quantity"], 400)

    def test_verifier_detects_tampered_purchase_terms(self):
        rid, tools, assessment, result = self.purchase()
        po = result["purchase_order"]
        po["arrival_day"] += 1
        with self.store.connection() as db:
            db.execute("UPDATE orders SET data=? WHERE run_id=?", (json.dumps(po), rid))
        result = tools.call("verify_outcome", {})
        self.assertFalse(result["passed"])
        self.assertFalse(next(c for c in result["checks"] if c["name"] == "Purchase terms")["passed"])

    def test_single_active_run_reset_and_restart_recovery(self):
        rid, tools, assessment, result = self.purchase()
        with self.assertRaises(Conflict):
            self.store.start_run("accept-800", "test-model")
        with self.assertRaises(Conflict):
            self.store.reset("review-800")
        self.store.initialize()
        run = self.store.run(rid)
        self.assertEqual(run["status"], "needs_review")
        self.assertIsNotNone(run["purchase_order"])
        self.assertTrue(run["validation"]["passed"])
        self.store.reset("review-800")
        self.assertEqual(self.store.scenario("review-800")["budget_cents"], 500000)
        self.assertIsNotNone(self.store.run(rid)["purchase_order"])

    def test_missing_key_is_visible_failure(self):
        run = self.store.start_run("review-800", "test-model")
        with patch.dict("os.environ", {"NVIDIA_API_KEY": ""}):
            asyncio.run(run_agent(self.store, run["id"]))
        self.assertEqual(self.store.run(run["id"])["status"], "failed")
        self.assertIn("NVIDIA_API_KEY", self.store.run(run["id"])["error"])

    def test_unproductive_model_stops_at_twelve_turns(self):
        run = self.store.start_run("review-800", "test-model")
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content="I will investigate.", tool_calls=[]))])
        generate = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=None)
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-only-not-a-key"}), patch("backend.agent.AsyncOpenAI", return_value=context) as factory:
            asyncio.run(run_agent(self.store, run["id"]))
        self.assertEqual(factory.call_args.kwargs["base_url"], NIM_BASE_URL)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 1)
        self.assertEqual(generate.await_count, 12)
        self.assertEqual(self.store.run(run["id"])["status"], "failed")
        self.assertIn("12-turn limit", self.store.run(run["id"])["error"])
        self.assertIsNone(self.store.order(run["id"]))

    def test_nim_tool_loop_completes_purchase(self):
        run = self.store.start_run("review-800", "test-model")
        requests = []
        call_number = 0

        def completion(*calls):
            nonlocal call_number
            tool_calls = []
            for name, args in calls:
                call_number += 1
                tool_calls.append(SimpleNamespace(id=f"call-{call_number}", function=SimpleNamespace(
                    name=name, arguments=json.dumps(args))))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=tool_calls))])

        async def generate_response(**kwargs):
            requests.append(copy.deepcopy(kwargs))
            turn = len(requests)
            if turn == 1:
                return completion(*[(name, {}) for name in sorted(EVIDENCE)])
            if turn == 2:
                return completion(("assess_purchase", {"proposed_quantity": 400, "rationale": "Evidence supports 400 units."}))
            if turn == 3:
                assessment = next(json.loads(item["content"]) for item in reversed(kwargs["messages"])
                                  if item["role"] == "tool" and item["name"] == "assess_purchase")
                aid = assessment["assessment_id"]
                return completion(
                    ("record_decision", {"assessment_id": aid, "decision": "modify", "quantity": 400,
                                         "rationale": "The recommendation exceeds the assessed need."}),
                    ("create_purchase", {"assessment_id": aid}),
                    ("verify_outcome", {}),
                )
            return completion(("finish_run", {"summary": "Purchased and verified 400 units."}))

        generate = AsyncMock(side_effect=generate_response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)))
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=None)
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-only-not-a-key"}), patch("backend.agent.AsyncOpenAI", return_value=context):
            asyncio.run(run_agent(self.store, run["id"]))

        finished = self.store.run(run["id"])
        self.assertEqual(finished["status"], "validated")
        self.assertEqual(finished["purchase_order"]["requested_units"], 400)
        self.assertEqual(generate.await_count, 4)
        self.assertIn("read_inventory", {tool["function"]["name"] for tool in requests[0]["tools"]})
        tool_result = next(item for item in requests[1]["messages"] if item["role"] == "tool")
        self.assertTrue(tool_result["tool_call_id"].startswith("call-"))

    def test_http_contract(self):
        from backend import main
        with patch.object(main, "store", self.store), TestClient(main.app) as client:
            self.assertEqual(client.get("/api/health").status_code, 200)
            self.assertEqual(len(client.get("/api/scenarios").json()), 10)
            self.assertEqual(client.get("/api/scenarios/no-such-id").status_code, 404)
            self.assertIsInstance(client.post("/api/runs", json={"scenario_id": 4}).json()["detail"], str)
            run = self.store.start_run("review-800", "test-model")
            self.assertEqual(client.post("/api/runs", json={"scenario_id": "review-800"}).status_code, 409)
            self.assertEqual(client.post("/api/scenarios/review-800/reset").status_code, 409)
            self.assertEqual(client.get("/api/runs/" + run["id"]).json()["status"], "running")


if __name__ == "__main__":
    unittest.main()
