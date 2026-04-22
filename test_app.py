import copy
import unittest
from unittest.mock import patch

import app as mod


class MbankAppTests(unittest.TestCase):
    def setUp(self):
        self.original_db = copy.deepcopy(mod.DB)
        self.save_state_patcher = patch.object(mod, "save_state", lambda: None)
        self.save_state_patcher.start()
        mod.DB = copy.deepcopy(self.original_db)
        self.client = mod.app.test_client()

    def tearDown(self):
        mod.DB = self.original_db
        self.save_state_patcher.stop()

    def test_dashboard_and_insights_return_live_analytics(self):
        dashboard = self.client.get("/api/dashboard").get_json()
        insights = self.client.get("/api/insights?category=all&tag=all").get_json()

        self.assertIn("analytics", dashboard)
        self.assertIn("transactions_count", dashboard)
        self.assertGreaterEqual(dashboard["transactions_count"], len(dashboard["transactions"]))
        self.assertIn("average_check", dashboard["analytics"])
        self.assertIn("frequency_per_day", dashboard["analytics"])
        self.assertIn("budget_pressure", dashboard["analytics"])
        self.assertIn("tagged_share_by_count", dashboard["tag_analytics"])
        self.assertIn("average_check", insights)
        self.assertIn("top_category", insights)

    def test_smallest_expense_changes_analytics(self):
        before = self.client.get("/api/dashboard").get_json()
        before_total = before["analytics"]["total_spent"]
        before_count = before["analytics"]["tx_count"]
        before_tagged_count = before["tag_analytics"]["total_tagged_count"]

        response = self.client.post(
            "/api/transfer",
            json={
                "phone": "+996700555666",
                "amount": 1,
                "account_id": "main",
                "custom_tag": "Micro test",
            },
        )
        payload = response.get_json()
        after = self.client.get("/api/dashboard").get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(after["analytics"]["total_spent"], before_total + 1)
        self.assertEqual(after["analytics"]["tx_count"], before_count + 1)
        self.assertEqual(after["tag_analytics"]["total_tagged_count"], before_tagged_count + 1)
        self.assertEqual(after["transactions_count"], before["transactions_count"] + 1)

    def test_custom_tags_work_for_transfer_and_bill_payment(self):
        for bill in mod.DB["bills"]:
            if bill["id"] == "electric":
                bill["status"] = "due"
                bill["due"] = "До конца дня"
                break

        transfer = self.client.post(
            "/api/transfer",
            json={
                "phone": "+996700555666",
                "amount": 321,
                "account_id": "main",
                "custom_tag": "Custom family tag",
            },
        ).get_json()

        bill = self.client.post(
            "/api/pay-bill",
            json={
                "bill_id": "electric",
                "account_id": "main",
                "custom_tag": "Home utilities tag",
            },
        ).get_json()

        labels = {tag["label"] for tag in mod.DB["tags"]}
        self.assertTrue(transfer["ok"])
        self.assertTrue(bill["ok"])
        self.assertEqual(transfer["tag"]["label"], "Custom family tag")
        self.assertEqual(bill["tag"]["label"], "Home utilities tag")
        self.assertIn("Custom family tag", labels)
        self.assertIn("Home utilities tag", labels)

    def test_autopilot_and_missions_use_live_state(self):
        mod.DB["transactions"].insert(
            0,
            {
                "id": 999,
                "name": "Новая зарплата",
                "category": "income",
                "amount": 77777,
                "icon": "ЗП",
                "bg": "#0E3A1C",
                "date": "Сегодня, 12:00",
                "dir": "in",
                "account": "main",
                "tag": "savings",
                "kind": "salary",
            },
        )

        autopilot = self.client.post("/api/salary-plan", json={}).get_json()
        gamification = self.client.get("/api/gamification").get_json()

        self.assertEqual(autopilot["plan"]["salary"], 77777)
        self.assertEqual(autopilot["plan"]["salary_date"], "Сегодня, 12:00")
        budget_day = next(m for m in gamification["missions"] if m["id"] == "budget_day")
        tagged_transfer = next(m for m in gamification["missions"] if m["id"] == "tagged_transfer")
        self.assertIn("сом/день", budget_day["desc"])
        self.assertGreaterEqual(tagged_transfer["progress"], 0)

    def test_home_screen_keeps_focus_and_removes_duplicate_blocks(self):
        html = self.client.get("/").get_data(as_text=True)

        self.assertIn('id="home-focus"', html)
        self.assertIn('id="home-glance"', html)
        self.assertIn('id="home-bills"', html)
        self.assertIn('id="home-goals"', html)
        self.assertIn('id="home-mini-accounts"', html)
        self.assertIn('id="mini-account-modal"', html)
        self.assertIn('id="tag-modal"', html)
        self.assertIn('id="transfer-custom-tag"', html)
        self.assertIn('id="transfer-account-choices"', html)
        self.assertIn('id="bill-custom-tag"', html)
        self.assertIn('id="bill-account-choices"', html)
        self.assertNotIn('id="home-offers"', html)
        self.assertNotIn('id="home-nba"', html)
        self.assertNotIn('id="autopilot-hero"', html)
        self.assertNotIn('<div class="qa-lbl">История</div>', html)
        self.assertNotIn('<div class="qa-lbl">Контроль</div>', html)
        self.assertIn('<div class="qa-lbl">Платежи</div>', html)

    def test_key_screens_have_back_navigation(self):
        html = self.client.get("/").get_data(as_text=True)

        self.assertIn("goBack('screen-home')", html)
        self.assertIn('id="screen-notif"', html)
        self.assertIn('id="screen-profile"', html)
        self.assertIn('id="screen-goals"', html)
        self.assertIn('id="screen-applied"', html)

    def test_notifications_and_offer_messages_use_live_values(self):
        mod.DB["transactions"].insert(
            0,
            {
                "id": 1001,
                "name": "Свежая зарплата",
                "category": "income",
                "amount": 88888,
                "icon": "ЗП",
                "bg": "#0E3A1C",
                "date": "Сегодня, 08:00",
                "dir": "in",
                "account": "main",
                "tag": "savings",
                "kind": "salary",
            },
        )

        notifications = self.client.get("/api/notifications").get_json()["notifications"]
        boost_offer = next(
            offer for offer in self.client.get("/api/smart-offers").get_json()["offers"] if offer["id"] == "savings_boost"
        )
        offer_action = self.client.post("/api/offer-action", json={"offer_id": "savings_boost"})
        payload = offer_action.get_json()

        self.assertIn("88,888", notifications[0]["body"])
        self.assertEqual(offer_action.status_code, 200)
        self.assertIn(f"{boost_offer['amount']:,}", payload["message"])

    def test_mini_account_creation_and_topup_move_money_from_main(self):
        main_before = mod.get_account("main")["balance"]

        created = self.client.post(
            "/api/mini-accounts",
            json={
                "label": "Transport",
                "amount": 1500,
                "custom_tag": "Обед",
            },
        )
        create_payload = created.get_json()

        self.assertEqual(created.status_code, 200)
        self.assertTrue(create_payload["ok"])
        self.assertEqual(create_payload["account"]["label"], "Transport")
        self.assertEqual(create_payload["account"]["balance"], 1500)
        self.assertEqual(mod.get_account("main")["balance"], main_before - 1500)

        topped_up = self.client.post(
            f"/api/mini-accounts/{create_payload['account']['id']}/topup",
            json={"amount": 500},
        )
        topup_payload = topped_up.get_json()

        self.assertEqual(topped_up.status_code, 200)
        self.assertTrue(topup_payload["ok"])
        self.assertEqual(topup_payload["account"]["balance"], 2000)
        self.assertEqual(mod.get_account("main")["balance"], main_before - 2000)

    def test_bill_payment_uses_linked_mini_account_when_tag_matches(self):
        self.client.post(
            "/api/mini-accounts",
            json={
                "label": "Обед",
                "amount": 2000,
                "custom_tag": "Lunch",
            },
        )
        linked_account = next(account for account in mod.DB["accounts"] if account.get("tag_id"))
        linked_tag = linked_account["tag_id"]

        for bill in mod.DB["bills"]:
            if bill["id"] == "electric":
                bill["status"] = "due"
                break

        main_before = mod.get_account("main")["balance"]
        mini_before = linked_account["balance"]

        response = self.client.post(
            "/api/pay-bill",
            json={
                "bill_id": "electric",
                "tag": linked_tag,
            },
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["account"]["id"], linked_account["id"])
        self.assertEqual(mod.get_account("main")["balance"], main_before)
        self.assertEqual(mod.get_account(linked_account["id"])["balance"], mini_before - 1240)

    def test_transfer_analytics_question_stays_in_advice_mode(self):
        reply, action = mod.fallback_chat_response("Покажи аналитику переводов за месяц")

        self.assertIsNone(action)
        self.assertIn("перевод", reply.lower())
        self.assertIn("тег", reply.lower())

    def test_explicit_transfer_command_can_prepare_transfer_action(self):
        reply, action = mod.fallback_chat_response("Переведи 1500 Айгуль")

        self.assertIsNotNone(action)
        self.assertEqual(action["action"], "transfer")
        self.assertEqual(action["amount"], 1500)
        self.assertEqual(action["contact"], "Айгуль Токтосунова")
        self.assertIn("перевод", reply.lower())


if __name__ == "__main__":
    unittest.main()
