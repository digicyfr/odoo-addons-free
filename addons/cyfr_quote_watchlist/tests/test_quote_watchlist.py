from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import config


@tagged("post_install", "-at_install")
class TestQuoteWatchlist(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env["res.partner"].create({"name": "Quote Watchlist Test Customer"})
        cls.today = fields.Date.context_today(cls.env["cyfr.quote.watchlist"])

    def _quote(self, *, days=None, state="draft", company=None, user=None, team=None):
        company = company or self.company
        vals = {"partner_id": self.partner.id, "company_id": company.id,
                "validity_date": self.today + timedelta(days=days) if days is not None else False,
                "user_id": (user or self.env.user).id}
        if team:
            vals["team_id"] = team.id
        quote = self.env["sale.order"].with_company(company).create(vals)
        if state != "draft":
            quote.write({"state": state})
        return quote

    def _activity(self, quote, days, user=None):
        return self.env["mail.activity"].create({
            "res_model_id": self.env["ir.model"]._get("sale.order").id,
            "res_id": quote.id,
            "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
            "user_id": (user or self.env.user).id,
            "date_deadline": self.today + timedelta(days=days),
            "summary": "Test quote follow-up",
        })

    def _scan(self, **filters):
        wizard = self.env["cyfr.quote.watchlist"].create(filters)
        action = wizard.action_scan()
        if wizard.truncated:
            self.assertEqual(action["res_model"], "cyfr.quote.watchlist")
            self.assertEqual(action["res_id"], wizard.id)
        else:
            self.assertEqual(action["domain"], [("worklist_id", "=", wizard.id)])
        return wizard

    def test_expiry_boundaries_and_closed_states(self):
        expired = self._quote(days=-1)
        today = self._quote(days=0)
        horizon = self._quote(days=7)
        beyond = self._quote(days=8)
        confirmed = self._quote(days=-1, state="sale")
        cancelled = self._quote(days=-1, state="cancel")
        self._activity(beyond, 2)
        wizard = self._scan()
        rows = {row.order_id.id: row for row in wizard.line_ids}
        self.assertEqual(rows[expired.id].reason_code, "expired")
        self.assertEqual(rows[today.id].reason_code, "soon")
        self.assertEqual(rows[horizon.id].reason_code, "soon")
        self.assertFalse({beyond.id, confirmed.id, cancelled.id} & rows.keys())

    def test_future_due_today_overdue_and_missing_validity(self):
        only_overdue = self._quote(days=30)
        due_today = self._quote(days=30)
        future = self._quote(days=30)
        no_activity = self._quote(days=30)
        missing_date = self._quote()
        self._activity(only_overdue, -1)
        self._activity(due_today, 0)
        self._activity(future, 2)
        self._activity(future, -2)
        wizard = self._scan()
        rows = {row.order_id.id: row for row in wizard.line_ids}
        self.assertTrue(rows[only_overdue.id].missing_future_activity)
        self.assertTrue(rows[only_overdue.id].has_overdue_activity)
        self.assertTrue(rows[due_today.id].missing_future_activity)
        self.assertTrue(rows[due_today.id].has_due_today_activity)
        self.assertNotIn(future.id, rows)
        self.assertEqual(rows[no_activity.id].reason_code, "no_future")
        self.assertEqual(rows[missing_date.id].reason_code, "missing")
        self.assertFalse(rows[missing_date.id].validity_date)

    def test_settings_filters_and_rescan(self):
        manager_setting = self.env["cyfr.quote.watchlist.setting"].create({
            "company_id": self.company.id, "horizon_days": 3})
        near = self._quote(days=3)
        far = self._quote(days=4)
        self._activity(near, 5)
        self._activity(far, 5)
        wizard = self._scan(valid_from=self.today + timedelta(days=3),
                            valid_to=self.today + timedelta(days=4))
        self.assertEqual(wizard.horizon_days, 3)
        self.assertEqual(wizard.line_ids.order_id.ids, near.ids)
        self.assertEqual(wizard.line_ids.next_activity_date, self.today + timedelta(days=5))
        manager_setting.horizon_days = 4
        wizard.action_scan()
        self.assertEqual(set(wizard.line_ids.order_id.ids), {near.id, far.id})
        wizard.write({"valid_from": self.today + timedelta(days=4)})
        self.assertFalse(wizard.scanned_at)
        self.assertFalse(wizard.line_ids)
        wizard.action_scan()
        self.assertEqual(wizard.line_ids.order_id.ids, far.ids)
        with self.assertRaises(ValidationError):
            wizard.write({"valid_from": self.today + timedelta(days=5)})
        with self.assertRaises(ValidationError):
            manager_setting.horizon_days = 91

    def test_manager_setting_and_team_filter(self):
        manager = self.env["res.users"].create({
            "name": "Quote Watchlist Manager", "login": "quote-watchlist-manager-test",
            "company_id": self.company.id, "company_ids": [Command.link(self.company.id)],
            "group_ids": [Command.link(self.env.ref("sales_team.group_sale_manager").id)],
        })
        setting = self.env["cyfr.quote.watchlist.setting"].with_user(manager).create({
            "company_id": self.company.id, "horizon_days": 2,
        })
        self.assertEqual(setting.horizon_days, 2)
        setting.write({"horizon_days": 4})
        team_a = self.env["crm.team"].create({"name": "Quote Team A"})
        team_b = self.env["crm.team"].create({"name": "Quote Team B"})
        quote_a = self._quote(days=3, team=team_a)
        quote_b = self._quote(days=3, team=team_b)
        wizard = self._scan(team_id=team_a.id)
        self.assertEqual(wizard.horizon_days, 4)
        self.assertIn(quote_a.id, wizard.line_ids.order_id.ids)
        self.assertNotIn(quote_b.id, wizard.line_ids.order_id.ids)

    def test_scan_is_bounded_and_read_only_on_quotes(self):
        quotes = self.env["sale.order"]
        for _ in range(4):
            quotes |= self._quote(days=-1)
        before = {quote.id: quote.read(["write_date", "state", "validity_date"])[0] for quote in quotes}
        with patch("odoo.addons.cyfr_quote_watchlist.models.quote_watchlist.MAX_CANDIDATES", 2):
            wizard = self._scan()
        self.assertTrue(wizard.truncated)
        self.assertEqual(wizard.candidate_count, 2)
        with patch("odoo.addons.cyfr_quote_watchlist.models.quote_watchlist.MAX_RESULTS", 1):
            wizard.action_scan()
        self.assertTrue(wizard.truncated)
        self.assertEqual(wizard.result_count, 1)
        for quote in quotes:
            self.assertEqual(quote.read(["write_date", "state", "validity_date"])[0], before[quote.id])

    def test_activity_grouping_has_constant_query_shape(self):
        quotes = self.env["sale.order"]
        for offset in range(30):
            quote = self._quote(days=30)
            self._activity(quote, 1 + offset % 3)
            quotes |= quote
        wizard = self.env["cyfr.quote.watchlist"].create({})
        self.env.flush_all()
        one_start = self.cr.sql_log_count
        one_future, _, _ = wizard._activity_summary(quotes[:1].ids, self.today)
        one_count = self.cr.sql_log_count - one_start
        many_start = self.cr.sql_log_count
        many_future, _, _ = wizard._activity_summary(quotes.ids, self.today)
        many_count = self.cr.sql_log_count - many_start
        self.assertEqual(len(one_future), 1)
        self.assertEqual(len(many_future), len(quotes))
        self.assertLess(many_count, one_count + 12)

    def test_activity_action_rechecks_write_and_state(self):
        quote = self._quote(days=-1)
        wizard = self._scan()
        row = wizard.line_ids.filtered(lambda item: item.order_id == quote)
        self.assertTrue(row)
        activity_count = self.env["mail.activity"].search_count([
            ("res_model", "=", "sale.order"), ("res_id", "=", quote.id)])
        action = row.action_schedule_activity()
        self.assertEqual(action["res_model"], "mail.activity")
        self.assertEqual(action["context"]["default_res_id"], quote.id)
        self.assertEqual(self.env["mail.activity"].search_count([
            ("res_model", "=", "sale.order"), ("res_id", "=", quote.id)]), activity_count)
        self.assertEqual(row.action_open_quote()["res_id"], quote.id)
        quote.state = "cancel"
        with self.assertRaises(UserError):
            row.action_schedule_activity()

    def test_salesperson_owner_company_and_source_acl(self):
        foreign_company = self.env["res.company"].create({
            "name": "Quote Watchlist Other Company", "country_id": self.company.country_id.id})
        salesperson = self.env["res.users"].create({
            "name": "Quote Watchlist Salesperson", "login": "quote-watchlist-salesperson-test",
            "company_id": self.company.id, "company_ids": [Command.link(self.company.id)],
            "group_ids": [Command.link(self.env.ref("sales_team.group_sale_salesman").id)]})
        other_user = self.env["res.users"].create({
            "name": "Quote Watchlist Other Salesperson", "login": "quote-watchlist-other-test",
            "company_id": self.company.id, "company_ids": [Command.link(self.company.id)],
            "group_ids": [Command.link(self.env.ref("sales_team.group_sale_salesman").id)]})
        own = self._quote(days=-1, user=salesperson)
        other = self._quote(days=-1, user=other_user)
        foreign = self._quote(days=-1, company=foreign_company, user=salesperson)
        assigned_elsewhere = self._quote(days=30, user=salesperson)
        self._activity(assigned_elsewhere, 3, user=other_user)
        wizard = self.env["cyfr.quote.watchlist"].with_user(salesperson).create({})
        wizard.action_scan()
        self.assertIn(own.id, wizard.line_ids.order_id.ids)
        self.assertNotIn(other.id, wizard.line_ids.order_id.ids)
        self.assertNotIn(foreign.id, wizard.line_ids.order_id.ids)
        self.assertNotIn(assigned_elsewhere.id, wizard.line_ids.order_id.ids)
        own_row = wizard.line_ids.filtered(lambda row: row.order_id.id == own.id)
        with self.assertRaises(AccessError):
            wizard.with_user(other_user).action_open_results()
        with self.assertRaises(AccessError):
            own_row.with_user(other_user).read(["partner_id"])
        with self.assertRaises(AccessError):
            self.env["cyfr.quote.watchlist"].with_user(salesperson).create({"company_id": foreign_company.id})
        with self.assertRaises(AccessError):
            self.env["cyfr.quote.watchlist.setting"].with_user(salesperson).create({
                "company_id": self.company.id, "horizon_days": 1})

    def test_rpc_cannot_forge_rows_or_horizon_and_live_source_rule(self):
        quote = self._quote(days=-1)
        salesperson = self.env["res.users"].create({
            "name": "Quote Watchlist Integrity User", "login": "quote-watchlist-integrity-test",
            "company_id": self.company.id, "company_ids": [Command.link(self.company.id)],
            "group_ids": [Command.link(self.env.ref("sales_team.group_sale_salesman_all_leads").id)]})
        Wizard = self.env["cyfr.quote.watchlist"].with_user(salesperson)
        Row = self.env["cyfr.quote.watchlist.line"].with_user(salesperson)
        with self.assertRaises(AccessError):
            Wizard.create({"horizon_days": 90})
        wizard = Wizard.create({})
        wizard.action_scan()
        row = wizard.line_ids.filtered(lambda item: item.order_id == quote)
        self.assertTrue(row)
        with self.assertRaises(AccessError):
            wizard.write({"horizon_days": 90})
        with self.assertRaises(AccessError):
            Row.create({"worklist_id": wizard.id, "order_id": quote.id, "company_id": self.company.id})
        with self.assertRaises(AccessError):
            row.write({"reason_code": "soon"})
        with self.assertRaises(AccessError):
            row.unlink()
        self.env["ir.rule"].create({
            "name": "Quote watchlist test hide one order",
            "model_id": self.env.ref("sale.model_sale_order").id,
            "domain_force": "[('id', '!=', %d)]" % quote.id,
            "perm_read": True, "perm_write": False, "perm_create": False, "perm_unlink": False,
        })
        self.assertNotIn(row.id, Row.search([("id", "=", row.id)]).ids)
        with self.assertRaises(AccessError):
            row.read(["partner_id"])
        with self.assertRaises(AccessError):
            row.export_data(["partner_id"])
        with self.assertRaises(AccessError):
            row.action_open_quote()
        with self.assertRaises(AccessError):
            row.action_schedule_activity()

    def test_demo_data_is_loaded_when_requested(self):
        if not config["with_demo"]:
            self.skipTest("Demo data intentionally disabled")
        ids = ["demo_customer", "demo_second_company", "demo_expiring", "demo_expired",
               "demo_no_activity", "demo_only_overdue", "demo_future", "demo_missing_date",
               "demo_confirmed", "demo_cancelled", "demo_second_company_quote",
               "demo_overdue_activity", "demo_future_activity"]
        for xmlid in ids:
            self.assertTrue(self.env.ref("cyfr_quote_watchlist." + xmlid, raise_if_not_found=False), xmlid)
