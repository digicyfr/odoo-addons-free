from datetime import timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo import SUPERUSER_ID, Command, api, fields, tools
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPosShiftHandover(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        group = cls.env.ref("point_of_sale.group_pos_user")
        manager_group = cls.env.ref("point_of_sale.group_pos_manager")

        def make_user(name, group_id):
            return cls.env["res.users"].create({
                "name": name, "login": "shift-test-" + name.lower().replace(" ", "-"),
                "company_id": company.id, "company_ids": [Command.link(company.id)],
                "group_ids": [Command.link(group_id)],
            })

        cls.preparer = make_user("Shift Preparer", group.id)
        cls.receiver = make_user("Shift Receiver", group.id)
        cls.other_user = make_user("Shift Other User", group.id)
        cls.manager = make_user("Shift Manager", manager_group.id)
        cls.non_pos = make_user("Shift No POS", cls.env.ref("base.group_user").id)
        cls.config = cls.env["pos.config"].create({"name": "Shift Test Register", "cash_control": False})
        cls.other_config = cls.env["pos.config"].create({"name": "Other Shift Register", "cash_control": False})
        now = fields.Datetime.now()
        cls.source = cls.env["pos.session"].create({
            "config_id": cls.config.id, "user_id": cls.preparer.id, "state": "closed",
            "start_at": now - timedelta(days=2), "stop_at": now - timedelta(days=1),
            "closing_notes": "Native finance note stays separate",
        })
        cls.target = cls.env["pos.session"].create({
            "config_id": cls.config.id, "user_id": cls.receiver.id, "state": "opened",
            "start_at": now - timedelta(hours=1),
        })
        cls.wrong_target = cls.env["pos.session"].create({
            "config_id": cls.other_config.id, "user_id": cls.other_user.id,
            "state": "opened", "start_at": now - timedelta(minutes=30),
        })

    def _handover(self, user=None):
        return self.env["cyfr.pos.handover"].with_user(user or self.preparer).create({
            "name": "A to B", "source_session_id": self.source.id,
        })

    def test_claim_acknowledge_retry_and_native_finance_untouched(self):
        handover = self._handover()
        before = self.source.read(["state", "closing_notes", "cash_register_balance_end_real", "stop_at"])[0]
        action = handover.with_user(self.receiver).action_claim()
        self.assertEqual(action["res_id"], handover.id)
        self.assertEqual(handover.target_session_id, self.target)
        self.assertEqual(handover.claimed_by_id, self.receiver)
        self.assertTrue(handover.claimed_at)
        self.assertEqual(handover.state, "claimed")
        handover.with_user(self.receiver).action_claim()
        self.assertEqual(handover.claimed_by_id, self.receiver)
        with self.assertRaises(UserError):
            handover.with_user(self.other_user).action_claim()
        handover.with_user(self.receiver).action_acknowledge()
        handover.with_user(self.receiver).action_acknowledge()
        self.assertEqual(handover.acknowledged_by_id, self.receiver)
        self.assertEqual(handover.state, "acknowledged")
        with self.assertRaises(UserError):
            handover.with_user(self.other_user).action_acknowledge()
        self.assertEqual(self.source.read(["state", "closing_notes", "cash_register_balance_end_real", "stop_at"])[0], before)
        self.assertEqual(self.target.state, "opened")

    def test_wrong_register_and_session_state_rejected(self):
        handover = self._handover()
        with self.assertRaises(UserError):
            handover.with_user(self.receiver).action_claim(self.wrong_target.id)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            handover.sudo().write({"target_session_id": self.wrong_target.id,
                                   "claimed_by_id": self.receiver.id, "claimed_at": fields.Datetime.now()})
        self.target.state = "closed"
        with self.assertRaises(UserError):
            handover.with_user(self.receiver).action_claim()

    def test_open_source_cannot_be_claimed(self):
        open_source = self.env["pos.session"].create({
            "config_id": self.env["pos.config"].create({"name": "Unclosed Shift Register"}).id,
            "user_id": self.preparer.id, "state": "opened", "start_at": fields.Datetime.now(),
        })
        handover = self.env["cyfr.pos.handover"].with_user(self.preparer).create({
            "source_session_id": open_source.id,
        })
        with self.assertRaises(UserError):
            handover.with_user(self.receiver).action_claim()

    def test_direct_rpc_spoof_and_duplicate_source_rejected(self):
        with self.assertRaises(AccessError):
            self.env["cyfr.pos.handover"].with_user(self.preparer).create({
                "source_session_id": self.source.id, "claimed_by_id": self.preparer.id,
            })
        handover = self._handover()
        with self.assertRaises(AccessError):
            handover.with_user(self.preparer).write({"target_session_id": self.target.id})
        with self.assertRaises(AccessError):
            handover.with_user(self.preparer).unlink()
        with self.assertRaises(AccessError):
            self.env["cyfr.pos.handover"].with_user(self.non_pos).create({"source_session_id": self.source.id})
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["cyfr.pos.handover"].create({"source_session_id": self.source.id})

    def test_same_day_overdue_filter_uses_current_time(self):
        handover = self._handover()
        with freeze_time("2026-11-05 12:00:00"):
            now = fields.Datetime.now()
            past = self.env["cyfr.pos.handover.task"].with_user(self.preparer).create({
                "handover_id": handover.id, "title": "Due earlier today",
                "due_at": now - timedelta(minutes=1),
            })
            future = self.env["cyfr.pos.handover.task"].with_user(self.preparer).create({
                "handover_id": handover.id, "title": "Due later today",
                "due_at": now + timedelta(minutes=1),
            })
            self.assertEqual(past.due_at.date(), now.date())
            self.assertTrue(past.is_overdue)
            self.assertFalse(future.is_overdue)
            overdue = self.env["cyfr.pos.handover.task"].with_user(self.manager).search([
                ("handover_id", "=", handover.id), ("is_overdue", "=", True),
            ])
            self.assertIn(past, overdue)
            self.assertNotIn(future, overdue)

    def test_contended_claim_asks_for_retry_without_double_recipient(self):
        if not tools.config["with_demo"]:
            self.skipTest("The committed demo handover is required for lock contention")
        handover = self.env.ref("cyfr_pos_shift_handover.demo_unclaimed_handover")
        self.assertFalse(handover.target_session_id)
        # TransactionCase fixtures are uncommitted, so another cursor cannot
        # claim them. A committed demo row proves the NOWAIT lock path here;
        # the separate-process integration probe covers two full POS claims.
        self.env.cr.execute("SAVEPOINT shift_claim_lock")
        try:
            self.env.cr.execute(
                "SELECT id FROM cyfr_pos_handover WHERE id = %s FOR NO KEY UPDATE",
                [handover.id],
            )
            with self.env.registry.cursor() as contender_cr:
                contender = api.Environment(contender_cr, SUPERUSER_ID, {})
                with self.assertRaises(UserError) as error:
                    contender["cyfr.pos.handover"].browse(handover.id).action_claim()
                self.assertIn("Retry shortly", str(error.exception))
        finally:
            self.env.cr.execute("ROLLBACK TO SAVEPOINT shift_claim_lock")
            self.env.cr.execute("RELEASE SAVEPOINT shift_claim_lock")
        self.assertFalse(handover.target_session_id)

    def test_task_owner_manager_reopen_and_retention(self):
        handover = self._handover()
        task = self.env["cyfr.pos.handover.task"].with_user(self.preparer).create({
            "handover_id": handover.id, "title": "Check display", "owner_id": self.receiver.id,
            "priority": "high", "due_at": fields.Datetime.now() - timedelta(days=1),
        })
        self.assertEqual(task.state, "open")
        with self.assertRaises(AccessError):
            task.with_user(self.other_user).write({"state": "done"})
        handover.with_user(self.receiver).action_claim()
        task.with_user(self.receiver).write({"state": "done", "note": "Display checked"})
        with self.assertRaises(AccessError):
            task.with_user(self.receiver).write({"state": "open"})
        with self.assertRaises(AccessError):
            task.with_user(self.receiver).write({"owner_id": self.other_user.id})
        task.with_user(self.manager).write({"state": "open", "owner_id": self.other_user.id})
        self.assertEqual(task.owner_id, self.other_user)
        with self.assertRaises(AccessError):
            task.with_user(self.manager).unlink()
        with self.assertRaises(AccessError):
            task.with_user(self.other_user).write({"handover_id": handover.id})

    def test_cross_company_create_and_owner_assignment_are_rejected(self):
        other_company = self.env["res.company"].create({"name": "Other Shift Company"})
        foreign_user = self.env["res.users"].create({
            "name": "Foreign POS User", "login": "shift-foreign-pos-user",
            "company_id": other_company.id,
            "company_ids": [Command.link(other_company.id)],
            "group_ids": [Command.link(self.env.ref("point_of_sale.group_pos_user").id)],
        })
        with self.assertRaises(AccessError):
            self.env["cyfr.pos.handover"].with_user(foreign_user).create({
                "source_session_id": self.source.id,
            })
        handover = self._handover()
        with self.assertRaises(AccessError):
            handover.with_user(foreign_user).action_claim()
        with self.assertRaises(AccessError):
            handover.with_user(foreign_user).read(["name"])
        task = self.env["cyfr.pos.handover.task"].with_user(self.preparer).create({
            "handover_id": handover.id, "title": "Check company-bound owner",
        })
        with self.assertRaises(ValidationError):
            task.with_user(self.manager).write({"owner_id": foreign_user.id})

    def test_linked_session_rule_revocation_covers_search_read_export_and_actions(self):
        handover = self._handover()
        task = self.env["cyfr.pos.handover.task"].with_user(self.preparer).create({
            "handover_id": handover.id, "title": "Private source task",
        })
        self.assertIn(handover, self.env["cyfr.pos.handover"].with_user(self.receiver).search([]))
        rule = self.env["ir.rule"].create({
            "name": "Temporary source session revocation", "model_id": self.env["ir.model"]._get_id("pos.session"),
            "domain_force": "[('id', '!=', %d)]" % self.source.id,
        })
        try:
            self.assertNotIn(handover, self.env["cyfr.pos.handover"].with_user(self.receiver).search([]))
            self.assertNotIn(task, self.env["cyfr.pos.handover.task"].with_user(self.receiver).search([]))
            with self.assertRaises(AccessError):
                handover.with_user(self.receiver).read(["name"])
            with self.assertRaises(AccessError):
                handover.with_user(self.receiver).export_data(["name"])
            with self.assertRaises(AccessError):
                handover.with_user(self.receiver).action_claim()
            with self.assertRaises(AccessError):
                handover.with_user(self.preparer).write({"name": "Hidden source"})
            with self.assertRaises(AccessError):
                handover.with_user(self.manager).write({"name": "Hidden from manager"})
            with self.assertRaises(AccessError):
                task.with_user(self.receiver).read(["title"])
        finally:
            rule.unlink()

    def test_native_session_buttons_and_unclaimed_queue(self):
        handover = self._handover()
        outgoing = self.source.with_user(self.preparer).action_open_outgoing_handover()
        incoming = self.target.with_user(self.receiver).action_open_incoming_handover()
        self.assertEqual(outgoing["context"]["default_source_session_id"], self.source.id)
        self.assertEqual(outgoing["domain"], [("source_session_id", "=", self.source.id)])
        self.assertEqual(incoming["res_model"], "cyfr.pos.handover")
        self.assertIn(handover, self.env["cyfr.pos.handover"].with_user(self.receiver).search(incoming["domain"]))
        with self.assertRaises(UserError):
            self.source.with_user(self.preparer).action_open_incoming_handover()

    def test_demo_records_load_only_when_demo_enabled(self):
        if not tools.config["with_demo"]:
            self.skipTest("Demo loading was intentionally disabled")
        handover = self.env.ref("cyfr_pos_shift_handover.demo_unclaimed_handover")
        overdue = self.env.ref("cyfr_pos_shift_handover.demo_overdue_task")
        unassigned = self.env.ref("cyfr_pos_shift_handover.demo_unassigned_task")
        self.assertEqual(handover.source_session_id, self.env.ref("point_of_sale.pos_closed_session_2"))
        self.assertEqual(handover.source_session_id.state, "closed")
        self.assertFalse(handover.target_session_id)
        self.assertEqual(handover.state, "unclaimed")
        self.assertEqual(overdue.handover_id, handover)
        self.assertLess(overdue.due_at, fields.Datetime.now())
        self.assertEqual(unassigned.handover_id, handover)
        self.assertFalse(unassigned.owner_id)
