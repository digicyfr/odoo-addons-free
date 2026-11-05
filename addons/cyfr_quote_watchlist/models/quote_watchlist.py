from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.orm.domains import Domain


MAX_CANDIDATES = 2000
MAX_RESULTS = 500
FILTER_FIELDS = {"company_id", "salesperson_id", "team_id", "valid_from", "valid_to"}


class QuoteWatchlistSetting(models.Model):
    _name = "cyfr.quote.watchlist.setting"
    _description = "Quote Watchlist Company Setting"
    _rec_name = "company_id"

    company_id = fields.Many2one("res.company", required=True, ondelete="cascade", index=True,
                                 default=lambda self: self.env.company)
    horizon_days = fields.Integer("Expiry Horizon (Days)", required=True, default=7)

    _company_unique = models.Constraint("UNIQUE(company_id)", "Only one watchlist setting is allowed per company.")

    @api.constrains("horizon_days")
    def _check_horizon(self):
        for setting in self:
            if not 0 <= setting.horizon_days <= 90:
                raise ValidationError(_("Expiry horizon must be between 0 and 90 days."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any((vals.get("company_id") or self.env.company.id) not in self.env.companies.ids
                                   for vals in vals_list):
            raise AccessError(_("The selected company is not allowed for your session."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and vals.get("company_id") and vals["company_id"] not in self.env.companies.ids:
            raise AccessError(_("The selected company is not allowed for your session."))
        return super().write(vals)


class QuoteWatchlist(models.TransientModel):
    _name = "cyfr.quote.watchlist"
    _description = "Quote Follow-up Watchlist Scan"

    @api.depends_context("lang")
    def _compute_display_name(self):
        for worklist in self:
            worklist.display_name = _("Quote Watchlist")

    scan_owner_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, readonly=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    salesperson_id = fields.Many2one("res.users", string="Salesperson")
    team_id = fields.Many2one("crm.team", string="Sales Team")
    valid_from = fields.Date("Validity From")
    valid_to = fields.Date("Validity Through")
    horizon_days = fields.Integer("Expiry Horizon (Days)", readonly=True)
    scanned_at = fields.Datetime("Last Scan", readonly=True)
    candidate_count = fields.Integer("Quotes Checked", readonly=True)
    result_count = fields.Integer("Quotes Shown", readonly=True)
    truncated = fields.Boolean("Results Truncated", readonly=True)
    line_ids = fields.One2many("cyfr.quote.watchlist.line", "worklist_id", readonly=True)

    @api.model
    def _horizon_for_company(self, company):
        setting = self.env["cyfr.quote.watchlist.setting"].search([("company_id", "=", company.id)], limit=1)
        return setting.horizon_days if setting else 7

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id:
            self.horizon_days = self._horizon_for_company(self.company_id)

    @api.constrains("valid_from", "valid_to")
    def _check_dates(self):
        for worklist in self:
            if worklist.valid_from and worklist.valid_to and worklist.valid_from > worklist.valid_to:
                raise ValidationError(_("Validity From must be on or before Validity Through."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(set(vals) - FILTER_FIELDS for vals in vals_list):
            raise AccessError(_("Only worklist filters may be set directly."))
        prepared = []
        for vals in vals_list:
            company_id = vals.get("company_id") or self.env.company.id
            if company_id not in self.env.companies.ids:
                raise AccessError(_("The selected company is not allowed for your session."))
            prepared.append({**vals, "company_id": company_id, "scan_owner_id": self.env.uid,
                             "horizon_days": self._horizon_for_company(self.env["res.company"].browse(company_id))})
        return super().create(prepared)

    def write(self, vals):
        if not self.env.su:
            self.check_access("write")
            if set(vals) - FILTER_FIELDS:
                raise AccessError(_("Only worklist filters may be changed directly."))
            if vals.get("company_id") and vals["company_id"] not in self.env.companies.ids:
                raise AccessError(_("The selected company is not allowed for your session."))
        result = super().write(vals)
        if FILTER_FIELDS.intersection(vals):
            for worklist in self:
                worklist.sudo().write({"line_ids": [Command.clear()], "scanned_at": False,
                                       "candidate_count": 0, "result_count": 0, "truncated": False,
                                       "horizon_days": worklist._horizon_for_company(worklist.company_id)})
        return result

    def _check_scope(self):
        self.ensure_one()
        self.check_access("read")
        if self.scan_owner_id != self.env.user or self.company_id not in self.env.companies:
            raise AccessError(_("This watchlist is outside your session scope."))

    def _candidate_domain(self):
        domain = [("state", "in", ("draft", "sent")), ("company_id", "=", self.company_id.id)]
        if self.salesperson_id:
            domain.append(("user_id", "=", self.salesperson_id.id))
        if self.team_id:
            domain.append(("team_id", "=", self.team_id.id))
        if self.valid_from:
            domain.append(("validity_date", ">=", self.valid_from))
        if self.valid_to:
            domain.append(("validity_date", "<=", self.valid_to))
        return domain

    def _activity_summary(self, order_ids, today):
        activity = self.env["mail.activity"]
        base = [("res_model", "=", "sale.order"), ("res_id", "in", order_ids)]
        future = dict(activity._read_group(base + [("date_deadline", ">", today)],
                                           ["res_id"], ["date_deadline:min"]))
        overdue = {res_id for (res_id,) in activity._read_group(
            base + [("date_deadline", "<", today)], ["res_id"])}
        due_today = {res_id for (res_id,) in activity._read_group(
            base + [("date_deadline", "=", today)], ["res_id"])}
        return future, overdue, due_today

    def action_scan(self):
        self.ensure_one()
        self._check_scope()
        self.check_access("write")
        today = fields.Date.context_today(self)
        horizon = self._horizon_for_company(self.company_id)
        orders = self.env["sale.order"].search(self._candidate_domain(), order="id desc",
                                               limit=MAX_CANDIDATES + 1)
        candidates_truncated = len(orders) > MAX_CANDIDATES
        orders = orders[:MAX_CANDIDATES]
        future, overdue, due_today = self._activity_summary(orders.ids, today) if orders else ({}, set(), set())
        values = []
        results_truncated = False
        for order in orders:
            expiry = ("missing" if not order.validity_date else
                      "expired" if order.validity_date < today else
                      "soon" if order.validity_date <= today + timedelta(days=horizon) else "later")
            missing_future = order.id not in future
            if expiry == "later" and not missing_future:
                continue
            if len(values) >= MAX_RESULTS:
                results_truncated = True
                break
            reason = {"expired": "expired", "soon": "soon", "missing": "missing"}.get(expiry, "no_future")
            values.append(Command.create({
                "order_id": order.id, "company_id": order.company_id.id, "reason_code": reason,
                "expiry_status": expiry, "missing_future_activity": missing_future,
                "next_activity_date": future.get(order.id), "has_overdue_activity": order.id in overdue,
                "has_due_today_activity": order.id in due_today,
            }))
        self.sudo().write({"line_ids": [Command.clear(), *values], "scanned_at": fields.Datetime.now(),
                           "horizon_days": horizon, "candidate_count": len(orders),
                           "result_count": len(values), "truncated": candidates_truncated or results_truncated})
        if self.truncated:
            # Keep the warning and count in front of the user. The results are
            # available from the adjacent View Last Scan button.
            return {"type": "ir.actions.act_window", "name": _("Quote Watchlist"),
                    "res_model": "cyfr.quote.watchlist", "view_mode": "form",
                    "res_id": self.id,
                    "views": [(self.env.ref("cyfr_quote_watchlist.view_quote_watchlist_form").id, "form")],
                    "context": {"create": False}}
        return self.action_open_results()

    def action_open_results(self):
        self.ensure_one()
        self._check_scope()
        return {"type": "ir.actions.act_window", "name": _("Quote Watchlist"),
                "res_model": "cyfr.quote.watchlist.line", "view_mode": "list,form",
                "views": [(self.env.ref("cyfr_quote_watchlist.view_quote_watchlist_line_list").id, "list"),
                          (self.env.ref("cyfr_quote_watchlist.view_quote_watchlist_line_form").id, "form")],
                "search_view_id": self.env.ref("cyfr_quote_watchlist.view_quote_watchlist_line_search").id,
                "domain": [("worklist_id", "=", self.id)],
                "context": {"create": False, "edit": False, "delete": False}}


class QuoteWatchlistLine(models.TransientModel):
    _name = "cyfr.quote.watchlist.line"
    _description = "Quote Follow-up Watchlist Row"
    _order = "id desc"

    worklist_id = fields.Many2one("cyfr.quote.watchlist", required=True, ondelete="cascade", readonly=True)
    scan_owner_id = fields.Many2one(related="worklist_id.scan_owner_id", store=True, readonly=True)
    order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", readonly=True)
    partner_id = fields.Many2one(related="order_id.partner_id", readonly=True)
    salesperson_id = fields.Many2one(related="order_id.user_id", readonly=True)
    team_id = fields.Many2one(related="order_id.team_id", readonly=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    validity_date = fields.Date(related="order_id.validity_date", readonly=True)
    reason_code = fields.Selection([
        ("expired", "Expired"), ("soon", "Expiring Soon"),
        ("missing", "Validity Date Missing"), ("no_future", "No Future Activity")], readonly=True)
    expiry_status = fields.Selection([
        ("expired", "Expired"), ("soon", "Expiring Soon"),
        ("missing", "Validity Date Missing"), ("later", "Later")], readonly=True)
    missing_future_activity = fields.Boolean("No Future Activity", readonly=True)
    next_activity_date = fields.Date("Next Future Activity", readonly=True)
    has_overdue_activity = fields.Boolean("Overdue Activity", readonly=True)
    has_due_today_activity = fields.Boolean("Activity Due Today", readonly=True)

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            source_query = self.env["sale.order"]._search([], active_test=False)
            domain = Domain(domain) & Domain("order_id", "in", source_query)
        return super()._search(domain, offset=offset, limit=limit, order=order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        orders = self.env["sale.order"].browse(self.sudo().mapped("order_id").ids)
        if orders._check_access("read"):
            return self, lambda: AccessError(_("A linked quotation is no longer readable."))
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

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Watchlist rows are generated only by a scan."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_("Watchlist rows are read-only."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Watchlist rows are removed only by a scan or expiration."))
        return super().unlink()

    def _check_source(self, *, require_write=False):
        self.ensure_one()
        self.check_access("read")
        self.worklist_id._check_scope()
        order = self.order_id
        order.check_access("read")
        if order.company_id != self.company_id or order.company_id not in self.env.companies:
            raise AccessError(_("This quotation is outside your session scope."))
        if require_write:
            order.check_access("write")
        return order

    def action_open_quote(self):
        order = self._check_source()
        return {"type": "ir.actions.act_window", "name": _("Quotation"),
                "res_model": "sale.order", "view_mode": "form", "res_id": order.id}

    def action_schedule_activity(self):
        order = self._check_source(require_write=True)
        if order.state not in ("draft", "sent"):
            raise UserError(_("This quotation is no longer open."))
        return {"type": "ir.actions.act_window", "name": _("Schedule Quote Follow-up"),
                "res_model": "mail.activity", "view_mode": "form",
                "views": [(self.env.ref("mail.mail_activity_view_form_popup").id, "form")],
                "target": "new", "context": {
                    "default_res_model_id": self.env["ir.model"]._get("sale.order").id,
                    "default_res_id": order.id,
                    "default_activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                    "default_user_id": self.env.uid,
                    "default_summary": _("Follow up quotation %s") % order.name,
                }}
