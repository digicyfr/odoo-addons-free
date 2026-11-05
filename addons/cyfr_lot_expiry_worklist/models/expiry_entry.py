from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.orm.domains import Domain


class LotExpiryEntry(models.Model):
    _name = "cyfr.lot.expiry.entry"
    _description = "Lot Expiry Location Action"
    _inherit = ["mail.thread"]
    _order = "expiration_date, location_id, lot_id, owner_key"

    company_id = fields.Many2one("res.company", required=True, index=True, ondelete="restrict", readonly=True)
    lot_id = fields.Many2one("stock.lot", required=True, index=True, ondelete="restrict", readonly=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict", readonly=True)
    location_id = fields.Many2one("stock.location", required=True, index=True, ondelete="restrict", readonly=True)
    owner_id = fields.Many2one("res.partner", string="Stock Owner", ondelete="restrict", readonly=True)
    owner_key = fields.Integer(required=True, default=0, readonly=True)
    on_hand = fields.Float(digits="Product Unit", readonly=True, help="Physical quantity in the product's base unit at the last scan.")
    reserved = fields.Float(digits="Product Unit", readonly=True, help="Reserved quantity at the last scan.")
    physical_unreserved = fields.Float(digits="Product Unit", readonly=True,
        help="On hand minus reserved. Odoo's native available quantity may be zero after the removal date.")
    product_uom_id = fields.Many2one("uom.uom", string="Unit", readonly=True)
    stock_present = fields.Boolean(readonly=True, help="Positive net on-hand quantity at the last scan.")
    expiration_date = fields.Datetime(readonly=True, help="The only date used for expiry and horizon decisions.")
    alert_date = fields.Datetime(readonly=True, help="Native Odoo alert threshold, shown for context only.")
    use_date = fields.Datetime(string="Best Before Date", readonly=True)
    removal_date = fields.Datetime(readonly=True)
    expiry_state = fields.Selection([
        ("expired", "Expired"), ("within_horizon", "Within Horizon"),
        ("outside_horizon", "Outside Last Horizon"),
    ], required=True, readonly=True)
    observed_at = fields.Datetime(required=True, readonly=True)
    scan_horizon_days = fields.Integer(readonly=True)
    assigned_user_id = fields.Many2one("res.users", string="Responsible User", tracking=True, ondelete="set null", readonly=True)
    next_action = fields.Char(tracking=True, readonly=True)
    action_note = fields.Text(tracking=True, readonly=True)
    status = fields.Selection([
        ("open", "Open"), ("assigned", "Assigned"), ("acknowledged", "Acknowledged"),
    ], default="open", required=True, tracking=True, readonly=True)
    acknowledged_by = fields.Many2one("res.users", readonly=True, ondelete="set null")
    acknowledged_at = fields.Datetime(readonly=True)

    _key_unique = models.Constraint(
        "unique(company_id, lot_id, location_id, owner_key)",
        "An action already exists for this lot, location and stock owner.",
    )

    @api.depends("lot_id.name", "location_id.complete_name", "owner_id.name")
    def _compute_display_name(self):
        for row in self:
            names = [row.lot_id.name, row.location_id.complete_name]
            if row.owner_id:
                names.append(row.owner_id.name)
            row.display_name = " / ".join(name for name in names if name) or self.env._("Lot Expiry Action")

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            lot_query = self.env["stock.lot"]._search([], active_test=False)
            product_query = self.env["product.product"]._search([], active_test=False)
            location_query = self.env["stock.location"]._search([], active_test=False)
            owner_query = self.env["res.partner"]._search([], active_test=False)
            domain = (Domain(domain) & Domain("lot_id", "in", lot_query)
                      & Domain("product_id", "in", product_query)
                      & Domain("location_id", "in", location_query)
                      & (Domain("owner_id", "=", False) | Domain("owner_id", "in", owner_query)))
        return super()._search(domain, offset=offset, limit=limit, order=order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        for model, ids in (
            ("stock.lot", set(self.sudo().mapped("lot_id").ids)),
            ("product.product", set(self.sudo().mapped("product_id").ids)),
            ("stock.location", set(self.sudo().mapped("location_id").ids)),
            ("res.partner", set(self.sudo().mapped("owner_id").ids)),
        ):
            if ids and self.env[model].browse(ids)._check_access("read"):
                return self, lambda: AccessError(self.env._("A linked stock record is no longer readable."))
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

    @api.constrains("company_id", "lot_id", "product_id", "location_id", "owner_id", "owner_key")
    def _check_identity(self):
        for row in self:
            if (row.location_id.usage != "internal" or row.location_id.company_id != row.company_id
                    or row.lot_id.product_id != row.product_id
                    or (row.lot_id.company_id and row.company_id != row.lot_id.company_id
                        and row.company_id not in row.lot_id.company_id.all_child_ids)
                    or row.owner_key != (row.owner_id.id or 0)):
                raise ValidationError(self.env._("The lot, product, location, owner and company must describe one stock position."))

    def _check_inventory_user(self):
        self.check_access("read")
        if not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(self.env._("Inventory access is required."))
        if any(row.company_id not in self.env.companies for row in self):
            raise AccessError(self.env._("The stock company must be active for your user."))

    def _check_manager(self):
        self._check_inventory_user()
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(self.env._("Only an inventory administrator may assign this action."))

    def action_open_assign(self):
        self.ensure_one()
        self._check_manager()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Assign Lot Action"),
            "res_model": "cyfr.lot.expiry.assign",
            "view_mode": "form",
            "target": "new",
            "context": {"default_entry_id": self.id},
        }

    def action_acknowledge(self):
        self.ensure_one()
        self._check_inventory_user()
        if self.status != "assigned":
            raise ValidationError(self.env._("Only an assigned action can be acknowledged."))
        if self.assigned_user_id != self.env.user and not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(self.env._("Only the responsible user or an inventory administrator may acknowledge."))
        self.sudo().write({"status": "acknowledged", "acknowledged_by": self.env.user.id,
                           "acknowledged_at": fields.Datetime.now()})
        return True

    def action_open_lot(self):
        self.ensure_one()
        self._check_inventory_user()
        self.lot_id.check_access("read")
        action = self.env.ref("stock.action_production_lot_form").read()[0]
        action.update({"res_id": self.lot_id.id, "view_mode": "form", "views": [(False, "form")]})
        return action

    def action_open_quants(self):
        self.ensure_one()
        self._check_inventory_user()
        domain = [("company_id", "=", self.company_id.id), ("lot_id", "=", self.lot_id.id),
                  ("location_id", "=", self.location_id.id), ("owner_id", "=", self.owner_id.id or False)]
        self.env["stock.quant"].search(domain, limit=1)
        return {"type": "ir.actions.act_window", "name": self.env._("Current Quants"),
                "res_model": "stock.quant", "view_mode": "list,form", "domain": domain}
