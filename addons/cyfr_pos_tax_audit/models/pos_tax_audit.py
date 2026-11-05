"""Bounded, read-only snapshots of the normal POS product catalog's taxes."""

import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


MAX_PRODUCTS_PER_PAGE = 100
MAX_SCENARIOS = 20
MAX_LINES_PER_PAGE = 1000
MAX_TAX_CANDIDATES = 2000


def _safe_csv(value):
    """Keep values from catalog data inert in spreadsheet applications."""
    value = str(value or "")
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


class PosTaxAudit(models.TransientModel):
    _name = "cyfr.pos.tax.audit"
    _description = "POS Tax Setup Audit"

    config_id = fields.Many2one("pos.config", string="Point of Sale", required=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", related="config_id.company_id", store=True, readonly=True)
    user_id = fields.Many2one("res.users", string="Scan Owner", required=True, readonly=True, default=lambda self: self.env.user)
    offset = fields.Integer(string="Variant Offset", default=0, required=True)
    page_size = fields.Integer(string="Variants per Page", default=50, required=True)
    scanned_at = fields.Datetime(string="Scanned At", readonly=True)
    total_count = fields.Integer(string="Eligible Variants", readonly=True)
    scanned_count = fields.Integer(string="Scanned Variants", readonly=True)
    skipped_count = fields.Integer(string="Remaining Variants", readonly=True)
    scenario_count = fields.Integer(string="Scenarios", readonly=True)
    line_count = fields.Integer(string="Matrix Rows", readonly=True)
    note = fields.Text(string="Scope", readonly=True)
    line_ids = fields.One2many("cyfr.pos.tax.audit.line", "audit_id", string="Tax Matrix", readonly=True)
    csv_data = fields.Binary(string="CSV", attachment=False, readonly=True)
    csv_filename = fields.Char(string="CSV Filename", readonly=True)

    @api.depends("config_id", "scanned_at")
    def _compute_display_name(self):
        for audit in self:
            audit.display_name = "%s — %s" % (
                audit.config_id.display_name or _("New POS tax audit"),
                fields.Datetime.to_string(audit.scanned_at) if audit.scanned_at else _("Not scanned"),
            )

    @api.model_create_multi
    def create(self, vals_list):
        self._require_manager()
        for vals in vals_list:
            if set(vals) - {"config_id", "offset", "page_size"}:
                raise AccessError(_("Only audit inputs may be set when creating a scan."))
            config = self.env["pos.config"].browse(vals.get("config_id"))
            config.check_access("read")
            if config.company_id not in self.env.companies:
                raise AccessError(_("The Point of Sale company is not allowed for this user."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            self._require_manager()
            if set(vals) - {"config_id", "offset", "page_size"}:
                raise AccessError(_("Scan results cannot be changed directly."))
            for audit in self:
                audit._check_scope()
            if "config_id" in vals:
                config = self.env["pos.config"].browse(vals["config_id"])
                config.check_access("read")
                if config.company_id not in self.env.companies:
                    raise AccessError(_("The Point of Sale company is not allowed for this user."))
        changed = not self.env.su and bool({"config_id", "offset", "page_size"}.intersection(vals))
        result = super().write(vals)
        if changed:
            # A changed input cannot keep rows or a CSV labelled with the old
            # configuration. Invalidate the snapshot even before the next run.
            self.mapped("line_ids").sudo().unlink()
            self.sudo().write({
                "scanned_at": False, "total_count": 0, "scanned_count": 0,
                "skipped_count": 0, "scenario_count": 0, "line_count": 0,
                "note": False, "csv_data": False, "csv_filename": False,
            })
        return result

    @api.model
    def _require_manager(self):
        if not self.env.user.has_group("point_of_sale.group_pos_manager"):
            raise AccessError(_("Only Point of Sale managers can use the tax audit."))

    def _check_scope(self):
        self.ensure_one()
        self._require_manager()
        if self.user_id != self.env.user:
            raise AccessError(_("This scan belongs to another user."))
        if self.config_id.company_id not in self.env.companies:
            raise AccessError(_("The Point of Sale company is not allowed for this user."))
        self.config_id.check_access("read")
        if self.offset < 0 or self.page_size < 1 or self.page_size > MAX_PRODUCTS_PER_PAGE:
            raise ValidationError(_("Choose a variant offset of zero or more and a page size from 1 to 100."))

    def _scenarios(self):
        self.ensure_one()
        config = self.config_id
        # An archived default still applies to new backend orders; do not omit
        # it merely because the manager archived the fiscal position later.
        positions = config.default_fiscal_position_id | config.fiscal_position_ids.filtered("active")
        positions = positions.filtered_domain(
            self.env["account.fiscal.position"]._check_company_domain(config.company_id)
        )
        if len(positions) + 1 > MAX_SCENARIOS:
            raise UserError(_("This Point of Sale has more than 19 active fiscal positions. Reduce its configured positions before auditing."))
        return [(False, _("Base taxes"))] + [
            (position, position.display_name + (_(" (inactive default)") if not position.active else ""))
            for position in positions.sorted("id")
        ]

    def _variant_domain(self):
        self.ensure_one()
        template_domain = self.env["product.template"]._load_pos_data_domain({}, self.config_id)
        return [("product_tmpl_id", "any", template_domain)]

    def _pos_source_taxes(self, product, config, loaded_taxes):
        """Match the pinned frontend's closest-company tax selection."""
        raw = product.taxes_id
        source = raw & loaded_taxes
        # The POS template loader applies this narrowing only when its loaded
        # tax set spans companies and the product has multiple tax IDs.
        if config.company_id.parent_id and len(loaded_taxes.mapped("company_id")) > 1 and len(raw) > 1:
            company = config.company_id
            while company:
                nearest = source.filtered(lambda tax: tax.company_id == company)
                if nearest:
                    return nearest, bool(raw - nearest)
                company = company.parent_id
        return source, bool(raw - source)

    def action_run(self):
        self.ensure_one()
        self._check_scope()
        self.lock_for_update(allow_referencing=True)
        config = self.config_id
        scenarios = self._scenarios()
        if self.page_size * len(scenarios) > MAX_LINES_PER_PAGE:
            raise UserError(_("Reduce variants per page so the tax matrix has at most 1,000 rows."))
        Product = self.env["product.product"].with_company(config.company_id).with_context(active_test=True)
        domain = self._variant_domain()
        total = Product.search_count(domain)
        products = Product.search(domain, offset=self.offset, limit=self.page_size, order="id")
        Tax = self.env["account.tax"].with_company(config.company_id).with_context(active_test=True)
        company_tax_domain = Tax._check_company_domain(config.company_id)
        raw_taxes = products.mapped("taxes_id")
        if len(raw_taxes) > MAX_TAX_CANDIDATES:
            raise UserError(_("This page references too many distinct taxes. Reduce variants per page."))
        eligible_sources = Tax.search([("id", "in", raw_taxes.ids), *company_tax_domain])
        selected_sources = Tax.browse()
        for product in products:
            selected_sources |= self._pos_source_taxes(product, config, eligible_sources)[0]
        candidate_taxes = selected_sources
        for position, _label in scenarios:
            if position:
                candidate_taxes |= position.map_tax(selected_sources)
        if len(candidate_taxes) > MAX_TAX_CANDIDATES:
            raise UserError(_("This page maps to too many distinct taxes. Reduce variants per page or configured fiscal positions."))
        loaded_taxes = Tax.search([("id", "in", candidate_taxes.ids), *company_tax_domain])
        values = []
        for product in products:
            source_taxes, source_foreign = self._pos_source_taxes(product, config, loaded_taxes)
            for position, label in scenarios:
                mapped_taxes = position.map_tax(source_taxes) if position else source_taxes
                result_taxes = mapped_taxes & loaded_taxes
                foreign = source_foreign or bool(mapped_taxes - result_taxes)
                if not position:
                    mapping = "base"
                elif not result_taxes and source_taxes:
                    mapping = "empty"
                elif result_taxes == source_taxes:
                    mapping = "passthrough"
                else:
                    mapping = "mapped"
                values.append({
                    "audit_id": self.id,
                    "company_id": config.company_id.id,
                    "product_id": product.id,
                    "position_id": position.id if position else False,
                    "scenario_name": label,
                    "source_tax_ids": [(6, 0, source_taxes.ids)],
                    "result_tax_ids": [(6, 0, result_taxes.ids)],
                    "no_tax": not bool(source_taxes),
                    "multiple_taxes": len(source_taxes) > 1,
                    "foreign_company_tax": foreign,
                    "empty_result": bool(source_taxes) and not bool(result_taxes),
                    "mapping": mapping,
                })
        # The source products were searched with the invoking user's rights. Only
        # result storage uses superuser privileges; managers cannot forge lines.
        self.line_ids.sudo().unlink()
        if values:
            self.env["cyfr.pos.tax.audit.line"].sudo().create(values)
        self.sudo().write({
            "scanned_at": fields.Datetime.now(),
            "total_count": total,
            "scanned_count": len(products),
            "skipped_count": max(total - self.offset - len(products), 0),
            "scenario_count": len(scenarios),
            "line_count": len(values),
            "note": _("Normal eligible POS catalog variants, in ID order. Contextual special, tip, combo, optional, and previously ordered products are excluded. POS limited loading may show a different first subset. Other-company taxes excluded by POS are flagged without naming them. Flags are advisory; ask your accountant or localization owner about legally correct tax rates."),
            "csv_data": False,
            "csv_filename": False,
        })
        return self._reopen()

    def action_next_page(self):
        self.ensure_one()
        self._check_scope()
        if not self.scanned_at or self.offset + self.scanned_count >= self.total_count:
            raise UserError(_("There are no more eligible variants to scan."))
        self.write({"offset": self.offset + self.scanned_count})
        return self.action_run()

    def action_export_csv(self):
        self.ensure_one()
        self._check_scope()
        if not self.scanned_at:
            raise UserError(_("Run the audit before exporting."))
        rows = self.env["cyfr.pos.tax.audit.line"].search([("audit_id", "=", self.id)], order="product_id,position_id,id")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["product_id", "product", "company", "scenario", "fiscal_position_id", "source_tax_ids", "source_taxes", "result_tax_ids", "result_taxes", "no_tax", "multiple_taxes", "foreign_company_tax", "empty_result", "mapping", "scanned_at"])
        for row in rows:
            writer.writerow([
                row.product_id.id, _safe_csv(row.product_id.display_name), _safe_csv(row.company_id.display_name),
                _safe_csv(row.scenario_name), row.position_id.id or "",
                ";".join(map(str, row.source_tax_ids.ids)), _safe_csv("; ".join(row.source_tax_ids.mapped("display_name"))),
                ";".join(map(str, row.result_tax_ids.ids)), _safe_csv("; ".join(row.result_tax_ids.mapped("display_name"))),
                int(row.no_tax), int(row.multiple_taxes), int(row.foreign_company_tax), int(row.empty_result), row.mapping, row.audit_id.scanned_at,
            ])
        self.sudo().write({
            "csv_data": base64.b64encode(output.getvalue().encode("utf-8-sig")),
            "csv_filename": "pos-tax-audit-%s-%s.csv" % (self.config_id.id, self.id),
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content?model=cyfr.pos.tax.audit&id=%s&field=csv_data&filename_field=csv_filename&download=true" % self.id,
            "target": "download",
        }

    def _reopen(self):
        return {"type": "ir.actions.act_window", "name": _("POS Tax Setup Audit"), "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "current"}


class PosTaxAuditLine(models.TransientModel):
    _name = "cyfr.pos.tax.audit.line"
    _description = "POS Tax Audit Matrix Row"
    _order = "product_id, position_id, id"

    audit_id = fields.Many2one("cyfr.pos.tax.audit", required=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade", readonly=True)
    position_id = fields.Many2one("account.fiscal.position", string="Fiscal Position", readonly=True)
    scenario_name = fields.Char(string="Scenario", required=True, readonly=True)
    source_tax_ids = fields.Many2many("account.tax", "cyfr_pos_tax_audit_source_rel", "line_id", "tax_id", string="Source Taxes", readonly=True)
    result_tax_ids = fields.Many2many("account.tax", "cyfr_pos_tax_audit_result_rel", "line_id", "tax_id", string="Result Taxes", readonly=True)
    no_tax = fields.Boolean(string="No Company Tax", readonly=True)
    multiple_taxes = fields.Boolean(string="Multiple Taxes (Review)", readonly=True)
    foreign_company_tax = fields.Boolean(string="Other Company Tax Excluded", readonly=True)
    empty_result = fields.Boolean(string="Empty Mapped Result (Review)", readonly=True)
    mapping = fields.Selection([
        ("base", "Base"), ("mapped", "Changed"), ("passthrough", "Pass-through"), ("empty", "Empty Result")
    ], string="Mapping", readonly=True)

    @api.depends("product_id", "scenario_name")
    def _compute_display_name(self):
        for line in self:
            line.display_name = "%s — %s" % (line.product_id.display_name, line.scenario_name)

    def _open_taxes(self, field_name):
        self.ensure_one()
        self.check_access("read")
        self.audit_id._check_scope()
        taxes = self[field_name]
        if not taxes:
            raise UserError(_("This scenario has no taxes to open."))
        action = {
            "type": "ir.actions.act_window",
            "name": _("Taxes"),
            "res_model": "account.tax",
            "view_mode": "list,form",
            "domain": [("id", "in", taxes.ids)],
            "target": "current",
        }
        if len(taxes) == 1:
            action.update({"view_mode": "form", "res_id": taxes.id})
        return action

    def action_open_source_taxes(self):
        self.ensure_one()
        return self._open_taxes("source_tax_ids")

    def action_open_result_taxes(self):
        self.ensure_one()
        return self._open_taxes("result_tax_ids")

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Audit matrix rows are generated by the scanner."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_("Audit matrix rows are read-only."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Audit matrix rows are read-only."))
        return super().unlink()
