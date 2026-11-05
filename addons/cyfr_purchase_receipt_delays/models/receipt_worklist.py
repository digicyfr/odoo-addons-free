from datetime import datetime, time, timedelta

import pytz
from markupsafe import escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.orm.domains import Domain


MAX_CANDIDATES = 2000
MAX_RESULTS = 500
FILTER_FIELDS = {"horizon_days", "vendor_id", "buyer_id", "company_id", "date_from", "date_to"}


class ReceiptWorklist(models.TransientModel):
    _name = "cyfr.purchase.receipt.worklist"
    _description = "Late Receipt Worklist Scan"

    @api.depends_context("lang")
    def _compute_display_name(self):
        for worklist in self:
            worklist.display_name = _("Late Receipts")

    owner_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, readonly=True)
    horizon_days = fields.Integer("Due Soon (Days)", default=7, required=True)
    vendor_id = fields.Many2one("res.partner", string="Vendor")
    buyer_id = fields.Many2one("res.users", string="Buyer")
    company_id = fields.Many2one("res.company", string="Company")
    date_from = fields.Date("Expected From")
    date_to = fields.Date("Expected Through")
    scanned_at = fields.Datetime("Last Scan", readonly=True)
    candidate_count = fields.Integer("Lines Checked", readonly=True)
    result_count = fields.Integer("Lines Shown", readonly=True)
    truncated = fields.Boolean("Results Truncated", readonly=True)
    line_ids = fields.One2many("cyfr.purchase.receipt.worklist.line", "worklist_id", readonly=True)

    @api.constrains("horizon_days", "date_from", "date_to")
    def _check_filters(self):
        for worklist in self:
            if not 0 <= worklist.horizon_days <= 90:
                raise ValidationError(_("Due-soon horizon must be between 0 and 90 days."))
            if worklist.date_from and worklist.date_to and worklist.date_from > worklist.date_to:
                raise ValidationError(_("Expected From must be on or before Expected Through."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(set(vals) - FILTER_FIELDS for vals in vals_list):
            raise AccessError(_("Only worklist filters may be set directly."))
        if not self.env.su and any(vals.get("company_id") and
                                   vals["company_id"] not in self.env.companies.ids for vals in vals_list):
            raise AccessError(_("The selected company is not allowed for your session."))
        return super().create([{**vals, "owner_id": self.env.uid} for vals in vals_list])

    def write(self, vals):
        if not self.env.su:
            if set(vals) - FILTER_FIELDS:
                raise AccessError(_("Only worklist filters may be changed directly."))
            self.check_access("write")
            if vals.get("company_id") and vals["company_id"] not in self.env.companies.ids:
                raise AccessError(_("The selected company is not allowed for your session."))
        result = super().write(vals)
        if FILTER_FIELDS.intersection(vals):
            self.sudo().write({"line_ids": [Command.clear()], "scanned_at": False,
                               "candidate_count": 0, "result_count": 0, "truncated": False})
        return result

    def _check_scope(self):
        self.ensure_one()
        self.check_access("read")
        if self.owner_id != self.env.user:
            raise AccessError(_("You can only use your own receipt worklist."))
        if self.company_id and self.company_id not in self.env.companies:
            raise AccessError(_("The selected company is not allowed for your session."))

    def _local_day(self, value):
        return fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(value)).date() if value else False

    def _status(self, planned, today, horizon):
        if not planned:
            return "missing"
        planned_day = self._local_day(planned)
        if planned_day < today:
            return "late"
        if planned_day <= today + timedelta(days=horizon):
            return "soon"
        return False

    def _end_utc(self, local_end):
        tz = pytz.timezone(self.env.context.get("tz") or self.env.user.tz or "UTC")
        next_midnight = tz.localize(datetime.combine(local_end + timedelta(days=1), time.min))
        return next_midnight.astimezone(pytz.UTC).replace(tzinfo=None)

    def _candidate_domain(self, today):
        end_day = today + timedelta(days=self.horizon_days)
        if self.date_to:
            end_day = min(end_day, self.date_to)
        domain = [
            ("state", "=", "purchase"),
            ("display_type", "=", False),
            ("is_downpayment", "=", False),
            ("product_id.type", "=", "consu"),
            ("order_id.dest_address_id", "=", False),
            "|", ("date_planned", "=", False), ("date_planned", "<", self._end_utc(end_day)),
        ]
        if self.vendor_id:
            domain.append(("partner_id", "=", self.vendor_id.id))
        if self.buyer_id:
            domain.append(("order_id.user_id", "=", self.buyer_id.id))
        if self.company_id:
            domain.append(("company_id", "=", self.company_id.id))
        else:
            domain.append(("company_id", "in", self.env.companies.ids))
        return domain

    def action_scan(self):
        self.ensure_one()
        self._check_scope()
        self.check_access("write")
        today = fields.Date.context_today(self)
        lines = self.env["purchase.order.line"].search(
            self._candidate_domain(today), order="date_planned asc, id asc", limit=MAX_CANDIDATES + 1,
        )
        candidates_truncated = len(lines) > MAX_CANDIDATES
        lines = lines[:MAX_CANDIDATES]
        values = []
        results_truncated = False
        for line in lines:
            remaining = line.product_qty - line.qty_received
            if line.product_uom_id.compare(remaining, 0.0) <= 0:
                continue
            status = self._status(line.date_planned, today, self.horizon_days)
            if not status:
                continue
            local_day = self._local_day(line.date_planned)
            if local_day and self.date_from and local_day < self.date_from:
                continue
            if local_day and self.date_to and local_day > self.date_to:
                continue
            if not local_day and (self.date_from or self.date_to):
                continue
            if len(values) >= MAX_RESULTS:
                results_truncated = True
                break
            values.append(Command.create({
                "purchase_line_id": line.id,
                "company_id": line.company_id.id,
                "status": status,
                "remaining_qty": remaining,
                "expected_day": local_day,
            }))
        self.sudo().write({
            "line_ids": [Command.clear(), *values],
            "scanned_at": fields.Datetime.now(),
            "candidate_count": len(lines),
            "result_count": len(values),
            "truncated": candidates_truncated or results_truncated,
        })
        return self.action_open_results()

    def action_open_results(self):
        self.ensure_one()
        self._check_scope()
        return {
            "type": "ir.actions.act_window",
            "name": _("Late Receipts"),
            "res_model": "cyfr.purchase.receipt.worklist.line",
            "view_mode": "list,form",
            "views": [(self.env.ref("cyfr_purchase_receipt_delays.view_receipt_worklist_line_list").id, "list"),
                      (self.env.ref("cyfr_purchase_receipt_delays.view_receipt_worklist_line_form").id, "form")],
            "search_view_id": self.env.ref("cyfr_purchase_receipt_delays.view_receipt_worklist_line_search").id,
            "domain": [("worklist_id", "=", self.id)],
            "context": {"create": False, "edit": False, "delete": False},
        }


class ReceiptWorklistLine(models.TransientModel):
    _name = "cyfr.purchase.receipt.worklist.line"
    _description = "Late Receipt Worklist Row"
    _order = "expected_day asc, id asc"

    worklist_id = fields.Many2one("cyfr.purchase.receipt.worklist", required=True, ondelete="cascade", readonly=True)
    owner_id = fields.Many2one(related="worklist_id.owner_id", store=True, readonly=True)
    purchase_line_id = fields.Many2one("purchase.order.line", required=True, ondelete="cascade", readonly=True)
    order_id = fields.Many2one(related="purchase_line_id.order_id", readonly=True)
    product_id = fields.Many2one(related="purchase_line_id.product_id", readonly=True)
    vendor_id = fields.Many2one(related="purchase_line_id.partner_id", readonly=True)
    buyer_id = fields.Many2one(related="purchase_line_id.order_id.user_id", readonly=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    expected_day = fields.Date("Expected Day", readonly=True)
    status = fields.Selection([("late", "Late"), ("soon", "Due Soon"), ("missing", "Date Missing")], readonly=True)
    ordered_qty = fields.Float(related="purchase_line_id.product_qty", readonly=True)
    received_qty = fields.Float(related="purchase_line_id.qty_received", readonly=True)
    remaining_qty = fields.Float("Remaining Qty", digits="Product Unit", readonly=True)
    uom_id = fields.Many2one(related="purchase_line_id.product_uom_id", readonly=True)
    receipt_ids = fields.Many2many("stock.picking", compute="_compute_receipt_ids", string="Receipts")

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            source_query = self.env["purchase.order.line"]._search([], active_test=False)
            domain = Domain(domain) & Domain("purchase_line_id", "in", source_query)
        return super()._search(domain, offset=offset, limit=limit, order=order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        ids = self.sudo().mapped("purchase_line_id").ids
        if self.env["purchase.order.line"].browse(ids)._check_access("read"):
            return self, lambda: AccessError(_("A linked purchase line is no longer readable."))
        return None

    def read(self, fields=None, load="_classic_read"):
        self.check_access("read")
        return super().read(fields=fields, load=load)

    def _read_format(self, fnames, load="_classic_read"):
        self.check_access("read")
        return super()._read_format(fnames=fnames, load=load)

    def export_data(self, fields_to_export):
        self.check_access("read")
        return super().export_data(fields_to_export)

    @api.depends("purchase_line_id.move_ids.picking_id")
    def _compute_receipt_ids(self):
        for row in self:
            row.receipt_ids = row.purchase_line_id.move_ids.picking_id.filtered(
                lambda picking: picking.company_id == row.company_id
            )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Worklist rows are generated only by a scan."))
        for vals in vals_list:
            worklist = self.env["cyfr.purchase.receipt.worklist"].browse(vals.get("worklist_id"))
            worklist._check_scope()
            line = self.env["purchase.order.line"].browse(vals.get("purchase_line_id"))
            line.check_access("read")
            if ((worklist.company_id and line.company_id != worklist.company_id)
                    or line.company_id not in self.env.companies):
                raise AccessError(_("The purchase line company is not allowed for this worklist."))
            vals["company_id"] = line.company_id.id
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_("Worklist rows are read-only."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Worklist rows are removed only by a scan or by expiration."))
        return super().unlink()

    def _check_source(self, *, require_write=False):
        self.ensure_one()
        self.check_access("read")
        self.worklist_id._check_scope()
        line = self.purchase_line_id
        line.check_access("read")
        if line.company_id != self.company_id or line.company_id not in self.env.companies:
            raise AccessError(_("This purchase line is no longer in an allowed company."))
        if require_write:
            line.order_id.check_access("write")
        return line

    def action_open_order(self):
        line = self._check_source()
        return {"type": "ir.actions.act_window", "name": _("Purchase Order"),
                "res_model": "purchase.order", "view_mode": "form", "res_id": line.order_id.id}

    def action_open_receipts(self):
        self._check_source()
        pickings = self.receipt_ids
        pickings.check_access("read")
        return {"type": "ir.actions.act_window", "name": _("Receipts"),
                "res_model": "stock.picking", "view_mode": "list,form",
                "domain": [("id", "in", pickings.ids)]}

    def action_schedule_activity(self):
        line = self._check_source(require_write=True)
        if line.state != "purchase":
            raise UserError(_("This purchase order is no longer confirmed."))
        if line.product_uom_id.compare(line.product_qty - line.qty_received, 0.0) <= 0:
            raise UserError(_("This purchase line is already fully received."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Schedule Purchase Follow-up"),
            "res_model": "mail.activity",
            "view_mode": "form",
            "views": [(self.env.ref("mail.mail_activity_view_form_popup").id, "form")],
            "target": "new",
            "context": {
                "default_res_model_id": self.env["ir.model"]._get("purchase.order").id,
                "default_res_id": line.order_id.id,
                "default_activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "default_user_id": self.env.uid,
                "default_summary": _("Follow up on purchase line #%s") % line.id,
                "default_note": _("Purchase order %s, line #%s: %s") %
                                (escape(line.order_id.name), line.id, escape(line.name)),
            },
        }
