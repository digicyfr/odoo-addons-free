import base64
import csv
import io
from uuid import uuid4
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models import pos_tax_audit


@tagged("post_install", "-at_install")
class TestPosTaxAudit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env.ref("cyfr_pos_tax_audit.demo_config")
        cls.tax_23 = cls.env.ref("cyfr_pos_tax_audit.demo_tax_23")
        cls.tax_8 = cls.env.ref("cyfr_pos_tax_audit.demo_tax_8")
        cls.category = cls.env.ref("cyfr_pos_tax_audit.demo_pos_category")
        cls.taxed = cls.env.ref("cyfr_pos_tax_audit.demo_product_taxed").product_variant_id
        cls.zero = cls.env.ref("cyfr_pos_tax_audit.demo_product_zero").product_variant_id
        cls.manager = cls.env["res.users"].create({
            "name": "POS Tax Audit Manager", "login": "pos-tax-audit-manager-test",
            "company_id": cls.env.company.id,
            "company_ids": [Command.link(cls.env.company.id)],
            "group_ids": [Command.link(cls.env.ref("point_of_sale.group_pos_manager").id)],
        })

    def _audit(self, **values):
        return self.env["cyfr.pos.tax.audit"].with_user(self.manager).create({
            "config_id": self.config.id, "page_size": 100, **values,
        })

    def test_base_default_allowed_and_checkout_calculation(self):
        audit = self._audit()
        audit.action_run()
        rows = audit.line_ids.filtered(lambda row: row.product_id == self.taxed)
        self.assertEqual(len(rows), 3)
        base = rows.filtered(lambda row: not row.position_id)
        default = rows.filtered(lambda row: row.position_id == self.config.default_fiscal_position_id)
        allowed = rows.filtered(lambda row: row.position_id == self.env.ref("cyfr_pos_tax_audit.demo_position_allowed"))
        self.assertEqual(base.source_tax_ids, self.tax_23)
        self.assertEqual(base.result_tax_ids, self.tax_23)
        self.assertEqual(default.result_tax_ids, self.tax_8)
        self.assertEqual(allowed.result_tax_ids, self.tax_23)
        self.assertEqual(default.mapping, "mapped")
        # Persist a real POS session/order/line. The order takes its default
        # fiscal position from the selected config; its own line method and
        # tax totals are the pinned backend checkout calculation.
        session = self.env["pos.session"].create({"config_id": self.config.id})
        order = self.env["pos.order"].create({
            "company_id": self.env.company.id,
            "session_id": session.id,
            "lines": [Command.create({
                "name": "Tax audit checkout comparison",
                "product_id": self.taxed.id,
                "tax_ids": [Command.set([self.tax_23.id])],
                "price_unit": 100,
                "qty": 1,
                "price_subtotal": 100,
                "price_subtotal_incl": 100,
            })],
            "amount_total": 100,
            "amount_tax": 0,
            "amount_paid": 0,
            "amount_return": 0,
        })
        line = order.lines
        self.assertTrue(order.id and line.id)
        self.assertEqual(order.fiscal_position_id, self.config.default_fiscal_position_id)
        self.assertEqual(line.tax_ids_after_fiscal_position, default.result_tax_ids)
        actual = line._compute_amount_line_all()
        expected = default.result_tax_ids.compute_all(100, self.env.company.currency_id, 1, product=self.taxed)
        self.assertAlmostEqual(actual["price_subtotal_incl"], expected["total_included"])
        self.assertAlmostEqual(actual["price_subtotal"], expected["total_excluded"])
        order._compute_prices()
        self.assertAlmostEqual(order.amount_total, expected["total_included"])

    def test_no_and_multiple_taxes_are_descriptive(self):
        multi_template = self.env["product.template"].create({
            "name": "Tax Audit Multiple", "sale_ok": True, "available_in_pos": True,
            "pos_categ_ids": [Command.link(self.category.id)],
            "taxes_id": [Command.set([self.tax_23.id, self.tax_8.id])],
        })
        audit = self._audit()
        audit.action_run()
        zero = audit.line_ids.filtered(lambda row: row.product_id == self.zero and not row.position_id)
        multi = audit.line_ids.filtered(lambda row: row.product_id == multi_template.product_variant_id and not row.position_id)
        self.assertTrue(zero.no_tax)
        self.assertFalse(zero.empty_result)
        self.assertTrue(multi.multiple_taxes)
        self.assertFalse(multi.empty_result)
        self.assertEqual(multi.action_open_source_taxes()["domain"], [("id", "in", multi.source_tax_ids.ids)])
        self.assertEqual(multi.action_open_source_taxes()["view_mode"], "list,form")
        with self.assertRaises(UserError):
            zero.action_open_source_taxes()

    def test_domain_category_company_and_inactive(self):
        other_company = self.env["res.company"].create({
            "name": "Tax Audit Other Company Test",
            "country_id": (self.env.company.country_id or self.env.ref("base.pl")).id,
        })
        other_product = self.env["product.template"].with_company(other_company).create({
            "name": "Tax Audit Other Company Product Test",
            "company_id": other_company.id,
            "available_in_pos": True,
            "sale_ok": True,
            "pos_categ_ids": [Command.link(self.category.id)],
            "taxes_id": [Command.clear()],
        }).product_variant_id
        self.config.with_user(self.manager).check_access("read")
        audit = self._audit()
        audit.action_run()
        ids = audit.line_ids.mapped("product_id").ids
        self.assertIn(self.taxed.id, ids)
        self.assertNotIn(self.env.ref("cyfr_pos_tax_audit.demo_product_excluded_category").product_variant_id.id, ids)
        self.assertNotIn(other_product.id, ids)
        self.taxed.product_tmpl_id.active = False
        audit.action_run()
        self.assertNotIn(self.taxed.id, audit.line_ids.mapped("product_id").ids)
        audit.with_context(active_test=False).action_run()
        self.assertNotIn(self.taxed.id, audit.line_ids.mapped("product_id").ids)

    def test_page_limit_and_continuation(self):
        audit = self._audit(page_size=1)
        audit.action_run()
        first = audit.line_ids.mapped("product_id")
        self.assertEqual(audit.scanned_count, 1)
        self.assertEqual(audit.line_count, audit.scenario_count)
        self.assertGreater(audit.skipped_count, 0)
        audit.action_next_page()
        self.assertEqual(audit.offset, 1)
        self.assertEqual(audit.scanned_count, 1)
        self.assertFalse(first & audit.line_ids.mapped("product_id"))
        with self.assertRaises(ValidationError):
            self._audit(page_size=101).action_run()
        with self.assertRaises(ValidationError):
            self._audit(offset=-1).action_run()

    def test_bounded_scenarios_and_matrix(self):
        audit = self._audit(page_size=2)
        with patch.object(pos_tax_audit, "MAX_SCENARIOS", 2), self.assertRaises(UserError):
            audit.action_run()
        with patch.object(pos_tax_audit, "MAX_LINES_PER_PAGE", 5), self.assertRaises(UserError):
            audit.action_run()
        with patch.object(pos_tax_audit, "MAX_TAX_CANDIDATES", 0), self.assertRaises(UserError):
            audit.action_run()
        self.assertFalse(audit.line_ids)

    def test_tax_lookup_uses_only_page_candidates(self):
        unrelated = self.env["account.tax"].create({
            "name": "Unrelated audit tax", "amount": 11,
            "type_tax_use": "sale", "company_id": self.env.company.id,
        })
        archived = self.env["account.tax"].create({
            "name": "Archived audit tax", "amount": 9,
            "type_tax_use": "sale", "company_id": self.env.company.id,
        })
        archived.active = False
        self.taxed.product_tmpl_id.taxes_id = [Command.link(archived.id)]
        TaxModel = type(self.env["account.tax"])
        original_search = TaxModel.search
        searched_domains = []

        def traced_search(records, domain, *args, **kwargs):
            searched_domains.append(domain)
            return original_search(records, domain, *args, **kwargs)

        audit = self._audit()
        with patch.object(TaxModel, "search", traced_search):
            audit.with_context(active_test=False).action_run()
        self.assertTrue(searched_domains)
        for domain in searched_domains:
            candidate_ids = [term[2] for term in domain if isinstance(term, tuple) and term[:2] == ("id", "in")]
            self.assertTrue(candidate_ids, "tax searches must be limited to page candidate IDs")
            self.assertNotIn(unrelated.id, candidate_ids[0])
            self.assertNotIn(archived.id, candidate_ids[0])
        row = audit.line_ids.filtered(lambda line: line.product_id == self.taxed and not line.position_id)
        self.assertEqual(row.source_tax_ids, self.tax_23)

    def test_cashier_owner_and_company_denied(self):
        cashier = self.env["res.users"].create({
            "name": "POS Tax Audit Cashier", "login": "pos-tax-audit-cashier-test",
            "company_id": self.env.company.id,
            "company_ids": [Command.link(self.env.company.id)],
            "group_ids": [Command.link(self.env.ref("point_of_sale.group_pos_user").id)],
        })
        with self.assertRaises(AccessError):
            self.env["cyfr.pos.tax.audit"].with_user(cashier).create({"config_id": self.config.id})
        audit = self._audit()
        audit.action_run()
        taxed_row = audit.line_ids.filtered(lambda row: row.product_id == self.taxed and not row.position_id)
        self.assertEqual(taxed_row.action_open_source_taxes()["res_id"], self.tax_23.id)
        with self.assertRaises(AccessError):
            audit.with_user(cashier).action_run()
        with self.assertRaises(AccessError):
            audit.with_user(cashier).action_export_csv()
        with self.assertRaises(AccessError):
            taxed_row.with_user(cashier).action_open_source_taxes()
        with self.assertRaises(AccessError):
            audit.line_ids.with_user(self.manager).write({"no_tax": False})
        with self.assertRaises(AccessError):
            audit.with_user(self.manager).write({"total_count": 1})
        other = self.env["res.company"].create({"name": "Tax Audit Test Other Company"})
        other_manager = self.env["res.users"].create({
            "name": "POS Tax Audit Other Manager", "login": "pos-tax-audit-other-manager-test",
            "company_id": other.id, "company_ids": [Command.link(other.id)],
            "group_ids": [Command.link(self.env.ref("point_of_sale.group_pos_manager").id)],
        })
        self.assertFalse(self.env["cyfr.pos.tax.audit.line"].with_user(other_manager).search([("audit_id", "=", audit.id)]))
        with self.assertRaises(AccessError):
            audit.with_user(other_manager).action_export_csv()
        with self.assertRaises(AccessError):
            taxed_row.with_user(other_manager).action_open_source_taxes()

    def test_export_current_page_and_formula_escape(self):
        formula = self.env["product.template"].create({
            "name": "=SUM(1,2)", "available_in_pos": True, "sale_ok": True,
            "pos_categ_ids": [Command.link(self.category.id)],
            "taxes_id": [Command.set([self.tax_23.id])],
        })
        audit = self._audit()
        audit.action_run()
        action = audit.action_export_csv()
        self.assertEqual(action["target"], "download")
        raw = base64.b64decode(audit.csv_data).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(raw)))
        self.assertEqual(len(rows), audit.line_count)
        formula_rows = [row for row in rows if row["product_id"] == str(formula.product_variant_id.id)]
        self.assertEqual(len(formula_rows), audit.scenario_count)
        self.assertTrue(all(row["product"].startswith("'=") for row in formula_rows))
        with self.assertRaises(AccessError):
            self.env["cyfr.pos.tax.audit"].with_user(self.manager).create({
                "config_id": self.config.id, "user_id": self.env.user.id,
            })

    def test_empty_mapping_and_repeat_replaces_rows(self):
        position = self.env["account.fiscal.position"].create({
            "name": "Tax Audit Exempt", "company_id": self.env.company.id,
        })
        source_marker_position = self.env["account.fiscal.position"].create({
            "name": "Tax Audit Source Marker", "company_id": self.env.company.id,
        })
        self.tax_23.fiscal_position_ids = [Command.link(source_marker_position.id)]
        self.config.fiscal_position_ids = [Command.link(position.id)]
        audit = self._audit()
        audit.action_run()
        row = audit.line_ids.filtered(lambda r: r.product_id == self.taxed and r.position_id == position)
        self.assertTrue(row.empty_result)
        first_ids = set(audit.line_ids.ids)
        audit.action_run()
        self.assertFalse(first_ids.intersection(audit.line_ids.ids))
        self.assertEqual(len(audit.line_ids), audit.line_count)

    def test_changing_inputs_invalidates_report_and_csv(self):
        audit = self._audit()
        audit.action_run()
        audit.action_export_csv()
        self.assertTrue(audit.csv_data)
        old_rows = audit.line_ids.ids
        audit.write({"page_size": 1})
        self.assertFalse(audit.scanned_at)
        self.assertFalse(audit.csv_data)
        self.assertFalse(audit.line_ids)
        self.assertFalse(self.env["cyfr.pos.tax.audit.line"].sudo().browse(old_rows).exists())
        with self.assertRaises(UserError):
            audit.action_export_csv()
        audit.action_run()
        audit.write({"offset": 1})
        self.assertFalse(audit.scanned_at)
        other_config = self.env["pos.config"].create({"name": "Audit Other Config"})
        audit.action_run()
        audit.write({"config_id": other_config.id})
        self.assertFalse(audit.scanned_at)
        self.assertFalse(audit.line_ids)

    def test_archived_default_still_included(self):
        position = self.config.default_fiscal_position_id
        position.active = False
        audit = self._audit()
        audit.action_run()
        rows = audit.line_ids.filtered(lambda row: row.product_id == self.taxed and row.position_id == position)
        self.assertEqual(len(rows), 1)
        self.assertIn("inactive", rows.scenario_name)
        self.assertEqual(rows.result_tax_ids, self.tax_8)

    def test_child_company_taxes_match_pos_template_loader(self):
        child = self.env["res.company"].create({
            "name": "Tax Audit Child", "parent_id": self.env.company.id,
            "country_id": (self.env.company.country_id or self.env.ref("base.pl")).id,
        })
        tax_group = self.env["account.tax.group"].with_company(child).create({
            "name": "Tax Audit Child Taxes", "company_id": child.id,
        })
        child_tax = self.env["account.tax"].with_company(child).create({
            "name": "Child tax 7%", "amount": 7,
            "type_tax_use": "sale", "company_id": child.id,
            "tax_group_id": tax_group.id,
        })
        child_config = self.env["pos.config"].with_company(child).create({
            "name": "Tax Audit Child POS", "company_id": child.id,
            "payment_method_ids": [Command.clear()],
            "limit_categories": True,
            "iface_available_categ_ids": [Command.link(self.category.id)],
            "default_fiscal_position_id": self.config.default_fiscal_position_id.id,
        })
        product = self.env["product.template"].with_company(child).create({
            "name": "Child plus parent tax", "company_id": child.id,
            "available_in_pos": True, "sale_ok": True,
            "pos_categ_ids": [Command.link(self.category.id)],
            "taxes_id": [Command.set([self.tax_23.id, child_tax.id])],
        })
        self.manager.company_ids = [Command.link(child.id)]
        audit = self.env["cyfr.pos.tax.audit"].with_user(self.manager).with_company(child).create({
            "config_id": child_config.id,
        })
        audit.action_run()
        row = audit.line_ids.filtered(lambda item: item.product_id == product.product_variant_id and not item.position_id)
        self.assertEqual(len(row), 1)
        self.assertEqual(row.source_tax_ids, child_tax)
        self.assertTrue(row.foreign_company_tax)
        self.assertTrue(audit.line_ids.filtered(
            lambda item: item.product_id == product.product_variant_id
            and item.position_id == self.config.default_fiscal_position_id
        ), "A parent-company default fiscal position is valid for a child POS")
        # Compare the actual POS template payload, which narrows to the
        # nearest company's tax IDs before the frontend receives it.
        payload = self.env["product.template"].with_company(child)._load_pos_data_read(product.with_company(child), child_config)
        self.assertEqual(set(payload[0]["taxes_id"]), set(row.source_tax_ids.ids))

    def test_pos_order_sync_uses_audited_default_tax(self):
        audit = self._audit()
        audit.action_run()
        row = audit.line_ids.filtered(
            lambda item: item.product_id == self.taxed
            and item.position_id == self.config.default_fiscal_position_id
        )
        self.assertEqual(row.result_tax_ids, self.tax_8)
        journal = self.env["account.journal"].search([
            ("company_id", "=", self.env.company.id), ("type", "=", "sale")
        ], limit=1)
        if not journal:
            journal = self.env["account.journal"].create({
                "name": "Tax Audit Sync Sales", "code": "TAXS", "type": "sale",
                "company_id": self.env.company.id,
            })
        self.config.invoice_journal_id = journal
        session = self.env["pos.session"].create({
            "config_id": self.config.id, "state": "opened",
        })
        expected = row.result_tax_ids.compute_all(
            100, self.env.company.currency_id, 1, product=self.taxed
        )
        order_uuid = str(uuid4())
        # This is the same order sync API used by Odoo's POS browser. The UI
        # sends the source product tax IDs; the fiscal-position mapping is
        # applied during calculation, including after the order is persisted.
        payload = {
            "uuid": order_uuid,
            "name": "Tax Audit Sync %s" % order_uuid,
            "session_id": session.id,
            "company_id": self.env.company.id,
            "fiscal_position_id": self.config.default_fiscal_position_id.id,
            "pricelist_id": self.config.pricelist_id.id,
            "last_order_preparation_change": "{}",
            "date_order": fields.Datetime.now(),
            "state": "draft",
            "lines": [Command.create({
                "product_id": self.taxed.id,
                "price_unit": 100,
                "qty": 1,
                "tax_ids": [Command.set(row.source_tax_ids.ids)],
                "price_subtotal": expected["total_excluded"],
                "price_subtotal_incl": expected["total_included"],
            })],
            "payment_ids": [],
            "amount_paid": 0,
            "amount_return": 0,
            "amount_tax": expected["total_included"] - expected["total_excluded"],
            "amount_total": expected["total_included"],
            "user_id": self.env.uid,
        }
        self.env["pos.order"].sync_from_ui([payload])
        order = self.env["pos.order"].search([("uuid", "=", order_uuid)])
        self.assertEqual(len(order), 1)
        self.assertEqual(order.session_id, session)
        self.assertEqual(order.lines.tax_ids, row.source_tax_ids)
        self.assertEqual(order.lines.tax_ids_after_fiscal_position, row.result_tax_ids)
        order._compute_prices()
        self.assertAlmostEqual(order.amount_total, expected["total_included"])
