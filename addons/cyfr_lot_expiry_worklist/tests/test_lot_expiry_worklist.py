from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..wizard import scan_wizard


@tagged("post_install", "-at_install")
class TestLotExpiryWorklist(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.location_a = cls.env["stock.location"].create({
            "name": "Expiry test shelf A", "usage": "internal",
            "company_id": cls.company.id, "location_id": cls.warehouse.lot_stock_id.id,
        })
        cls.location_b = cls.env["stock.location"].create({
            "name": "Expiry test shelf B", "usage": "internal",
            "company_id": cls.company.id, "location_id": cls.warehouse.lot_stock_id.id,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Expiry test product", "is_storable": True,
            "tracking": "lot", "use_expiration_date": True,
        })
        cls.lot = cls.env["stock.lot"].create({
            "name": "EXPIRY-TEST-LOT", "product_id": cls.product.id,
            "company_id": cls.company.id,
            "expiration_date": fields.Datetime.now() + timedelta(days=4),
            "alert_date": fields.Datetime.now() - timedelta(days=1),
            "use_date": fields.Datetime.now() + timedelta(days=2),
            "removal_date": fields.Datetime.now() + timedelta(days=3),
        })
        cls.owner = cls.env["res.partner"].create({"name": "Expiry test consignor"})

    def _quant(self, location, quantity, reserved=0, owner=False, **values):
        return self.env["stock.quant"].create({
            "product_id": self.product.id, "lot_id": self.lot.id,
            "location_id": location.id, "owner_id": owner.id if owner else False,
            "quantity": quantity, "reserved_quantity": reserved, **values,
        })

    def _scan(self, location=None, horizon=30, user=None, company=None):
        company = company or self.company
        Scan = self.env["cyfr.lot.expiry.scan"]
        if user:
            Scan = Scan.with_user(user)
        scan = Scan.create({
            "company_id": company.id,
            "location_id": (location or self.warehouse.lot_stock_id).id,
            "horizon_days": horizon,
        })
        return scan.action_scan()

    def _rows(self):
        return self.env["cyfr.lot.expiry.entry"].search([
            ("lot_id", "=", self.lot.id),
            ("location_id", "in", [self.location_a.id, self.location_b.id]),
        ])

    def _user(self, name, manager=False, company=None):
        company = company or self.company
        group = self.env.ref("stock.group_stock_manager" if manager else "stock.group_stock_user")
        return self.env["res.users"].create({
            "name": name, "login": "expiry_" + name.lower().replace(" ", "_"),
            "company_id": company.id, "company_ids": [(6, 0, [company.id])],
            "group_ids": [(6, 0, [group.id])],
        })

    def test_location_owner_package_split_and_reserved_quantity(self):
        package = self.env["stock.package"].create({"name": "EXPIRY-TEST-PACK"})
        self._quant(self.location_a, 5, reserved=1)
        self._quant(self.location_a, 2, reserved=1, package_id=package.id)
        self._quant(self.location_b, 3)
        self._quant(self.location_b, 2, owner=self.owner)
        self._quant(self.location_b, 0, owner=self.owner, package_id=package.id)
        action = self._scan()
        rows = self._rows()
        self.assertEqual(len(rows), 3)
        self.assertTrue(set(rows.ids).issubset(set(action["domain"][0][2])))
        own_a = rows.filtered(lambda r: r.location_id == self.location_a and not r.owner_id)
        own_b = rows.filtered(lambda r: r.location_id == self.location_b and not r.owner_id)
        consigned_b = rows.filtered(lambda r: r.location_id == self.location_b and r.owner_id)
        self.assertEqual((own_a.on_hand, own_a.reserved, own_a.physical_unreserved), (7, 2, 5))
        self.assertIn(self.lot.name, own_a.display_name)
        self.assertIn(self.location_a.name, own_a.display_name)
        self.assertIn(self.owner.name, consigned_b.display_name)
        self.assertEqual((own_b.on_hand, own_b.physical_unreserved), (3, 3))
        self.assertEqual((consigned_b.on_hand, consigned_b.owner_key), (2, self.owner.id))
        self.assertEqual({r.expiry_state for r in rows}, {"within_horizon"})
        self.assertTrue(all(rows.mapped("stock_present")))
        self.assertEqual(len(self._rows()), 3, "repeat scan must not duplicate keys")
        self._scan()
        self.assertEqual(len(self._rows()), 3)

    def test_expiration_timestamp_horizon_and_native_removal_semantics(self):
        quant = self._quant(self.location_a, 3, reserved=1)
        now = fields.Datetime.now()
        self.lot.write({
            "expiration_date": now - timedelta(seconds=1),
            "removal_date": now - timedelta(days=1),
        })
        self._scan(location=self.location_a, horizon=0)
        row = self._rows()
        self.assertEqual(row.expiry_state, "expired")
        self.assertEqual(row.physical_unreserved, 2)
        self.assertEqual(quant.available_quantity, 0, "native FEFO availability differs after removal")
        self.lot.expiration_date = now + timedelta(days=40)
        self._scan(location=self.location_a, horizon=30)
        self.assertEqual(row.expiry_state, "outside_horizon")
        self.assertTrue(row.stock_present)
        self.assertEqual(self._scan(location=self.location_a, horizon=30)["domain"], [("id", "in", [])])

    def test_noninternal_zero_negative_and_departed_stock(self):
        positive = self._quant(self.location_a, 4)
        self._scan(location=self.location_a)
        row = self._rows()
        self.assertTrue(row.stock_present)
        transit = self.env["stock.location"].create({
            "name": "Expiry transit", "usage": "transit", "company_id": self.company.id,
        })
        customer = self.env["stock.location"].create({
            "name": "Expiry customer", "usage": "customer", "company_id": self.company.id,
        })
        self._quant(transit, 20)
        self._quant(customer, 20)
        positive.quantity = 0
        self._quant(self.location_b, -2)
        self._scan(location=self.location_a)
        row.invalidate_recordset()
        self.assertFalse(row.stock_present)
        self.assertEqual(row.on_hand, 0)
        self.assertEqual(len(self._rows()), 1)
        self.assertEqual(self._scan(location=self.location_a)["domain"], [("id", "in", [])])

    def test_assignment_acknowledgment_and_direct_rpc(self):
        self._quant(self.location_a, 2)
        self._scan()
        row = self._rows()
        manager = self._user("Expiry manager", manager=True)
        assignee = self._user("Expiry assignee")
        other_user = self._user("Expiry other user")
        wizard = self.env["cyfr.lot.expiry.assign"].with_user(manager).create({
            "entry_id": row.id, "assigned_user_id": assignee.id,
            "next_action": "Check chilled stock", "action_note": "Review handling",
        })
        wizard.action_assign()
        self.assertEqual((row.status, row.assigned_user_id), ("assigned", assignee))
        outsider = self.env["res.users"].create({
            "name": "Expiry non-inventory user", "login": "expiry_non_inventory_user",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(ValidationError):
            self.env["cyfr.lot.expiry.assign"].with_user(manager).create({
                "entry_id": row.id, "assigned_user_id": outsider.id,
                "next_action": "Do not assign",
            }).action_assign()
        self.assertEqual(row.assigned_user_id, assignee)
        with self.assertRaises(AccessError):
            row.with_user(other_user).action_acknowledge()
        with self.assertRaises(AccessError):
            row.with_user(assignee).write({"status": "acknowledged"})
        with self.assertRaises(AccessError):
            self.env["cyfr.lot.expiry.entry"].with_user(manager).create({
                "company_id": self.company.id, "lot_id": self.lot.id,
                "location_id": self.location_a.id,
            })
        row.with_user(assignee).action_acknowledge()
        self.assertEqual(row.status, "acknowledged")
        self.assertEqual(row.acknowledged_by, assignee)
        self.assertTrue(row.acknowledged_at)
        with self.assertRaises(ValidationError):
            row.with_user(assignee).action_acknowledge()
        self._quant(self.location_a, -2)
        self._scan()
        self.assertFalse(row.stock_present)
        self.assertEqual(row.status, "acknowledged", "action history survives stock departure")

    def test_company_scope_and_revoked_linked_lot(self):
        self._quant(self.location_a, 2)
        self._scan()
        row = self._rows()
        reader = self._user("Expiry reader")
        self.assertEqual(row.with_user(reader).read(["status"])[0]["status"], "open")
        with self.assertRaises(AccessError):
            self.env["cyfr.lot.expiry.scan"].with_user(reader).create({
                "company_id": self.company.id, "location_id": self.location_a.id,
            })
        other_company = self.env["res.company"].create({"name": "Expiry other company"})
        other_location = self.env["stock.location"].create({
            "name": "Expiry other shelf", "usage": "internal", "company_id": other_company.id,
        })
        other_action = self.env.ref("cyfr_lot_expiry_worklist.demo_second_company_action")
        self.assertFalse(other_action.with_user(reader).search([("id", "=", other_action.id)]))
        with self.assertRaises(AccessError):
            other_action.with_user(reader).read(["on_hand"])
        with self.assertRaises(AccessError):
            other_action.with_user(reader).export_data(["on_hand"])
        with self.assertRaises(AccessError):
            self._scan(location=other_location, company=other_company, user=reader)
        self.env["ir.rule"].create({
            "name": "Hide expiry test lot", "model_id": self.env.ref("stock.model_stock_lot").id,
            "domain_force": "[('id', '!=', %d)]" % self.lot.id,
        })
        self.assertFalse(self.env["cyfr.lot.expiry.entry"].with_user(reader).search([("id", "=", row.id)]))
        self.assertFalse(self.env["cyfr.lot.expiry.entry"].with_user(reader).read_group(
            [("id", "=", row.id)], ["on_hand:sum"], ["location_id"]))
        with self.assertRaises(AccessError):
            row.with_user(reader).read(["on_hand"])
        with self.assertRaises(AccessError):
            row.with_user(reader).export_data(["on_hand"])

    def test_parent_company_lot_at_child_company_location(self):
        child = self.env["res.company"].create({
            "name": "Expiry child company", "parent_id": self.company.id,
        })
        shelf = self.env["stock.location"].create({
            "name": "Expiry child company shelf", "usage": "internal",
            "company_id": child.id,
        })
        self.env["stock.quant"].with_company(child).create({
            "product_id": self.product.id, "lot_id": self.lot.id,
            "location_id": shelf.id, "quantity": 2,
        })
        scan = self.env["cyfr.lot.expiry.scan"].with_company(child).create({
            "company_id": child.id, "location_id": shelf.id, "horizon_days": 30,
        })
        scan.action_scan()
        row = self.env["cyfr.lot.expiry.entry"].with_company(child).search([
            ("company_id", "=", child.id), ("lot_id", "=", self.lot.id),
            ("location_id", "=", shelf.id),
        ])
        self.assertEqual(len(row), 1)
        self.assertEqual(row.on_hand, 2)

    def test_revoked_product_hides_worklist_and_aborts_scan(self):
        self._quant(self.location_a, 2)
        self._scan(location=self.location_a)
        row = self._rows()
        original = row.observed_at
        manager = self._user("Expiry product-rule manager", manager=True)
        self.env["ir.rule"].create({
            "name": "Hide expiry test product", "model_id": self.env.ref("product.model_product_product").id,
            "domain_force": "[('id', '!=', %d)]" % self.product.id,
            "perm_read": True, "perm_write": False, "perm_create": False, "perm_unlink": False,
        })
        Rows = self.env["cyfr.lot.expiry.entry"].with_user(manager)
        self.assertFalse(Rows.search([("id", "=", row.id)]))
        self.assertFalse(Rows.read_group([("id", "=", row.id)], ["on_hand:sum"], ["location_id"]))
        with self.assertRaises(AccessError):
            row.with_user(manager).read(["product_id"])
        with self.assertRaises(AccessError):
            row.with_user(manager).export_data(["product_id"])
        with self.assertRaises(AccessError):
            row.with_user(manager).action_open_lot()
        scan = self.env["cyfr.lot.expiry.scan"].with_user(manager).create({
            "company_id": self.company.id, "location_id": self.location_a.id,
            "horizon_days": 30,
        })
        with self.assertRaises(AccessError):
            scan.action_scan()
        row.invalidate_recordset()
        self.assertEqual(row.observed_at, original)

    def test_hidden_quant_aborts_without_marking_stock_departed(self):
        quant = self._quant(self.location_a, 2)
        package = self.env["stock.package"].create({"name": "EXPIRY-HIDDEN-QUANT-PACK"})
        self._quant(self.location_a, 1, package_id=package.id)
        self._scan(location=self.location_a)
        row = self._rows()
        original = (row.on_hand, row.stock_present, row.observed_at)
        manager = self._user("Expiry quant-rule manager", manager=True)
        self.env["ir.rule"].create({
            "name": "Hide expiry test quant", "model_id": self.env.ref("stock.model_stock_quant").id,
            "domain_force": "[('id', '!=', %d)]" % quant.id,
            "perm_read": True, "perm_write": False, "perm_create": False, "perm_unlink": False,
        })
        scan = self.env["cyfr.lot.expiry.scan"].with_user(manager).create({
            "company_id": self.company.id, "location_id": self.location_a.id,
            "horizon_days": 30,
        })
        with self.assertRaises(AccessError):
            scan.action_scan()
        with patch.object(scan_wizard, "MAX_QUANTS", 1):
            with self.assertRaises(AccessError):
                scan.action_scan()
        row.invalidate_recordset()
        self.assertEqual((row.on_hand, row.stock_present, row.observed_at), original)

    def test_hidden_prior_action_overflow_is_generic(self):
        self._quant(self.location_a, 2)
        other_lot = self.env["stock.lot"].create({
            "name": "EXPIRY-OTHER-PRIOR-LOT", "product_id": self.product.id,
            "company_id": self.company.id,
            "expiration_date": fields.Datetime.now() + timedelta(days=4),
        })
        self.env["stock.quant"].create({
            "product_id": self.product.id, "lot_id": other_lot.id,
            "location_id": self.location_a.id, "quantity": 1,
        })
        self._scan(location=self.location_a)
        row = self._rows()
        original = row.observed_at
        manager = self._user("Expiry prior-rule manager", manager=True)
        self.env["ir.rule"].create({
            "name": "Hide expiry prior lot", "model_id": self.env.ref("stock.model_stock_lot").id,
            "domain_force": "[('id', '!=', %d)]" % self.lot.id,
            "perm_read": True, "perm_write": False, "perm_create": False, "perm_unlink": False,
        })
        scan = self.env["cyfr.lot.expiry.scan"].with_user(manager).create({
            "company_id": self.company.id, "location_id": self.location_a.id,
            "horizon_days": 30,
        })
        with patch.object(scan_wizard, "MAX_ACTIONS", 1):
            with self.assertRaises(AccessError):
                scan.action_scan()
        row.invalidate_recordset()
        self.assertEqual(row.observed_at, original)

    def test_bounded_scan_rejects_without_partial_updates(self):
        self.assertEqual((scan_wizard.MAX_QUANTS, scan_wizard.MAX_ACTIONS), (5000, 1000))
        scan_view = self.env.ref("cyfr_lot_expiry_worklist.view_lot_expiry_scan_form")
        self.assertIn("5,000 lot quants", scan_view.arch_db)
        self.assertIn("1,000 lot positions", scan_view.arch_db)
        self._quant(self.location_a, 3)
        self._quant(self.location_a, 1, owner=self.owner)
        with patch.object(scan_wizard, "MAX_QUANTS", 1):
            with self.assertRaises(ValidationError):
                self._scan(location=self.location_a)
        self.assertFalse(self._rows())
        with patch.object(scan_wizard, "MAX_ACTIONS", 1):
            with self.assertRaises(ValidationError):
                self._scan(location=self.location_a)
        self.assertFalse(self._rows())
        self._scan(location=self.location_a)
        rows = self._rows()
        self.assertEqual(len(rows), 2)
        original = {row.id: row.observed_at for row in rows}
        with patch.object(scan_wizard, "MAX_ACTIONS", 1):
            with self.assertRaises(ValidationError):
                self._scan(location=self.location_a)
        rows.invalidate_recordset()
        self.assertEqual({row.id: row.observed_at for row in rows}, original)

    def test_demo_loaded_and_native_drilldowns(self):
        demo = self.env.ref("cyfr_lot_expiry_worklist.demo_acknowledged_action", raise_if_not_found=False)
        second = self.env.ref("cyfr_lot_expiry_worklist.demo_second_company_action", raise_if_not_found=False)
        negative = self.env.ref("cyfr_lot_expiry_worklist.demo_negative_quant", raise_if_not_found=False)
        self.assertTrue(demo, "demo action must load in the demo lifecycle")
        self.assertTrue(second, "second-company demo action must load")
        self.assertTrue(negative, "negative-quantity demo quant must load")
        self.assertLess(negative.quantity, 0)
        self.assertEqual(demo.status, "acknowledged")
        self.assertNotEqual(demo.company_id, second.company_id)
        self.assertEqual(demo.action_open_lot()["res_id"], demo.lot_id.id)
        self.assertEqual(demo.action_open_quants()["res_model"], "stock.quant")
