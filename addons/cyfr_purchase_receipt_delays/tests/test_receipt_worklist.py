from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import config


@tagged("post_install", "-at_install")
class TestReceiptWorklist(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vendor = cls.env["res.partner"].create({"name": "Worklist Vendor", "supplier_rank": 1})
        cls.product = cls.env["product.product"].create({
            "name": "Worklist Warehouse Item", "type": "consu", "purchase_ok": True,
        })
        cls.service = cls.env["product.product"].create({
            "name": "Worklist Service", "type": "service", "purchase_ok": True,
        })
        cls.today = fields.Date.context_today(cls.env["cyfr.purchase.receipt.worklist"])

    def _order(self, *, state="purchase", company=None, dropship=False):
        company = company or self.company
        values = {
            "partner_id": self.vendor.id,
            "company_id": company.id,
            "user_id": self.env.user.id,
        }
        if dropship:
            values["dest_address_id"] = self.env["res.partner"].create({"name": "Drop Destination"}).id
        order = self.env["purchase.order"].with_company(company).create(values)
        if state != "draft":
            order.write({"state": state})
        return order

    def _line(self, order, *, planned=0, qty=5, product=None, display_type=False):
        values = {"order_id": order.id, "name": "Worklist test line", "product_qty": qty}
        if display_type:
            values["display_type"] = display_type
        else:
            product = product or self.product
            values.update({
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "date_planned": datetime.combine(self.today + timedelta(days=planned), datetime.min.time()).replace(hour=12),
                "price_unit": 10,
            })
        return self.env["purchase.order.line"].with_company(order.company_id).with_context(bypass_move_update=True).create(values)

    def _scan(self, **filters):
        wizard = self.env["cyfr.purchase.receipt.worklist"].create(filters)
        action = wizard.action_scan()
        self.assertEqual(action["domain"], [("worklist_id", "=", wizard.id)])
        return wizard

    def _move(self, line, qty, *, returned=False):
        supplier = self.env.ref("stock.stock_location_suppliers")
        stock = self.env.ref("stock.stock_location_stock")
        values = {
            "product_id": line.product_id.id,
            "product_uom": line.product_uom_id.id,
            "product_uom_qty": qty,
            "quantity": qty,
            "location_id": stock.id if returned else supplier.id,
            "location_dest_id": supplier.id if returned else stock.id,
            "purchase_line_id": line.id,
            "company_id": line.company_id.id,
            "state": "done",
        }
        if returned:
            values["to_refund"] = True
        move = self.env["stock.move"].with_company(line.company_id).create(values)
        line.invalidate_recordset(["qty_received"])
        return move

    def test_late_due_soon_future_cancelled_section_service_and_dropship(self):
        order = self._order()
        late = self._line(order, planned=-3)
        soon = self._line(order, planned=2)
        future = self._line(order, planned=20)
        section = self._line(order, display_type="line_section")
        service = self._line(order, planned=-2, product=self.service)
        cancelled = self._line(self._order(state="cancel"), planned=-2)
        dropship = self._line(self._order(dropship=True), planned=-2)
        wizard = self._scan(vendor_id=self.vendor.id)
        self.assertEqual(set(wizard.line_ids.purchase_line_id.ids), {late.id, soon.id})
        self.assertEqual({row.purchase_line_id.id: row.status for row in wizard.line_ids},
                         {late.id: "late", soon.id: "soon"})
        self.assertFalse(set((future | section | service | cancelled | dropship).ids) &
                         set(wizard.line_ids.purchase_line_id.ids))

    def test_partial_return_overreceipt_and_uom_precision(self):
        order = self._order()
        line = self._line(order, planned=-1, qty=5)
        receipt = self._move(line, 3)
        self.assertAlmostEqual(line.qty_received, 3)
        wizard = self._scan(vendor_id=self.vendor.id)
        row = wizard.line_ids.filtered(lambda r: r.purchase_line_id == line)
        self.assertAlmostEqual(row.remaining_qty, 2)
        self.assertIn(receipt, row.purchase_line_id.move_ids)
        self._move(line, 1, returned=True)
        self.assertAlmostEqual(line.qty_received, 2)
        wizard.action_scan()
        row = wizard.line_ids.filtered(lambda r: r.purchase_line_id == line)
        self.assertAlmostEqual(row.remaining_qty, 3)
        self._move(line, 4)
        self.assertAlmostEqual(line.qty_received, 6)
        wizard.action_scan()
        self.assertFalse(wizard.line_ids.filtered(lambda r: r.purchase_line_id == line))
        self.assertEqual(line.product_uom_id.compare(0.000001, 0), 0)

    def test_date_timezone_missing_and_filter_validation(self):
        wizard = self.env["cyfr.purchase.receipt.worklist"].with_context(tz="Pacific/Honolulu").create({})
        self.assertEqual(wizard.with_context(lang="en_US").display_name, "Late Receipts")
        at_utc_midnight = datetime.combine(self.today, datetime.min.time()).replace(hour=2)
        local_day = wizard._local_day(at_utc_midnight)
        self.assertEqual(local_day, (self.today - timedelta(days=1)))
        self.assertEqual(wizard._status(at_utc_midnight, self.today, 7), "late")
        self.assertEqual(wizard._status(False, self.today, 7), "missing")
        self.assertFalse(wizard._status(self.today + timedelta(days=10), self.today, 7))
        self.assertEqual(wizard._end_utc(self.today).hour, 10)
        with self.assertRaises(ValidationError):
            self.env["cyfr.purchase.receipt.worklist"].create({"horizon_days": 91})
        with self.assertRaises(ValidationError):
            self.env["cyfr.purchase.receipt.worklist"].create({
                "date_from": self.today + timedelta(days=1), "date_to": self.today,
            })

    def test_filters_bound_and_rescan_clear_stale_results(self):
        first = self._line(self._order(), planned=-5)
        second = self._line(self._order(), planned=-4)
        third = self._line(self._order(), planned=-3)
        with patch("odoo.addons.cyfr_purchase_receipt_delays.models.receipt_worklist.MAX_CANDIDATES", 2):
            wizard = self._scan(vendor_id=self.vendor.id)
        self.assertTrue(wizard.truncated)
        self.assertEqual(wizard.candidate_count, 2)
        self.assertTrue(set(wizard.line_ids.purchase_line_id.ids) <= {first.id, second.id, third.id})
        wizard.write({"horizon_days": 0})
        self.assertFalse(wizard.scanned_at)
        self.assertFalse(wizard.line_ids)
        wizard.action_scan()
        self.assertEqual(wizard.result_count, len(wizard.line_ids))
        with patch("odoo.addons.cyfr_purchase_receipt_delays.models.receipt_worklist.MAX_RESULTS", 2):
            wizard.action_scan()
        self.assertTrue(wizard.truncated)
        self.assertEqual(wizard.result_count, 2)

    def test_vendor_buyer_date_and_archived_product_filters(self):
        own = self._line(self._order(), planned=-2)
        later = self._line(self._order(), planned=3)
        other_vendor = self.env["res.partner"].create({"name": "Other worklist vendor"})
        other_order = self._order()
        other_order.partner_id = other_vendor
        self._line(other_order, planned=-2)
        self.product.active = False
        wizard = self._scan(vendor_id=self.vendor.id, buyer_id=self.env.user.id,
                            date_from=self.today - timedelta(days=3),
                            date_to=self.today - timedelta(days=1))
        self.assertEqual(wizard.line_ids.purchase_line_id.ids, [own.id])
        wizard.write({"date_from": self.today + timedelta(days=2),
                      "date_to": self.today + timedelta(days=4)})
        wizard.action_scan()
        self.assertEqual(wizard.line_ids.purchase_line_id.ids, [later.id])

    def test_scan_changes_only_transient_records_and_activity_is_native(self):
        line = self._line(self._order(), planned=-1)
        order = line.order_id
        before = line.read(["write_date", "date_planned", "product_qty", "qty_received"])[0]
        order_before = order.read(["write_date", "state"])[0]
        move_count = self.env["stock.move"].search_count([("purchase_line_id", "=", line.id)])
        wizard = self._scan(vendor_id=self.vendor.id)
        row = wizard.line_ids.filtered(lambda r: r.purchase_line_id == line)
        self.assertEqual(line.read(["write_date", "date_planned", "product_qty", "qty_received"])[0], before)
        self.assertEqual(order.read(["write_date", "state"])[0], order_before)
        self.assertEqual(self.env["stock.move"].search_count([("purchase_line_id", "=", line.id)]), move_count)
        action = row.action_schedule_activity()
        self.assertEqual(action["res_model"], "mail.activity")
        self.assertEqual(action["context"]["default_res_id"], order.id)
        self.assertIn(str(line.id), action["context"]["default_summary"])
        self.assertEqual(order.read(["write_date", "state"])[0], order_before)
        self.assertEqual(self.env["mail.activity"].search_count([
            ("res_model", "=", "purchase.order"), ("res_id", "=", order.id),
        ]), 0)
        order.write({"state": "cancel"})
        with self.assertRaises(UserError):
            row.action_schedule_activity()

    def test_company_and_owner_access(self):
        other = self.env["res.company"].create({"name": "Worklist Other Company", "country_id": self.company.country_id.id})
        own = self._line(self._order(), planned=-1)
        foreign = self._line(self._order(company=other), planned=-1)
        purchase_group = self.env.ref("purchase.group_purchase_user")
        buyer = self.env["res.users"].create({
            "name": "Worklist Buyer", "login": "worklist-buyer-test", "company_id": self.company.id,
            "company_ids": [Command.link(self.company.id)], "group_ids": [Command.link(purchase_group.id)],
        })
        other_buyer = self.env["res.users"].create({
            "name": "Worklist Other Buyer", "login": "worklist-other-buyer-test",
            "company_id": self.company.id,
            "company_ids": [Command.link(self.company.id)], "group_ids": [Command.link(purchase_group.id)],
        })
        own_wizard = self.env["cyfr.purchase.receipt.worklist"].with_user(buyer).create({
            "vendor_id": self.vendor.id,
        })
        own_wizard.action_scan()
        self.assertIn(own.id, own_wizard.line_ids.purchase_line_id.ids)
        self.assertNotIn(foreign.id, own_wizard.line_ids.purchase_line_id.ids)
        with self.assertRaises(AccessError):
            own_wizard.with_user(other_buyer).action_open_results()
        with self.assertRaises(AccessError):
            own_wizard.line_ids[:1].with_user(other_buyer).action_schedule_activity()
        with self.assertRaises(AccessError):
            self.env["cyfr.purchase.receipt.worklist"].with_user(buyer).create({"company_id": other.id}).action_scan()
        with self.assertRaises(AccessError):
            self.env["purchase.order.line"].browse(foreign.id).with_user(buyer).check_access("read")

    def test_activity_rechecks_purchase_order_write_permission(self):
        line = self._line(self._order(), planned=-1)
        purchase_group = self.env.ref("purchase.group_purchase_user")
        buyer = self.env["res.users"].create({
            "name": "Worklist Read Only Order Buyer", "login": "worklist-write-denied-test",
            "company_id": self.company.id, "company_ids": [Command.link(self.company.id)],
            "group_ids": [Command.link(purchase_group.id)],
        })
        wizard = self.env["cyfr.purchase.receipt.worklist"].with_user(buyer).create({
            "vendor_id": self.vendor.id,
        })
        wizard.action_scan()
        row = wizard.line_ids.filtered(lambda r: r.purchase_line_id.id == line.id)
        self.assertTrue(row)
        self.env["ir.rule"].create({
            "name": "Worklist test deny one PO write",
            "model_id": self.env.ref("purchase.model_purchase_order").id,
            "domain_force": "[('id', '!=', %d)]" % line.order_id.id,
            "perm_read": False, "perm_write": True, "perm_create": False, "perm_unlink": False,
        })
        with self.assertRaises(AccessError):
            row.action_schedule_activity()

    def test_direct_rpc_cannot_forge_or_edit_scan_results(self):
        line = self._line(self._order(), planned=-1)
        buyer = self.env["res.users"].create({
            "name": "Worklist Integrity Buyer", "login": "worklist-integrity-test",
            "company_id": self.company.id, "company_ids": [Command.link(self.company.id)],
            "group_ids": [Command.link(self.env.ref("purchase.group_purchase_user").id)],
        })
        Wizard = self.env["cyfr.purchase.receipt.worklist"].with_user(buyer)
        Row = self.env["cyfr.purchase.receipt.worklist.line"].with_user(buyer)
        with self.assertRaises(AccessError):
            Wizard.create({"owner_id": self.env.user.id})
        wizard = Wizard.create({"vendor_id": self.vendor.id})
        wizard.action_scan()
        row = wizard.line_ids.filtered(lambda r: r.purchase_line_id.id == line.id)
        self.assertTrue(row)
        with self.assertRaises(AccessError):
            wizard.write({"scanned_at": fields.Datetime.now()})
        with self.assertRaises(AccessError):
            wizard.write({"line_ids": [Command.clear()]})
        with self.assertRaises(AccessError):
            Row.create({"worklist_id": wizard.id, "purchase_line_id": line.id,
                        "status": "late", "remaining_qty": 999})
        with self.assertRaises(AccessError):
            row.write({"remaining_qty": 999})
        with self.assertRaises(AccessError):
            row.unlink()
        self.assertEqual(wizard.line_ids.ids, row.ids)
        wizard.write({"horizon_days": 5})
        self.assertFalse(wizard.line_ids)
        self.assertFalse(wizard.scanned_at)

    def test_source_rule_change_hides_stale_snapshot_even_on_direct_read(self):
        line = self._line(self._order(), planned=-1)
        buyer = self.env["res.users"].create({
            "name": "Worklist Restricted Buyer", "login": "worklist-restricted-test",
            "company_id": self.company.id, "company_ids": [Command.link(self.company.id)],
            "group_ids": [Command.link(self.env.ref("purchase.group_purchase_user").id)],
        })
        wizard = self.env["cyfr.purchase.receipt.worklist"].with_user(buyer).create({
            "vendor_id": self.vendor.id,
        })
        wizard.action_scan()
        row = wizard.line_ids.filtered(lambda r: r.purchase_line_id.id == line.id)
        self.assertTrue(row)
        self.env["ir.rule"].create({
            "name": "Worklist test hide one source line",
            "model_id": self.env.ref("purchase.model_purchase_order_line").id,
            "domain_force": "[('id', '!=', %d)]" % line.id,
            "perm_read": True, "perm_write": False, "perm_create": False, "perm_unlink": False,
        })
        self.assertFalse(self.env["cyfr.purchase.receipt.worklist.line"].with_user(buyer).search([
            ("id", "=", row.id),
        ]))
        with self.assertRaises(AccessError):
            row.read(["remaining_qty"])
        with self.assertRaises(AccessError):
            row.export_data(["remaining_qty"])
        with self.assertRaises(AccessError):
            row.action_schedule_activity()

    def test_purchase_only_menu_and_demo(self):
        menu = self.env.ref("cyfr_purchase_receipt_delays.menu_receipt_worklist")
        action = self.env.ref("cyfr_purchase_receipt_delays.action_receipt_worklist")
        self.assertEqual(menu.action, action)
        self.assertEqual(action.res_model, "cyfr.purchase.receipt.worklist")
        internal = self.env["res.users"].create({
            "name": "Worklist Internal", "login": "worklist-internal-test",
            "group_ids": [Command.link(self.env.ref("base.group_user").id)],
        })
        with self.assertRaises(AccessError):
            self.env["cyfr.purchase.receipt.worklist"].with_user(internal).create({})
        if config["with_demo"]:
            for xmlid in ("demo_vendor", "demo_product", "demo_service", "demo_order_open",
                          "demo_order_cancelled", "demo_line_late", "demo_line_soon",
                          "demo_line_section", "demo_line_service", "demo_line_cancelled"):
                self.assertTrue(self.env.ref("cyfr_purchase_receipt_delays." + xmlid,
                                             raise_if_not_found=False), xmlid)
