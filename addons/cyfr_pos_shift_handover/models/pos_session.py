from odoo import _, models
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = "pos.session"

    def action_open_outgoing_handover(self):
        self.ensure_one()
        self.check_access("read")
        if self.rescue or self.state == "opening_control":
            raise UserError(_("Open the regular session before preparing a handover."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Outgoing Handovers"),
            "res_model": "cyfr.pos.handover",
            "view_mode": "list,form",
            "domain": [("source_session_id", "=", self.id)],
            "context": {"default_source_session_id": self.id},
        }

    def action_open_incoming_handover(self):
        self.ensure_one()
        self.check_access("read")
        if self.rescue or self.state != "opened" or not self.start_at:
            raise UserError(_("Only an open regular session can receive a handover."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Incoming Handovers"),
            "res_model": "cyfr.pos.handover",
            "view_mode": "list,form",
            "domain": [
                ("config_id", "=", self.config_id.id),
                "|", ("target_session_id", "=", self.id),
                "&", "&", ("target_session_id", "=", False),
                ("source_session_id.state", "=", "closed"),
                ("source_session_id.stop_at", "<", self.start_at),
            ],
            "context": {"create": False},
        }
