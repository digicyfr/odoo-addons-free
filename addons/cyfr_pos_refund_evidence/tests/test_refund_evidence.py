from uuid import uuid4

from odoo import Command, fields, tools
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import CommonPosTest


@tagged("post_install", "-at_install")
class TestRefundEvidence(CommonPosTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Case = cls.env["cyfr.pos.refund.case"]
        cls.product = cls.ten_dollars_with_10_incl.product_variant_id
        cls.reason = cls.env["cyfr.pos.refund.reason"].create({
            "name": "Test: packaging", "code": "TEST_PACKAGING",
            "company_id": cls.env.company.id,
        })
        cls.cashier = cls.env["res.users"].create({
            "name": "Refund evidence cashier", "login": "refund-evidence-cashier-test",
            "company_id": cls.env.company.id,
            "company_ids": [Command.link(cls.env.company.id)],
            "group_ids": [Command.link(cls.env.ref("point_of_sale.group_pos_user").id)],
        })
        cls.other_cashier = cls.env["res.users"].create({
            "name": "Other refund cashier", "login": "other-refund-cashier-test",
            "company_id": cls.env.company.id,
            "company_ids": [Command.link(cls.env.company.id)],
            "group_ids": [Command.link(cls.env.ref("point_of_sale.group_pos_user").id)],
        })
        cls.manager = cls.env["res.users"].create({
            "name": "Refund evidence manager", "login": "refund-evidence-manager-test",
            "company_id": cls.env.company.id,
            "company_ids": [Command.link(cls.env.company.id)],
            "group_ids": [Command.link(cls.env.ref("point_of_sale.group_pos_manager").id)],
        })

    def test_demo_reasons_when_with_demo(self):
        if not tools.config["with_demo"]:
            self.skipTest("Demo records are asserted during --with-demo installs")
        for xmlid in ("reason_damaged", "reason_wrong_item", "reason_changed_mind"):
            reason = self.env.ref("cyfr_pos_refund_evidence.%s" % xmlid, raise_if_not_found=False)
            self.assertTrue(reason, "Missing demo reason %s" % xmlid)
            # The POS test parent runs as an account user in another company.
            # XML ID existence and its declared demo company are checked by
            # the test runner; this setup assertion is not a user-ACL check.
            self.assertEqual(reason.sudo().company_id, self.env.ref("base.main_company"))

    def _sale(self):
        order, _ = self.create_backend_pos_order({
            "line_data": [{"product_id": self.product.id, "qty": 2}],
        })
        order.user_id = self.cashier
        return order

    def _manual_refund(self, source_lines):
        self.pos_config_usd.open_ui()
        order = self.env["pos.order"].create({
            "name": "Evidence test refund", "is_refund": True,
            "company_id": self.env.company.id,
            "session_id": self.pos_config_usd.current_session_id.id,
            "user_id": self.cashier.id,
            "amount_total": 0, "amount_paid": 0, "amount_tax": 0, "amount_return": 0,
            "lines": [Command.create({
                "name": "Refund test line", "product_id": line.product_id.id,
                "qty": -1, "price_unit": line.price_unit,
                "price_subtotal": -line.price_unit,
                "price_subtotal_incl": -line.price_unit,
                "refunded_orderline_id": line.id,
            }) for line in source_lines],
        })
        order._process_saved_order(draft=True)
        return order

    def _refund_ui_payload(self, sale, order_uuid):
        self.pos_config_usd.open_ui()
        return {
            "uuid": order_uuid, "name": "Evidence UI refund %s" % order_uuid,
            "session_id": self.pos_config_usd.current_session_id.id,
            "company_id": self.env.company.id,
            "config_id": self.pos_config_usd.id,
            "pricelist_id": self.pos_config_usd.pricelist_id.id,
            "last_order_preparation_change": "{}",
            "date_order": fields.Datetime.now(),
            "state": "draft", "is_refund": True,
            "lines": [Command.create({
                "uuid": str(uuid4()), "refunded_orderline_id": sale.lines.id,
                "product_id": self.product.id, "qty": -1,
                "price_unit": 10, "price_subtotal": -10,
                "price_subtotal_incl": -10,
            })],
            "payment_ids": [], "amount_paid": 0, "amount_return": 0,
            "amount_tax": 0, "amount_total": -10,
            "user_id": self.cashier.id,
        }

    def test_native_backend_refund_creates_one_case_after_lines(self):
        sale = self._sale()
        before_sale_pickings = sale.picking_ids.ids
        before_sale_move = sale.session_move_id.id
        refund = sale._refund()
        case = self.Case.search([("refund_order_id", "=", refund.id)])
        self.assertEqual(len(case), 1)
        self.assertEqual(case.refund_line_ids, refund.lines)
        self.assertEqual(case.origin_order_count, 1)
        self.assertEqual(case.action_open_origins()["domain"], [("id", "in", sale.ids)])
        self.assertEqual(case.state, "incomplete")
        self.assertFalse(case.recorded_by_id)
        self.assertEqual(sale.picking_ids.ids, before_sale_pickings)
        self.assertEqual(sale.session_move_id.id, before_sale_move)
        self.assertFalse(refund.account_move)
        refund._ensure_refund_evidence_cases()
        self.assertEqual(self.Case.search_count([("refund_order_id", "=", refund.id)]), 1)

    def test_partial_and_multi_origin_per_line(self):
        first = self._sale()
        second = self._sale()
        refund = self._manual_refund(first.lines[:1] | second.lines[:1])
        case = self.Case.search([("refund_order_id", "=", refund.id)])
        self.assertEqual(case.origin_order_count, 2)
        self.assertEqual(set(case.refund_line_ids.mapped("cyfr_original_order_id").ids), set((first | second).ids))
        self.assertEqual(set(case.action_open_origins()["domain"][0][2]), set((first | second).ids))
        self.assertTrue(all(line.qty == -1 for line in refund.lines))
        self.assertEqual(first.lines.refunded_qty, 1)
        self.assertEqual(second.lines.refunded_qty, 1)
        self.assertEqual(self.Case.search_count([("refund_order_id", "=", refund.id)]), 1)
        refund.lines[1].write({"refunded_orderline_id": first.lines.id})
        self.assertEqual(case.origin_order_count, 1)
        self.assertEqual(set(case.refund_line_ids.mapped("cyfr_original_order_id").ids), set(first.ids))

    def test_evidence_capture_and_rpc_integrity(self):
        refund = self._manual_refund(self._sale().lines)
        case = self.Case.search([("refund_order_id", "=", refund.id)])
        own = case.with_user(self.cashier)
        own.write({"reason_id": self.reason.id, "condition_note": "Sealed item returned"})
        self.assertEqual(case.state, "complete")
        self.assertEqual(case.recorded_by_id, self.cashier)
        self.assertTrue(case.captured_at)
        own.write({"condition_note": "   "})
        self.assertEqual(case.state, "incomplete")
        case.write({"manager_note": "Reviewed by manager"})
        self.assertEqual(case.manager_note, "Reviewed by manager")
        for forged in ({"refund_order_id": 999}, {"recorded_by_id": self.other_cashier.id}, {"captured_at": False}, {"manager_note": "fake"}, {"company_id": self.env.company.id}):
            with self.assertRaises(AccessError):
                own.write(forged)
        with self.assertRaises(AccessError):
            self.Case.with_user(self.cashier).create({"refund_order_id": refund.id})
        with self.assertRaises(AccessError):
            own.unlink()
        with self.assertRaises(AccessError):
            self.env["cyfr.pos.refund.reason"].with_user(self.cashier).create({
                "name": "Forged reason", "code": "FORGED",
                "company_id": self.env.company.id,
            })
        other_reason = self.env["cyfr.pos.refund.reason"].create({
            "name": "Inactive", "code": "INACTIVE_TEST", "company_id": self.env.company.id,
            "active": False,
        })
        with self.assertRaises(ValidationError):
            own.write({"reason_id": other_reason.id})

    def test_cashier_owner_and_manager_queue(self):
        refund = self._manual_refund(self._sale().lines)
        case = self.Case.search([("refund_order_id", "=", refund.id)])
        self.assertEqual(self.Case.with_user(self.cashier).search([("id", "=", case.id)]), case)
        self.assertFalse(self.Case.with_user(self.other_cashier).search([("id", "=", case.id)]))
        with self.assertRaises(AccessError):
            case.with_user(self.other_cashier).write({"condition_note": "forged"})
        with self.assertRaises(AccessError):
            case.with_user(self.other_cashier).action_open_origins()
        self.assertIn(case, self.Case.search([("state", "=", "incomplete")]))
        grouped = self.Case._read_group([("id", "=", case.id)], ["config_id"], ["__count"])
        self.assertEqual(grouped, [(refund.config_id, 1)])
        self.assertEqual(len(self.Case._read_group(
            [("id", "=", case.id)],
            ["reason_id", "config_id", "refund_date:day", "company_id"],
            ["__count"],
        )), 1)

    def test_company_isolation_and_foreign_reason(self):
        refund = self._manual_refund(self._sale().lines)
        case = self.Case.search([("refund_order_id", "=", refund.id)])
        other = self.env["res.company"].create({
            "name": "Refund test other company", "country_id": self.env.company.country_id.id,
        })
        foreign_reason = self.env["cyfr.pos.refund.reason"].sudo().create({
            "name": "Other company reason", "code": "OTHER_TEST", "company_id": other.id,
        })
        with self.assertRaises(AccessError):
            self.reason.with_user(self.manager).write({"company_id": other.id})
        with self.assertRaises(AccessError):
            self.env["cyfr.pos.refund.reason"].with_user(self.manager).create({
                "name": "Foreign company reason", "code": "FOREIGN_TEST",
                "company_id": other.id,
            })
        with self.assertRaises(AccessError):
            case.with_user(self.cashier).write({"reason_id": foreign_reason.id})
        with self.assertRaises(ValidationError):
            case.sudo().write({"reason_id": foreign_reason.id})
        case.write({"reason_id": self.reason.id, "condition_note": "Company regression"})
        self.reason.write({"company_id": self.env.company.id})
        with self.assertRaises(ValidationError):
            self.reason.sudo().write({"company_id": other.id})
        config = self.env["pos.config"].with_company(other).create({
            "name": "Other refund test POS", "company_id": other.id,
            "payment_method_ids": [Command.clear()],
        })
        session = self.env["pos.session"].with_company(other).create({
            "config_id": config.id, "state": "opened",
        })
        other_refund = self.env["pos.order"].with_company(other).create({
            "is_refund": True, "company_id": other.id,
            "session_id": session.id, "user_id": self.cashier.id,
            "amount_total": 0, "amount_paid": 0, "amount_tax": 0, "amount_return": 0,
        })
        other_refund._ensure_refund_evidence_cases()
        other_case = self.Case.search([("refund_order_id", "=", other_refund.id)])
        self.assertTrue(other_case)
        self.assertEqual(other_case.origin_order_count, 0)
        self.assertFalse(self.Case.with_user(self.cashier).search([("id", "=", other_case.id)]))
        with self.assertRaises(AccessError):
            other_case.with_user(self.cashier).read(["refund_order_id"])

    def test_unflagged_negative_order_is_not_a_case(self):
        sale = self._sale()
        self.pos_config_usd.open_ui()
        order = self.env["pos.order"].create({
            "company_id": self.env.company.id,
            "session_id": self.pos_config_usd.current_session_id.id,
            "amount_total": -10, "amount_paid": 0, "amount_tax": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.product.id, "qty": -1,
                "price_unit": 10, "price_subtotal": -10, "price_subtotal_incl": -10,
                "refunded_orderline_id": sale.lines.id,
            })],
        })
        order._process_saved_order(draft=True)
        self.assertFalse(self.Case.search([("refund_order_id", "=", order.id)]))

    def test_duplicate_ui_sync_keeps_case(self):
        sale = self._sale()
        refund = self._manual_refund(sale.lines)
        # The native sync path ignores a paid order with the same UUID. The
        # first persistence hook already created the case; re-entry is safe.
        refund.write({"state": "paid"})
        payload = self._refund_ui_payload(sale, refund.uuid)
        refund.sync_from_ui([payload])
        self.assertEqual(self.Case.search_count([("refund_order_id", "=", refund.id)]), 1)
        self.Case.search([("refund_order_id", "=", refund.id)]).sudo().unlink()
        refund.sync_from_ui([payload])
        self.assertEqual(self.Case.search_count([("refund_order_id", "=", refund.id)]), 1)

    def test_fresh_ui_sync_creates_case_with_source_line(self):
        sale = self._sale()
        order_uuid = str(uuid4())
        self.env["pos.order"].sync_from_ui([self._refund_ui_payload(sale, order_uuid)])
        refund = self.env["pos.order"].search([("uuid", "=", order_uuid)])
        case = self.Case.search([("refund_order_id", "=", refund.id)])
        self.assertEqual(len(refund), 1)
        self.assertEqual(len(case), 1)
        self.assertTrue(refund.is_refund)
        self.assertEqual(refund.lines.refunded_orderline_id, sale.lines)
        self.assertEqual(case.refund_line_ids, refund.lines)
        self.assertEqual(case.origin_order_count, 1)
        self.assertEqual(refund.state, "draft")
        self.assertFalse(refund.picking_ids)
        self.assertFalse(refund.account_move)
