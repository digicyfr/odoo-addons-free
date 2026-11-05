from psycopg2 import IntegrityError

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class PosRefundReason(models.Model):
    _name = "cyfr.pos.refund.reason"
    _description = "POS Refund Reason"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade", index=True)

    _code_company_unique = models.Constraint("unique (code, company_id)", "Reason code must be unique within a company.")

    def _check_target_company(self, company_id):
        if not self.env.su and company_id not in self.env.companies.ids:
            raise AccessError(_("You cannot move a refund reason to a company you cannot access."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_target_company(vals.get("company_id") or self.env.company.id)
        return super().create(vals_list)

    def write(self, vals):
        self.check_access("write")
        if "company_id" in vals:
            self._check_target_company(vals["company_id"])
            moving = self.filtered(lambda reason: reason.company_id.id != vals["company_id"])
            if moving and self.env["cyfr.pos.refund.case"].sudo().search_count([
                ("reason_id", "in", moving.ids),
            ]):
                raise ValidationError(_("A reason already used in evidence cannot change company."))
        return super().write(vals)

    @api.constrains("code")
    def _check_code(self):
        for reason in self:
            if not reason.code or not reason.code.strip() or reason.code != reason.code.strip():
                raise ValidationError(_("Reason code must be nonempty and have no outer spaces."))


class PosRefundEvidenceCase(models.Model):
    _name = "cyfr.pos.refund.case"
    _description = "POS Refund Evidence Case"
    _order = "refund_date desc, id desc"

    refund_order_id = fields.Many2one("pos.order", required=True, readonly=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="refund_order_id.company_id", store=True, readonly=True, index=True)
    config_id = fields.Many2one(related="refund_order_id.config_id", store=True, readonly=True, index=True)
    order_user_id = fields.Many2one(
        related="refund_order_id.user_id", string="POS Order User",
        store=True, readonly=True, index=True,
    )
    refund_date = fields.Datetime(related="refund_order_id.date_order", store=True, readonly=True, index=True)
    refund_line_ids = fields.One2many(
        "pos.order.line", compute="_compute_refund_line_ids", compute_sudo=False,
        string="Refund Lines", readonly=True,
    )
    reason_id = fields.Many2one("cyfr.pos.refund.reason", ondelete="restrict", index=True)
    condition_note = fields.Text(help="Describe the returned goods; do not enter sensitive customer information.")
    manager_note = fields.Text(groups="point_of_sale.group_pos_manager")
    recorded_by_id = fields.Many2one("res.users", readonly=True, ondelete="set null")
    captured_at = fields.Datetime(readonly=True)
    state = fields.Selection([("incomplete", "Incomplete"), ("complete", "Complete")], compute="_compute_state", store=True, index=True)
    origin_order_count = fields.Integer(compute="_compute_origin_order_count")

    _refund_unique = models.Constraint("unique (refund_order_id)", "Only one evidence case is allowed per refund order.")

    @api.depends("refund_order_id.lines")
    def _compute_refund_line_ids(self):
        for case in self:
            case.refund_line_ids = case.refund_order_id.lines

    @api.depends("reason_id", "condition_note")
    def _compute_state(self):
        for case in self:
            case.state = "complete" if case.reason_id and case.condition_note and case.condition_note.strip() else "incomplete"

    @api.depends("refund_order_id.lines.refunded_orderline_id")
    def _compute_origin_order_count(self):
        for case in self:
            case.origin_order_count = len(set(case.refund_line_ids.mapped("refunded_orderline_id.order_id").ids))

    @api.depends("refund_order_id.name")
    def _compute_display_name(self):
        for case in self:
            case.display_name = _("Refund evidence: %s", case.refund_order_id.name)

    def _check_reason_company(self, reason):
        if reason and (reason.company_id != self.company_id or not reason.active):
            raise ValidationError(_("Choose an active reason from the refund company."))

    @api.constrains("refund_order_id", "reason_id")
    def _check_case_values(self):
        for case in self:
            if not case.refund_order_id.is_refund:
                raise ValidationError(_("Evidence cases require a native refund order."))
            case._check_reason_company(case.reason_id)

    def write(self, vals):
        self.check_access("write")
        manager = self.env.user.has_group("point_of_sale.group_pos_manager")
        allowed = {"reason_id", "condition_note", "manager_note"} if manager else {"reason_id", "condition_note"}
        if set(vals) - allowed:
            raise AccessError(_("Refund provenance and capture metadata cannot be edited."))
        if "reason_id" in vals:
            reason = self.env["cyfr.pos.refund.reason"].browse(vals["reason_id"]) if vals["reason_id"] else False
            if reason:
                reason.check_access("read")
            for case in self:
                case._check_reason_company(reason)
        if set(vals) & {"reason_id", "condition_note"}:
            vals = {**vals, "recorded_by_id": self.env.uid, "captured_at": fields.Datetime.now()}
            # These two values are set only by this method, after the user-supplied
            # whitelist has been checked. A normal user cannot spoof them by RPC.
            return super().write(vals)
        return super().write(vals)

    def action_open_origins(self):
        self.ensure_one()
        self.check_access("read")
        origins = self.refund_line_ids.mapped("refunded_orderline_id.order_id")
        origins.check_access("read")
        return {
            "type": "ir.actions.act_window",
            "name": _("Original Sales"),
            "res_model": "pos.order",
            "view_mode": "list,form",
            "domain": [("id", "in", origins.ids)],
            "context": {"create": False},
        }


class PosOrder(models.Model):
    _inherit = "pos.order"

    refund_evidence_case_id = fields.One2many("cyfr.pos.refund.case", "refund_order_id", string="Refund Evidence", readonly=True)

    def _ensure_refund_evidence_cases(self):
        Case = self.env["cyfr.pos.refund.case"].sudo()
        for order in self.filtered("is_refund"):
            if Case.search_count([("refund_order_id", "=", order.id)]):
                continue
            try:
                with self.env.cr.savepoint():
                    Case.create({"refund_order_id": order.id})
            except IntegrityError:
                # A concurrent sync may have inserted the same case. The SQL
                # constraint remains the final arbiter of idempotence.
                if not Case.search_count([("refund_order_id", "=", order.id)]):
                    raise

    def _process_saved_order(self, draft):
        result = super()._process_saved_order(draft)
        self._ensure_refund_evidence_cases()
        return result

    @api.model
    def sync_from_ui(self, orders):
        result = super().sync_from_ui(orders)
        # Core ignores an already-paid order on reconnect. Reconcile cases for
        # only the UUIDs in this bounded request, including older refunds that
        # predate addon installation, without changing the native sync result.
        uuids = [order.get("uuid") for order in orders if order.get("uuid")]
        if uuids:
            self.search([("uuid", "in", uuids), ("is_refund", "=", True)])._ensure_refund_evidence_cases()
        return result

    def _refund(self):
        refunds = super()._refund()
        refunds._ensure_refund_evidence_cases()
        return refunds


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    cyfr_original_order_id = fields.Many2one(
        "pos.order", compute="_compute_cyfr_original_order_id",
        compute_sudo=False, string="Original Sale", readonly=True,
    )

    @api.depends("refunded_orderline_id.order_id")
    def _compute_cyfr_original_order_id(self):
        for line in self:
            line.cyfr_original_order_id = line.refunded_orderline_id.order_id
