from odoo import fields, models
from odoo.exceptions import AccessError, ValidationError


class LotExpiryAssign(models.TransientModel):
    _name = "cyfr.lot.expiry.assign"
    _description = "Assign Lot Expiry Action"

    entry_id = fields.Many2one("cyfr.lot.expiry.entry", required=True)
    assigned_user_id = fields.Many2one("res.users", required=True, string="Responsible User")
    next_action = fields.Char(required=True)
    action_note = fields.Text()

    def action_assign(self):
        self.ensure_one()
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(self.env._("Only an inventory administrator may assign this action."))
        self.check_access("read")
        row = self.entry_id
        row._check_manager()
        assignee = self.assigned_user_id
        if (not assignee.active or row.company_id not in assignee.company_ids
                or not assignee.has_group("stock.group_stock_user")):
            raise ValidationError(self.env._("The responsible user must be an active inventory user in this company."))
        if not self.next_action or not self.next_action.strip():
            raise ValidationError(self.env._("Enter a next action."))
        row.sudo().write({
            "assigned_user_id": assignee.id,
            "next_action": self.next_action.strip(),
            "action_note": self.action_note or False,
            "status": "assigned",
            "acknowledged_by": False,
            "acknowledged_at": False,
        })
        return {"type": "ir.actions.act_window_close"}
