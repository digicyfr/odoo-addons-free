from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import exception_queue


@tagged("post_install", "-at_install")
class TestStockExceptionQueue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env.ref("stock.warehouse0")
        cls.location = cls.env["stock.location"].create({
            "name": "Queue test shelf", "usage": "internal", "company_id": cls.company.id,
            "location_id": cls.warehouse.lot_stock_id.id,
        })
        cls.scope = cls.env["cyfr.stock.exception.scope"].create({
            "name": "Queue test", "company_id": cls.company.id,
            "warehouse_id": cls.warehouse.id, "location_id": cls.location.id,
            "zero_days": 1,
        })

    def _product(self, name):
        return self.env["product.product"].create({"name": name, "is_storable": True})

    def _quant(self, product, quantity, reserved=0, **values):
        return self.env["stock.quant"].create({
            "product_id": product.id, "location_id": self.location.id,
            "quantity": quantity, "reserved_quantity": reserved, **values,
        })

    def _orderpoint(self, product, minimum):
        return self.env["stock.warehouse.orderpoint"].create({
            "warehouse_id": self.warehouse.id, "location_id": self.location.id,
            "company_id": self.company.id, "product_id": product.id,
            "product_min_qty": minimum, "product_max_qty": minimum + 2,
            "trigger": "manual",
        })

    def _row(self, product):
        return self.env["cyfr.stock.exception.row"].search([
            ("scope_id", "=", self.scope.id), ("product_id", "=", product.id),
        ], limit=1)

    def test_negative_reserved_and_orderpoint_without_quant(self):
        self.assertTrue(self.scope.is_stale)
        negative = self._product("Queue negative")
        reserved = self._product("Queue reserved")
        empty = self._product("Queue no quant")
        self._quant(negative, -2)
        self._quant(reserved, 6, reserved=5)
        self._orderpoint(reserved, 3)
        self._orderpoint(empty, 2)
        moves_before = self.env["stock.move"].search_count([])
        rules_before = self.env["stock.warehouse.orderpoint"].search_count([])
        self.scope.action_scan_batch()
        self.assertFalse(self.scope.is_stale)
        self.assertEqual((self._row(negative).free_qty, self._row(negative).severity), (-2, "negative"))
        self.assertEqual((self._row(reserved).free_qty, self._row(reserved).severity), (1, "below_min"))
        self.assertEqual((self._row(empty).free_qty, self._row(empty).severity), (0, "below_min"))
        self.assertFalse(self._row(empty).is_persistent_zero)
        self.scope.action_scan_batch()
        self.assertEqual(self._row(empty).severity, "below_min")
        self.assertFalse(self._row(empty).is_persistent_zero, "one day must elapse even after two scans")
        self._row(empty).sudo().first_zero_at = fields.Datetime.now() - timedelta(days=2)
        self.scope.action_scan_batch()
        self.assertEqual(self._row(empty).severity, "below_min")
        self.assertTrue(self._row(empty).is_persistent_zero)
        self.assertEqual(self.env["stock.move"].search_count([]), moves_before)
        self.assertEqual(self.env["stock.warehouse.orderpoint"].search_count([]), rules_before)

    def test_lot_package_aggregation_and_consignment_exclusion(self):
        product = self._product("Queue lots")
        lot_a = self.env["stock.lot"].create({"name": "QA", "product_id": product.id, "company_id": self.company.id})
        lot_b = self.env["stock.lot"].create({"name": "QB", "product_id": product.id, "company_id": self.company.id})
        package = self.env["stock.package"].create({"name": "QUEUE-PACK"})
        self._quant(product, 3, lot_id=lot_a.id)
        self._quant(product, 2, reserved=1, lot_id=lot_b.id, package_id=package.id)
        owner = self.env["res.partner"].create({"name": "Demo consignor"})
        self._quant(product, 50, owner_id=owner.id)
        self._orderpoint(product, 5)
        self.scope.action_scan_batch()
        row = self._row(product)
        self.assertEqual((row.on_hand, row.reserved, row.free_qty), (5, 1, 4))
        self.assertEqual(row.severity, "below_min")

    def test_first_zero_persistence_reset_and_resolution(self):
        product = self._product("Queue zero transition")
        rule = self._orderpoint(product, 0)
        self.scope.action_scan_batch()
        row = self._row(product)
        self.assertEqual(row.severity, "normal")
        self.assertTrue(row.first_zero_at)
        row.sudo().first_zero_at = fields.Datetime.now() - timedelta(days=2)
        self.scope.action_scan_batch()
        self.assertEqual(row.severity, "persistent_zero")
        self.assertTrue(row.is_persistent_zero)
        quant = self._quant(product, 3)
        self.scope.action_scan_batch()
        self.assertEqual(row.severity, "normal")
        self.assertFalse(row.first_zero_at)
        self.assertFalse(row.is_persistent_zero)
        quant.unlink()
        rule.unlink()
        self.scope.action_scan_batch()
        self.assertFalse(row.is_exception)
        self.assertFalse(row.first_zero_at)
        self.assertFalse(row.is_persistent_zero)

    def test_zero_day_threshold_still_needs_second_scan(self):
        self.scope.zero_days = 0
        product = self._product("Queue immediate zero")
        self._orderpoint(product, 0)
        self.scope.action_scan_batch()
        row = self._row(product)
        self.assertEqual(row.severity, "normal")
        self.assertTrue(row.first_zero_at)
        self.scope.action_scan_batch()
        self.assertEqual(row.severity, "persistent_zero")
        self.assertTrue(row.is_persistent_zero)

    def test_only_internal_company_stock_and_bounded_resume(self):
        products = [self._product("Queue page %d" % n) for n in range(3)]
        for product in products:
            self._quant(product, -1)
        transit = self.env["stock.location"].create({
            "name": "Queue transit", "usage": "transit", "company_id": self.company.id,
        })
        ignored = self._product("Queue transit only")
        self.env["stock.quant"].create({"product_id": ignored.id, "location_id": transit.id, "quantity": -3})
        inactive = self.env["stock.location"].create({
            "name": "Queue inactive shelf", "usage": "internal", "company_id": self.company.id,
            "location_id": self.location.id,
        })
        inactive.active = False
        archived_product = self._product("Queue inactive location only")
        self.env["stock.quant"].create({
            "product_id": archived_product.id, "location_id": inactive.id, "quantity": -2,
        })
        with patch.object(exception_queue, "BATCH_SIZE", 2):
            self.scope.action_scan_batch()
            self.assertEqual(self.scope.state, "running")
            self.assertEqual(self.env["cyfr.stock.exception.row"].search_count([
                ("scope_id", "=", self.scope.id), ("is_exception", "=", True)]), 2)
            self.scope.action_scan_batch()
            self.assertEqual(self.scope.state, "idle")
        self.assertEqual(self.env["cyfr.stock.exception.row"].search_count([
            ("scope_id", "=", self.scope.id), ("is_exception", "=", True)]), 3)
        self.assertFalse(self._row(ignored))
        self.assertFalse(self._row(archived_product))

    def test_user_permissions_and_company_rule(self):
        reader = self.env["res.users"].create({
            "name": "Queue reader", "login": "queue_reader_test",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])],
        })
        product = self._product("Queue reader product")
        self._quant(product, -1)
        self.scope.action_scan_batch()
        self.assertTrue(self.env["cyfr.stock.exception.row"].with_user(reader).search([
            ("scope_id", "=", self.scope.id)]))
        with self.assertRaises(AccessError):
            self.scope.with_user(reader).action_scan_batch()
        with self.assertRaises(AccessError):
            self.env["cyfr.stock.exception.scope"].with_user(reader).cron_refresh()
        with self.assertRaises(AccessError):
            self.env["cyfr.stock.exception.row"].with_user(reader).create({
                "scope_id": self.scope.id, "company_id": self.company.id,
                "product_id": product.id, "location_id": self.location.id,
            })
        other = self.env["res.company"].create({"name": "Queue other company"})
        other_warehouse = self.env["stock.warehouse"].create({
            "name": "Queue other WH", "code": "QOTH", "company_id": other.id,
        })
        other_scope = self.env["cyfr.stock.exception.scope"].with_company(other).create({
            "name": "Other queue", "company_id": other.id,
            "warehouse_id": other_warehouse.id, "location_id": other_warehouse.lot_stock_id.id,
        })
        self.assertFalse(self.env["cyfr.stock.exception.scope"].with_user(reader).search([
            ("id", "=", other_scope.id)]))

    def test_linked_product_and_location_rules_protect_snapshot(self):
        reader = self.env["res.users"].create({
            "name": "Queue restricted reader", "login": "queue_restricted_reader_test",
            "company_id": self.company.id,
            "company_ids": [(6, 0, [self.company.id])],
            "group_ids": [(6, 0, [self.env.ref("stock.group_stock_user").id])],
        })
        product = self._product("Queue hidden source")
        self._quant(product, -1)
        self.scope.action_scan_batch()
        row = self._row(product)
        self.env["ir.rule"].create({
            "name": "Queue test hide one product", "model_id": self.env.ref("product.model_product_product").id,
            "domain_force": "[('id', '!=', %d)]" % product.id,
        })
        reader_rows = self.env["cyfr.stock.exception.row"].with_user(reader)
        self.assertFalse(reader_rows.search([("id", "=", row.id)]))
        with self.assertRaises(AccessError):
            row.with_user(reader).read(["free_qty"])
        with self.assertRaises(AccessError):
            row.with_user(reader).export_data(["free_qty"])
        self.env["ir.rule"].create({
            "name": "Queue test hide one location", "model_id": self.env.ref("stock.model_stock_location").id,
            "domain_force": "[('id', '!=', %d)]" % self.location.id,
        })
        self.assertFalse(self.env["cyfr.stock.exception.scope"].with_user(reader).search([
            ("id", "=", self.scope.id)]))

    def test_invalid_scope_and_cron_idempotence(self):
        transit = self.env["stock.location"].create({
            "name": "Invalid queue transit", "usage": "transit", "company_id": self.company.id,
        })
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.scope.location_id = transit
        self.scope.invalidate_recordset()
        product = self._product("Queue cron")
        self._quant(product, -1)
        self.env["cyfr.stock.exception.scope"].cron_refresh()
        self.env["cyfr.stock.exception.scope"].cron_refresh()
        self.assertEqual(self.env["cyfr.stock.exception.row"].search_count([
            ("scope_id", "=", self.scope.id), ("product_id", "=", product.id)]), 1)

    def test_parent_company_product_in_child_company_stock(self):
        child = self.env["res.company"].create({"name": "Queue child company", "parent_id": self.company.id})
        warehouse = self.env["stock.warehouse"].create({
            "name": "Queue child warehouse", "code": "QCHD", "company_id": child.id,
        })
        product = self.env["product.product"].create({
            "name": "Queue parent-owned product", "company_id": self.company.id, "is_storable": True,
        })
        scope = self.env["cyfr.stock.exception.scope"].with_company(child).create({
            "name": "Queue child scope", "company_id": child.id,
            "warehouse_id": warehouse.id, "location_id": warehouse.lot_stock_id.id,
        })
        self.env["stock.quant"].with_company(child).create({
            "product_id": product.id, "location_id": warehouse.lot_stock_id.id, "quantity": -2,
        })
        scope.with_company(child).action_scan_batch()
        row = self.env["cyfr.stock.exception.row"].with_company(child).search([
            ("scope_id", "=", scope.id), ("product_id", "=", product.id),
        ])
        self.assertEqual((row.free_qty, row.severity), (-2, "negative"))

    def test_scope_location_cap_and_cron_fairness(self):
        self.env["stock.location"].create([{
            "name": "Queue fanout %d" % n,
            "usage": "internal", "company_id": self.company.id,
            "location_id": self.location.id,
        } for n in range(50)])
        with self.assertRaises(ValidationError):
            self.scope.action_scan_batch()
        self.env["stock.location"].search([
            ("location_id", "=", self.location.id), ("name", "like", "Queue fanout")
        ]).unlink()
        other_location = self.env["stock.location"].create({
            "name": "Queue fair scope shelf", "usage": "internal", "company_id": self.company.id,
            "location_id": self.warehouse.lot_stock_id.id,
        })
        other_scope = self.env["cyfr.stock.exception.scope"].create({
            "name": "Queue fair scope", "company_id": self.company.id,
            "warehouse_id": self.warehouse.id, "location_id": other_location.id,
        })
        self.env["cyfr.stock.exception.scope"].search([
            ("id", "not in", [self.scope.id, other_scope.id]),
        ]).write({"active": False})
        for n in range(2):
            self._quant(self._product("Queue fair page %d" % n), -1)
        other_product = self._product("Queue fair other")
        self.env["stock.quant"].create({
            "product_id": other_product.id, "location_id": other_location.id, "quantity": -1,
        })
        with patch.object(exception_queue, "BATCH_SIZE", 1):
            self.env["cyfr.stock.exception.scope"].cron_refresh()
            self.assertTrue(self.scope.last_batch_at)
            self.assertFalse(other_scope.last_batch_at)
            self.assertEqual(self.scope.state, "running")
            first_cursor = self.scope.scan_cursor
            self.env["cyfr.stock.exception.scope"].cron_refresh()
            self.assertTrue(other_scope.last_batch_at)
            self.assertEqual(self.scope.scan_cursor, first_cursor)
            self.env["cyfr.stock.exception.scope"].cron_refresh()
            self.assertEqual(len(self.scope.row_ids), 2)

    def test_demo_records_loaded(self):
        ids = ["demo_scope", "demo_location_shelf", "demo_product_normal",
               "demo_product_negative", "demo_product_reserved", "demo_product_no_quant",
               "demo_quant_normal", "demo_quant_negative", "demo_quant_reserved",
               "demo_orderpoint_reserved", "demo_orderpoint_no_quant"]
        for xml_id in ids:
            self.assertTrue(self.env.ref("cyfr_stock_exception_queue." + xml_id, raise_if_not_found=False), xml_id)
