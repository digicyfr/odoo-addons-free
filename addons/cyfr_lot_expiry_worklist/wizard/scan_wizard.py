from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import float_compare


MAX_QUANTS = 5000
MAX_ACTIONS = 1000
MAX_HORIZON_DAYS = 365


class LotExpiryScan(models.TransientModel):
    _name = "cyfr.lot.expiry.scan"
    _description = "Lot Expiry Scan"

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    location_id = fields.Many2one("stock.location", required=True,
        help="This company-owned internal location and its internal descendants.")
    horizon_days = fields.Integer(default=30, required=True,
        help="Include lots expiring now or within this many 24-hour periods (UTC).")

    @api.constrains("company_id", "location_id", "horizon_days")
    def _check_scope(self):
        for scan in self:
            if not 0 <= scan.horizon_days <= MAX_HORIZON_DAYS:
                raise ValidationError(self.env._("The expiry horizon must be between 0 and 365 days."))
            if (scan.location_id and (scan.location_id.usage != "internal"
                    or not scan.location_id.active or scan.location_id.company_id != scan.company_id)):
                raise ValidationError(self.env._("Select an active company-owned internal location."))

    def action_scan(self):
        self.ensure_one()
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(self.env._("Only an inventory administrator may scan expiry actions."))
        self.check_access("read")
        if self.company_id not in self.env.companies:
            raise AccessError(self.env._("The scan company must be active for your user."))
        self._check_scope()
        now = fields.Datetime.now()
        horizon = now + timedelta(days=self.horizon_days)
        company = self.company_id
        domain = [
            ("company_id", "=", company.id),
            ("location_id", "child_of", self.location_id.id),
            ("location_id.usage", "=", "internal"),
            ("location_id.active", "=", True),
            ("location_id.company_id", "=", company.id),
            ("lot_id", "!=", False),
        ]
        # A custom quant rule must not turn hidden stock into an apparent
        # departure from an earlier snapshot. Compare IDs before any write.
        all_quants = self.env["stock.quant"].sudo().with_company(company).search(
            domain, order="id", limit=MAX_QUANTS + 1)
        quants = self.env["stock.quant"].with_company(company).search(
            domain, order="id", limit=MAX_QUANTS + 1)
        if set(quants.ids) != set(all_quants.ids):
            raise AccessError(self.env._("The selected stock scope cannot be scanned with your current access rights."))
        if len(all_quants) > MAX_QUANTS:
            raise ValidationError(self.env._("More than 5,000 lot quants match. Select a narrower internal location."))
        # Include prior rows even if a linked record became unreadable. The
        # caller sees an explicit access error rather than a partial refresh.
        Row = self.env["cyfr.lot.expiry.entry"].sudo()
        prior_domain = [
            ("company_id", "=", company.id),
            ("location_id", "child_of", self.location_id.id),
        ]
        entries = Row.with_context(active_test=False).search(prior_domain, limit=MAX_ACTIONS + 1)
        visible_entries = self.env["cyfr.lot.expiry.entry"].with_context(active_test=False).search(
            prior_domain, limit=MAX_ACTIONS + 1)
        if set(entries.ids) != set(visible_entries.ids):
            raise AccessError(self.env._("The selected stock scope cannot be scanned with your current access rights."))
        if len(entries) > MAX_ACTIONS:
            raise ValidationError(self.env._("More than 1,000 prior actions match. Select a narrower internal location."))

        # Check every relation through the caller's native ACL before the
        # administrative write. Do not silently skip a parent-owned lot.
        lot_ids = set(quants.mapped("lot_id").ids) | set(entries.mapped("lot_id").ids)
        visible_lots = self.env["stock.lot"].with_context(active_test=False).search([("id", "in", list(lot_ids))])
        if set(visible_lots.ids) != lot_ids:
            raise AccessError(self.env._("The selected stock scope cannot be scanned with your current access rights."))
        product_ids = set(quants.mapped("product_id").ids) | set(entries.mapped("product_id").ids)
        visible_products = self.env["product.product"].with_context(active_test=False).search([
            ("id", "in", list(product_ids)),
        ])
        if set(visible_products.ids) != product_ids:
            raise AccessError(self.env._("The selected stock scope cannot be scanned with your current access rights."))
        location_ids = set(quants.mapped("location_id").ids) | set(entries.mapped("location_id").ids)
        visible_locations = self.env["stock.location"].with_context(active_test=False).search([("id", "in", list(location_ids))])
        if set(visible_locations.ids) != location_ids:
            raise AccessError(self.env._("The selected stock scope cannot be scanned with your current access rights."))
        owner_ids = set(quants.mapped("owner_id").ids) | set(entries.mapped("owner_id").ids)
        visible_owners = self.env["res.partner"].with_context(active_test=False).search([("id", "in", list(owner_ids))])
        if set(visible_owners.ids) != owner_ids:
            raise AccessError(self.env._("The selected stock scope cannot be scanned with your current access rights."))

        grouped = defaultdict(lambda: [0.0, 0.0])
        lots = {lot.id: lot for lot in visible_lots}
        for quant in quants:
            key = (quant.lot_id.id, quant.location_id.id, quant.owner_id.id or 0)
            amounts = grouped[key]
            amounts[0] += quant.quantity
            amounts[1] += quant.reserved_quantity
        if len(set(grouped) | {(row.lot_id.id, row.location_id.id, row.owner_key) for row in entries}) > MAX_ACTIONS:
            raise ValidationError(self.env._("More than 1,000 lot positions match. Select a narrower internal location."))

        old = {(row.lot_id.id, row.location_id.id, row.owner_key): row for row in entries.sudo()}
        shown = []
        to_create = []
        for key in sorted(set(grouped) | set(old)):
            lot_id, location_id, owner_key = key
            lot = lots.get(lot_id)
            if not lot:
                # The linked lot could have been archived after an older scan.
                continue
            on_hand, reserved = grouped.get(key, (0.0, 0.0))
            rounding = lot.product_id.uom_id.rounding
            present = float_compare(on_hand, 0, precision_rounding=rounding) > 0
            expires = lot.expiration_date
            in_horizon = bool(present and lot.product_id.use_expiration_date and expires and expires <= horizon)
            if not in_horizon and key not in old:
                continue
            if expires and expires <= now:
                expiry_state = "expired"
            elif in_horizon:
                expiry_state = "within_horizon"
            else:
                expiry_state = "outside_horizon"
            values = {
                "on_hand": on_hand,
                "reserved": reserved,
                "physical_unreserved": on_hand - reserved,
                "stock_present": present,
                "expiration_date": expires or False,
                "alert_date": lot.alert_date or False,
                "use_date": lot.use_date or False,
                "removal_date": lot.removal_date or False,
                "expiry_state": expiry_state,
                "observed_at": now,
                "scan_horizon_days": self.horizon_days,
            }
            if key in old:
                old[key].sudo().write(values)
                if in_horizon:
                    shown.append(old[key].id)
            else:
                to_create.append({
                    "company_id": company.id,
                    "lot_id": lot_id,
                    "product_id": lot.product_id.id,
                    "product_uom_id": lot.product_id.uom_id.id,
                    "location_id": location_id,
                    "owner_id": owner_key or False,
                    "owner_key": owner_key,
                    **values,
                })
        for start in range(0, len(to_create), 200):
            shown.extend(Row.create(to_create[start:start + 200]).ids)
        action = self.env.ref("cyfr_lot_expiry_worklist.action_lot_expiry_entry").read()[0]
        action["domain"] = [("id", "in", shown)]
        return action
