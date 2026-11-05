from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    cyfr_next_step_reason = fields.Selection(
        [
            ("no_activity", "No Scheduled Activity"),
            ("overdue", "Overdue Activity"),
        ],
        string="Next Step Status",
        compute="_compute_cyfr_next_step_reason",
        compute_sudo=False,
        help="Reason this lead appears in the Next Step Queue. This is based only on active Odoo activities.",
    )

    @api.depends("activity_ids.state")
    def _compute_cyfr_next_step_reason(self):
        for lead in self:
            if lead.activity_state == "overdue":
                lead.cyfr_next_step_reason = "overdue"
            elif not lead.activity_state:
                lead.cyfr_next_step_reason = "no_activity"
            else:
                lead.cyfr_next_step_reason = False
