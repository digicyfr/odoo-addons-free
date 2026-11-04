import base64
import struct
import zlib
from unittest.mock import patch

from psycopg2 import IntegrityError
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import product_health


@tagged("post_install", "-at_install")
class TestProductDataHealth(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["product.category"].create({"name": "Health Test Goods"})
        cls.policy = cls.env.ref("cyfr_product_data_health.policy_default")

    def _product(self, name, **values):
        template = self.env["product.template"].create({
            "name": name,
            "sale_ok": True,
            "categ_id": self.category.id,
            "list_price": 10,
            **values,
        })
        return template.product_variant_id

    def _scan(self, company=None):
        return self.env["cyfr.product.health.scan"].create({
            "company_id": (company or self.env.company).id,
        })

    @staticmethod
    def _one_pixel_image():
        def chunk(name, data):
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(b"\x00\x00\xaa\x66\xff"))
        png += chunk(b"IEND", b"")
        return base64.b64encode(png)

    def test_default_checks_and_replacement(self):
        product = self._product("Health Missing Everything", list_price=0)
        first = self._scan()
        first.action_scan_batch()
        issue = first.issue_ids.filtered(lambda row: row.product_id == product)
        self.assertEqual(len(issue), 1)
        self.assertEqual(set(issue.issue_codes.split(",")), {
            "missing_internal_reference", "missing_barcode", "non_positive_sale_price", "missing_image",
        })
        self.assertTrue(first.is_current)
        self.assertIn(product.name, issue.display_name)
        self.assertIn(issue.id, [row_id for row_id, _name in self.env["cyfr.product.health.issue"].name_search(product.name)])

        second = self._scan()
        self.assertTrue(first.is_current, "Old results stay current while the replacement is incomplete")
        second.action_scan_batch()
        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)
        with self.assertRaises(ValidationError):
            second.action_scan_batch()

    def test_policy_precedence_and_disabled_checks(self):
        product = self._product("Health Policy Scope")
        company_policy = self.env["cyfr.product.health.policy"].create({
            "name": "Company wide",
            "company_id": self.env.company.id,
            "check_barcode": False,
        })
        category_policy = self.env["cyfr.product.health.policy"].create({
            "name": "Category override",
            "company_id": self.env.company.id,
            "categ_id": self.category.id,
            "check_barcode": True,
            "check_image": False,
        })
        scan = self._scan()
        scan.action_scan_batch()
        row = scan.issue_ids.filtered(lambda issue: issue.product_id == product)
        self.assertEqual(row.policy_id, category_policy)
        self.assertIn("missing_barcode", row.issue_codes)
        self.assertNotIn("missing_image", row.issue_codes)
        with self.assertRaises(ValidationError):
            self.env["cyfr.product.health.policy"].create({
                "name": "Conflicting", "company_id": self.env.company.id,
            })
        self.assertTrue(company_policy.active)

    def test_batch_continuation(self):
        products = [self._product("Health Batch %s" % index) for index in range(3)]
        scan = self._scan()
        with patch.object(product_health, "BATCH_SIZE", 2):
            while scan.state != "done":
                scan.action_scan_batch()
        self.assertGreaterEqual(scan.processed_count, 3)
        self.assertTrue(all(scan.issue_ids.filtered(lambda row: row.product_id == p) for p in products))
        self.assertEqual(scan.issue_count, len(scan.issue_ids))
        self.assertEqual(len(scan.issue_ids.mapped("product_id")), len(scan.issue_ids))

    def test_company_visibility_and_manager_boundary(self):
        other = self.env["res.company"].create({"name": "Other Health Company"})
        own_product = self._product("Health Own Product")
        foreign_product = self._product("Health Foreign Product", company_id=other.id)
        scan = self._scan()
        scan.action_scan_batch()
        self.assertTrue(scan.issue_ids.filtered(lambda row: row.product_id == own_product))
        self.assertFalse(scan.issue_ids.filtered(lambda row: row.product_id == foreign_product))

        reader = self.env["res.users"].create({
            "name": "Health Reader", "login": "health-reader-test",
            "company_id": self.env.company.id,
            "company_ids": [Command.link(self.env.company.id)],
            "group_ids": [Command.link(self.env.ref("base.group_user").id)],
        })
        with self.assertRaises(AccessError):
            self.env["cyfr.product.health.policy"].with_user(reader).create({"name": "Denied"})
        with self.assertRaises(AccessError):
            scan.with_user(reader).action_scan_batch()
        rows = self.env["cyfr.product.health.issue"].with_user(reader).search_read(
            [("product_id", "=", own_product.id), ("categ_id", "=", self.category.id)],
            ["product_id", "categ_id", "scan_id", "issue_summary"]
        )
        self.assertTrue(rows)
        self.assertEqual(self.env["cyfr.product.health.scan"].with_user(reader).search_read(
            [("id", "=", scan.id)], ["id"]
        ), [])
        with self.assertRaises(AccessError):
            scan.with_user(reader).action_open_issues()

        foreign_reader = self.env["res.users"].create({
            "name": "Other Health Reader", "login": "other-health-reader-test",
            "company_id": other.id,
            "company_ids": [Command.link(other.id)],
            "group_ids": [Command.link(self.env.ref("base.group_user").id)],
        })
        self.assertEqual(self.env["cyfr.product.health.issue"].with_user(foreign_reader).search_read(
            [("id", "in", scan.issue_ids.ids)], ["product_id", "issue_codes"]
        ), [])
        self.assertEqual(self.env["cyfr.product.health.scan"].with_user(foreign_reader).search_read(
            [("id", "=", scan.id)], ["id"]
        ), [])

    def test_zero_price_and_generic_category_are_policy_controlled(self):
        product = self._product("Health Free Product", list_price=0)
        self.policy.write({
            "check_sale_price": False,
            "generic_category_ids": [Command.link(self.category.id)],
        })
        scan = self._scan()
        scan.action_scan_batch()
        row = scan.issue_ids.filtered(lambda issue: issue.product_id == product)
        self.assertNotIn("non_positive_sale_price", row.issue_codes)
        self.assertIn("generic_or_missing_category", row.issue_codes)

    def test_missing_category_is_reported(self):
        product = self._product("Health Uncategorized", categ_id=False)
        scan = self._scan()
        scan.action_scan_batch()
        row = scan.issue_ids.filtered(lambda issue: issue.product_id == product)
        self.assertIn("generic_or_missing_category", row.issue_codes)

    def test_multi_variant_identifiers_and_template_image(self):
        attribute = self.env["product.attribute"].create({"name": "Health Test Color", "create_variant": "always"})
        red = self.env["product.attribute.value"].create({"name": "Red", "attribute_id": attribute.id})
        blue = self.env["product.attribute.value"].create({"name": "Blue", "attribute_id": attribute.id})
        template = self.env["product.template"].create({
            "name": "Health Color Variant", "categ_id": self.category.id,
            "list_price": 15, "image_1920": self._one_pixel_image(),
            "attribute_line_ids": [Command.create({
                "attribute_id": attribute.id, "value_ids": [Command.set([red.id, blue.id])],
            })],
        })
        self.assertEqual(len(template.product_variant_ids), 2)
        variants = template.product_variant_ids.sorted("id")
        variants[0].write({"barcode": "9999999999991", "default_code": "HEALTH-RED"})
        variants[1].write({"default_code": "HEALTH-BLUE"})
        scan = self._scan()
        scan.action_scan_batch()
        rows = scan.issue_ids.filtered(lambda row: row.product_id in variants)
        self.assertEqual(len(rows), 1, "The complete first variant should not produce an issue")
        self.assertFalse(rows.filtered(lambda row: row.product_id == variants[0]))
        self.assertIn("missing_barcode", rows.filtered(lambda row: row.product_id == variants[1]).issue_codes)
        self.assertTrue(all("missing_image" not in row.issue_codes for row in rows))

    def test_menu_permissions(self):
        root = self.env.ref("cyfr_product_data_health.menu_product_health_root")
        issues = self.env.ref("cyfr_product_data_health.menu_product_health_issues")
        scans = self.env.ref("cyfr_product_data_health.menu_product_health_scans")
        policies = self.env.ref("cyfr_product_data_health.menu_product_health_policies")
        self.assertIn(self.env.ref("base.group_user"), root.group_ids)
        self.assertEqual(issues.parent_id, root)
        self.assertIn(self.env.ref("product.group_product_manager"), scans.group_ids)
        self.assertIn(self.env.ref("product.group_product_manager"), policies.group_ids)

    def test_direct_rpc_cannot_fabricate_scan_or_issue(self):
        manager = self.env["res.users"].create({
            "name": "Health Manager", "login": "health-manager-test",
            "company_id": self.env.company.id,
            "company_ids": [Command.link(self.env.company.id)],
            "group_ids": [
                Command.link(self.env.ref("base.group_user").id),
                Command.link(self.env.ref("product.group_product_manager").id),
            ],
        })
        scan_model = self.env["cyfr.product.health.scan"].with_user(manager)
        with self.assertRaises(AccessError):
            scan_model.create({"company_id": self.env.company.id, "state": "done"})
        scan = scan_model.create({"company_id": self.env.company.id})
        with self.assertRaises(AccessError):
            scan.write({"state": "done"})
        with self.assertRaises(AccessError):
            scan.write({"company_id": self.env.company.id})
        with self.assertRaises(AccessError):
            scan.unlink()
        product = self._product("Health No Fabrication")
        with self.assertRaises(AccessError):
            self.env["cyfr.product.health.issue"].with_user(manager).create({
                "scan_id": scan.id, "company_id": self.env.company.id,
                "product_id": product.id, "policy_id": self.policy.id,
                "issue_codes": "missing_barcode",
            })
        scan.action_scan_batch()
        issue = scan.issue_ids.filtered(lambda row: row.product_id == product)
        with self.assertRaises(AccessError):
            issue.with_user(manager).write({"issue_codes": "missing_image"})
        with self.assertRaises(AccessError):
            issue.with_user(manager).unlink()

    def test_retention_action_only_deletes_old_completed_scan(self):
        first = self._scan()
        first.action_scan_batch()
        with self.assertRaises(ValidationError):
            first.action_delete_old_scan()
        second = self._scan()
        second.action_scan_batch()
        first_id = first.id
        first.action_delete_old_scan()
        self.assertFalse(self.env["cyfr.product.health.scan"].browse(first_id).exists())

    def test_company_publication_lock_and_single_current_snapshot(self):
        first = self._scan()
        second = self._scan()
        company_class = type(first.company_id)
        with patch.object(company_class, "lock_for_update", autospec=True) as company_lock:
            first.action_scan_batch()
            second.action_scan_batch()
        self.assertEqual(company_lock.call_count, 2)
        self.assertEqual(first.company_id, company_lock.call_args.args[0])
        self.assertFalse(first.is_current)
        self.assertTrue(second.is_current)
        self.assertEqual(self.env["cyfr.product.health.scan"].search_count([
            ("company_id", "=", self.env.company.id), ("is_current", "=", True),
        ]), 1)

    def test_demo_generic_category_is_flagged_when_demo_loaded(self):
        demo = self.env.ref("cyfr_product_data_health.demo_product_generic_category", raise_if_not_found=False)
        if not demo:
            self.skipTest("Demo data is not loaded")
        scan = self._scan()
        scan.action_scan_batch()
        issue = scan.issue_ids.filtered(lambda row: row.product_id in demo.product_variant_ids)
        self.assertTrue(issue)
        self.assertIn("generic_or_missing_category", issue.issue_codes)

    def test_custom_product_rule_after_scan_blocks_all_issue_reads(self):
        hidden = self._product("Health Rule Hidden")
        visible = self._product("Health Rule Visible")
        scan = self._scan()
        scan.action_scan_batch()
        hidden_issue = scan.issue_ids.filtered(lambda row: row.product_id == hidden)
        visible_issue = scan.issue_ids.filtered(lambda row: row.product_id == visible)
        restricted_group = self.env["res.groups"].create({"name": "Health Test Restricted Products"})
        reader = self.env["res.users"].create({
            "name": "Health Rule Reader", "login": "health-rule-reader-test",
            "company_id": self.env.company.id,
            "company_ids": [Command.link(self.env.company.id)],
            "group_ids": [
                Command.link(self.env.ref("base.group_user").id),
                Command.link(self.env.ref("base.group_allow_export").id),
                Command.link(restricted_group.id),
            ],
        })
        issue_model = self.env["cyfr.product.health.issue"].with_user(reader)
        cached_hidden = hidden_issue.with_user(reader)
        self.assertTrue(cached_hidden.read(["product_id", "issue_codes"]))
        self.env["ir.rule"].create({
            "name": "Hide one health test product",
            "model_id": self.env.ref("product.model_product_product").id,
            "groups": [Command.link(restricted_group.id)],
            "domain_force": "[('id', '!=', %d)]" % hidden.id,
            "perm_read": True, "perm_write": False,
            "perm_create": False, "perm_unlink": False,
        })
        visible_rows = issue_model.search_read(
            [("id", "in", [hidden_issue.id, visible_issue.id])], ["product_id", "issue_codes"]
        )
        self.assertEqual([row["id"] for row in visible_rows], [visible_issue.id])
        self.assertEqual(issue_model.search_count([("id", "=", hidden_issue.id)]), 0)
        self.assertNotIn(hidden_issue.id, [row_id for row_id, _name in issue_model.name_search(hidden.name)])
        self.assertIn(visible_issue.id, [row_id for row_id, _name in issue_model.name_search(visible.name)])
        visible_export = visible_issue.with_user(reader).export_data(["product_id", "issue_codes"])
        self.assertTrue(visible_export["datas"])
        self.assertIn("missing_barcode", str(visible_export["datas"]))
        with self.assertRaises(AccessError):
            cached_hidden.read(["product_id", "issue_codes"])
        with self.assertRaises(AccessError):
            cached_hidden.read(["display_name"])
        with self.assertRaises(AccessError):
            cached_hidden.export_data(["product_id", "issue_codes"])
        with self.assertRaises(AccessError):
            cached_hidden.action_open_product()

    def test_duplicate_issue_is_rejected(self):
        product = self._product("Health Unique Issue")
        scan = self._scan()
        scan.action_scan_batch()
        issue = scan.issue_ids.filtered(lambda row: row.product_id == product)
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["cyfr.product.health.issue"].sudo().create({
                "scan_id": scan.id, "company_id": self.env.company.id,
                "product_id": product.id, "policy_id": self.policy.id,
                "issue_codes": issue.issue_codes,
            })
        self.assertEqual(len(scan.issue_ids.filtered(lambda row: row.product_id == product)), 1)
