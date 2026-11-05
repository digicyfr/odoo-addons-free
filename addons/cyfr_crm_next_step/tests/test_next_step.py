import ast
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import config


@tagged("post_install", "-at_install")
class TestCrmNextStep(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.action = cls.env.ref("cyfr_crm_next_step.action_crm_next_step_queue")
        cls.queue_domain = ast.literal_eval(cls.action.domain)
        cls.activity_type = cls.env.ref("mail.mail_activity_data_todo")
        cls.env.user.tz = "UTC"

    def _lead(self, name, **values):
        return self.env["crm.lead"].create({"name": name, "type": "opportunity", **values})

    def _activity(self, lead, deadline, active=True):
        return self.env["mail.activity"].create({
            "res_model_id": self.env.ref("crm.model_crm_lead").id,
            "res_id": lead.id,
            "activity_type_id": self.activity_type.id,
            "user_id": self.env.user.id,
            "date_deadline": deadline,
            "active": active,
        })

    def _queue_ids(self, leads, user=None, extra_domain=None):
        lead_model = self.env["crm.lead"].with_user(user) if user else self.env["crm.lead"]
        return set(lead_model.search(self.queue_domain + [("id", "in", leads.ids)] + (extra_domain or [])).ids)

    def test_open_leads_with_no_activity_or_overdue_only(self):
        today = fields.Date.today()
        no_activity = self._lead("Queue No Activity")
        overdue = self._lead("Queue Overdue")
        today_due = self._lead("Queue Due Today")
        planned = self._lead("Queue Planned")
        won_stage = self.env["crm.stage"].create({"name": "Queue Won Stage", "is_won": True})
        won = self._lead("Queue Won", stage_id=won_stage.id, probability=100)
        lost = self._lead("Queue Lost", active=False, probability=0)
        archived = self._lead("Queue Archived", active=False)
        self._activity(overdue, today - timedelta(days=1))
        self._activity(today_due, today)
        self._activity(planned, today + timedelta(days=1))
        leads = no_activity | overdue | today_due | planned | won | lost | archived
        self.assertEqual(won.won_status, "won")
        self.assertEqual(lost.won_status, "lost")
        self.assertEqual(self._queue_ids(leads), {no_activity.id, overdue.id})
        self.assertEqual(no_activity.cyfr_next_step_reason, "no_activity")
        self.assertEqual(overdue.cyfr_next_step_reason, "overdue")
        self.assertFalse(today_due.cyfr_next_step_reason)
        self.assertFalse(planned.cyfr_next_step_reason)

    def test_overdue_wins_over_future_and_completed_is_ignored(self):
        today = fields.Date.today()
        overdue_plus_future = self._lead("Queue Mixed Activities")
        completed_only = self._lead("Queue Completed Only")
        self._activity(overdue_plus_future, today - timedelta(days=1))
        self._activity(overdue_plus_future, today + timedelta(days=7))
        self._activity(completed_only, today - timedelta(days=3), active=False)
        self.assertEqual(self._queue_ids(overdue_plus_future | completed_only),
                         {overdue_plus_future.id, completed_only.id})
        self.assertEqual(self._queue_ids(overdue_plus_future | completed_only,
                                        extra_domain=[("activity_state", "in", [False])]),
                         {completed_only.id})
        self.assertEqual(self._queue_ids(overdue_plus_future | completed_only,
                                        extra_domain=[("activity_state", "in", ["overdue"])]),
                         {overdue_plus_future.id})

    def test_salesperson_team_company_filters_and_existing_rules(self):
        company_a = self.env.company
        company_b = self.env["res.company"].create({"name": "Queue Test Company B"})
        sales_group = self.env.ref("sales_team.group_sale_salesman")
        salesperson = self.env["res.users"].create({
            "name": "Queue Test Salesperson", "login": "queue-salesperson-test",
            "company_id": company_a.id,
            "company_ids": [Command.link(company_a.id)],
            "group_ids": [Command.link(sales_group.id)],
        })
        other_salesperson = self.env["res.users"].create({
            "name": "Queue Other Salesperson", "login": "queue-other-salesperson-test",
            "company_id": company_b.id,
            "company_ids": [Command.link(company_b.id)],
            "group_ids": [Command.link(sales_group.id)],
        })
        team = self.env["crm.team"].create({"name": "Queue Team A", "company_id": company_a.id})
        other_team = self.env["crm.team"].create({"name": "Queue Team B", "company_id": company_b.id})
        own = self._lead("Queue Own Lead", company_id=company_a.id,
                         user_id=salesperson.id, team_id=team.id)
        foreign = self._lead("Queue Foreign Lead", company_id=company_b.id,
                             user_id=other_salesperson.id, team_id=other_team.id)
        leads = own | foreign
        self.assertEqual(self._queue_ids(leads, salesperson), {own.id})
        self.assertEqual(self._queue_ids(leads, salesperson,
                                        [("user_id", "=", salesperson.id)]), {own.id})
        self.assertEqual(self._queue_ids(leads, salesperson,
                                        [("team_id", "=", team.id)]), {own.id})
        self.assertEqual(self._queue_ids(leads, salesperson,
                                        [("company_id", "=", company_b.id)]), set())
        self.assertEqual(self._queue_ids(leads, other_salesperson), {foreign.id})
        self.assertEqual(self._queue_ids(leads, other_salesperson,
                                        [("company_id", "=", company_a.id)]), set())
        self.assertEqual(own.with_user(salesperson).read(["cyfr_next_step_reason"])[0]["cyfr_next_step_reason"],
                         "no_activity")
        with self.assertRaises(AccessError):
            foreign.with_user(salesperson).read(["cyfr_next_step_reason"])

        internal_only = self.env["res.users"].create({
            "name": "Queue Internal Only", "login": "queue-internal-only-test",
            "company_id": company_a.id,
            "company_ids": [Command.link(company_a.id)],
            "group_ids": [Command.link(self.env.ref("base.group_user").id)],
        })
        with self.assertRaises(AccessError):
            self._queue_ids(leads, internal_only)

    def test_queue_search_does_not_mutate_records(self):
        lead = self._lead("Queue Read Only")
        before = lead.read(["write_date", "activity_state", "activity_date_deadline"])[0]
        activity_count = self.env["mail.activity"].search_count([
            ("res_model", "=", "crm.lead"), ("res_id", "=", lead.id),
        ])
        self.assertIn(lead.id, self._queue_ids(lead))
        self.assertEqual(lead.read(["write_date", "activity_state", "activity_date_deadline"])[0], before)
        self.assertEqual(self.env["mail.activity"].search_count([
            ("res_model", "=", "crm.lead"), ("res_id", "=", lead.id),
        ]), activity_count)

    def test_menu_and_views_are_linked_once(self):
        menu = self.env.ref("cyfr_crm_next_step.menu_crm_next_step_queue")
        self.assertEqual(menu.action, self.action)
        self.assertEqual(self.action.res_model, "crm.lead")
        self.assertEqual(self.action.view_mode, "list,form")
        self.assertEqual(self.action.search_view_id,
                         self.env.ref("cyfr_crm_next_step.view_crm_next_step_search"))
        self.assertEqual(self.env["ir.ui.menu"].search_count([("id", "=", menu.id)]), 1)

    def test_demo_records_when_demo_enabled(self):
        if not config["with_demo"]:
            return
        module = "cyfr_crm_next_step"
        names = (
            "demo_company_other", "demo_won_stage", "demo_lead_no_activity",
            "demo_lead_planned", "demo_lead_overdue", "demo_lead_won",
            "demo_lead_lost", "demo_lead_other_company",
            "demo_activity_planned", "demo_activity_overdue",
        )
        for name in names:
            self.assertTrue(self.env.ref(f"{module}.{name}", raise_if_not_found=False), name)
        self.assertGreater(self.env.ref(f"{module}.demo_activity_planned").date_deadline,
                           fields.Date.today())
        self.assertLess(self.env.ref(f"{module}.demo_activity_overdue").date_deadline,
                        fields.Date.today())
