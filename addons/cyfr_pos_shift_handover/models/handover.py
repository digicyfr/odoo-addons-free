from collections.abc import Collection

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, LockError, UserError, ValidationError
from odoo.orm.domains import Domain


class PosShiftHandover(models.Model):
    _name = "cyfr.pos.handover"
    _description = "POS Shift Handover"
    _order = "id desc"

    name = fields.Char("Handover", required=True, default=lambda self: _("Shift Handover"))
    source_session_id = fields.Many2one("pos.session", string="Outgoing Session", required=True,
                                        ondelete="restrict", index=True, readonly=True)
    config_id = fields.Many2one("pos.config", related="source_session_id.config_id", store=True, readonly=True)
    company_id = fields.Many2one("res.company", related="source_session_id.company_id", store=True,
                                 readonly=True, index=True)
    target_session_id = fields.Many2one("pos.session", string="Incoming Session", ondelete="restrict",
                                        readonly=True, index=True)
    created_by_id = fields.Many2one("res.users", string="Prepared By", required=True,
                                    default=lambda self: self.env.user, readonly=True)
    claimed_by_id = fields.Many2one("res.users", string="Claimed By", readonly=True)
    claimed_at = fields.Datetime("Claimed At", readonly=True)
    acknowledged_by_id = fields.Many2one("res.users", string="Acknowledged By", readonly=True)
    acknowledged_at = fields.Datetime("Acknowledged At", readonly=True)
    state = fields.Selection([
        ("unclaimed", "Unclaimed"), ("claimed", "Claimed"),
        ("acknowledged", "Acknowledged"),
    ], compute="_compute_state", store=True, readonly=True)
    task_ids = fields.One2many("cyfr.pos.handover.task", "handover_id", string="Tasks")

    _one_handover_per_session = models.Constraint(
        "UNIQUE(source_session_id)", "Only one handover is allowed for each outgoing POS session.")

    @api.depends("target_session_id", "acknowledged_at")
    def _compute_state(self):
        for handover in self:
            handover.state = ("acknowledged" if handover.acknowledged_at else
                              "claimed" if handover.target_session_id else "unclaimed")

    @api.constrains("source_session_id", "target_session_id", "claimed_by_id", "claimed_at",
                    "acknowledged_by_id", "acknowledged_at")
    def _check_session_consistency(self):
        for handover in self:
            source = handover.source_session_id
            target = handover.target_session_id
            if source.rescue:
                raise ValidationError(_("Recovery sessions cannot be handover sources."))
            if target:
                if target.rescue or target == source or target.config_id != source.config_id or target.company_id != source.company_id:
                    raise ValidationError(_("The incoming session must be a later regular session on the same register and company."))
                if not source.stop_at or not target.start_at or target.start_at <= source.stop_at:
                    raise ValidationError(_("The incoming session must open after the outgoing session closed."))
            if bool(target) != bool(handover.claimed_by_id) or bool(target) != bool(handover.claimed_at):
                raise ValidationError(_("A claimed handover requires a session, user, and timestamp."))
            if bool(handover.acknowledged_by_id) != bool(handover.acknowledged_at) or (handover.acknowledged_at and not target):
                raise ValidationError(_("Acknowledgement requires a claim, user, and timestamp."))

    @api.model
    def _require_pos_user(self):
        if not self.env.su and not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise AccessError(_("A Point of Sale user is required."))

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            visible_sessions = self.env["pos.session"]._search([], active_test=False)
            visible_configs = self.env["pos.config"]._search([], active_test=False)
            domain = (Domain(domain) & Domain("source_session_id", "in", visible_sessions)
                      & Domain("config_id", "in", visible_configs)
                      & (Domain("target_session_id", "=", False)
                         | Domain("target_session_id", "in", visible_sessions)))
        return super()._search(domain, offset=offset, limit=limit, order=order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        protected = self.sudo()
        session_ids = (protected.mapped("source_session_id") | protected.mapped("target_session_id")).ids
        config_ids = protected.mapped("config_id").ids
        if (self.env["pos.session"].browse(session_ids)._check_access("read")
                or self.env["pos.config"].browse(config_ids)._check_access("read")):
            return self, lambda: AccessError(_("A linked POS session or register is no longer readable."))
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
        self._require_pos_user()
        allowed = {"name", "source_session_id", "task_ids"}
        for vals in vals_list:
            if not self.env.su and set(vals) - allowed:
                raise AccessError(_("Claim and acknowledgement fields can only be set by their buttons."))
            source = self.env["pos.session"].browse(vals.get("source_session_id") or self.env.context.get("default_source_session_id"))
            if not source.exists():
                raise ValidationError(_("Choose an outgoing POS session."))
            source.check_access("read")
            source.config_id.check_access("read")
            if source.company_id not in self.env.companies or source.rescue or source.state == "opening_control":
                raise AccessError(_("The outgoing session is outside your allowed scope or has not opened."))
            vals["source_session_id"] = source.id
            if not self.env.su:
                vals["created_by_id"] = self.env.uid
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            self._require_pos_user()
            self.check_access("read")  # Recheck live source/target session and register rules.
            self.check_access("write")
            if set(vals) - {"name", "task_ids"}:
                raise AccessError(_("Session and acknowledgement fields cannot be edited directly."))
            manager = self.env.user.has_group("point_of_sale.group_pos_manager")
            if not manager and any(row.created_by_id != self.env.user or row.target_session_id for row in self):
                raise AccessError(_("Only the preparer may edit an unclaimed handover."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Shift handovers are retained for audit and cannot be deleted."))
        return super().unlink()

    def _check_operational_scope(self):
        self.ensure_one()
        self._require_pos_user()
        self.check_access("read")
        self.check_access("write")
        self.source_session_id.check_access("read")
        self.config_id.check_access("read")
        if self.company_id not in self.env.companies:
            raise AccessError(_("This handover belongs to another company."))

    def _form_action(self):
        return {"type": "ir.actions.act_window", "name": _("Shift Handover"),
                "res_model": self._name, "view_mode": "form", "res_id": self.id}

    def action_claim(self, target_session_id=None):
        self.ensure_one()
        self._check_operational_scope()
        try:
            self.lock_for_update(allow_referencing=True)
        except LockError as exc:
            raise UserError(_("Another user is claiming this handover. Retry shortly.")) from exc
        self.invalidate_recordset(["target_session_id", "claimed_by_id", "claimed_at", "source_session_id"])
        if self.target_session_id:
            if self.claimed_by_id == self.env.user:
                return self._form_action()  # Retry by the original claimant is idempotent.
            raise UserError(_("This handover has already been claimed by another user."))
        source = self.source_session_id
        if source.rescue or source.state != "closed" or not source.stop_at:
            raise UserError(_("Close the regular outgoing session before it can be claimed."))
        self.config_id.invalidate_recordset(["current_session_id"])
        current = self.config_id.current_session_id
        target = self.env["pos.session"].browse(target_session_id) if target_session_id else current
        if target != current:
            raise UserError(_("Only the current session of this register may receive the handover."))
        if not target or target.rescue or target.state != "opened" or not target.start_at:
            raise UserError(_("Open the next regular session on this register before claiming."))
        target.check_access("read")
        if target.config_id != source.config_id or target.company_id != source.company_id or target.start_at <= source.stop_at:
            raise UserError(_("The receiving session must be later and on the same register and company."))
        super().write({"target_session_id": target.id, "claimed_by_id": self.env.uid,
                       "claimed_at": fields.Datetime.now()})
        return self._form_action()

    def action_acknowledge(self):
        self.ensure_one()
        self._check_operational_scope()
        try:
            self.lock_for_update(allow_referencing=True)
        except LockError as exc:
            raise UserError(_("Another user is updating this handover. Retry shortly.")) from exc
        self.invalidate_recordset(["target_session_id", "claimed_by_id", "acknowledged_by_id", "acknowledged_at"])
        if not self.target_session_id:
            raise UserError(_("Claim this handover before acknowledging it."))
        self.target_session_id.check_access("read")
        if self.acknowledged_at:
            if self.acknowledged_by_id == self.env.user:
                return self._form_action()
            raise UserError(_("This handover has already been acknowledged by another user."))
        if self.claimed_by_id != self.env.user and not self.env.user.has_group("point_of_sale.group_pos_manager"):
            raise AccessError(_("Only the claimant or a POS manager may acknowledge this handover."))
        super().write({"acknowledged_by_id": self.env.uid, "acknowledged_at": fields.Datetime.now()})
        return self._form_action()

    def action_open_tasks(self):
        self.ensure_one()
        self._check_operational_scope()
        return {"type": "ir.actions.act_window", "name": _("Handover Tasks"),
                "res_model": "cyfr.pos.handover.task", "view_mode": "list,form",
                "domain": [("handover_id", "=", self.id)],
                "context": {"default_handover_id": self.id}}


class PosShiftHandoverTask(models.Model):
    _name = "cyfr.pos.handover.task"
    _description = "POS Shift Handover Task"
    _order = "due_at asc, id asc"

    handover_id = fields.Many2one("cyfr.pos.handover", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", related="handover_id.company_id", store=True,
                                 readonly=True, index=True)
    title = fields.Char("Task", required=True)
    priority = fields.Selection([("normal", "Normal"), ("high", "High"),
                                 ("urgent", "Urgent")], default="normal", required=True)
    owner_id = fields.Many2one("res.users", string="Owner")
    due_at = fields.Datetime("Due At")
    is_overdue = fields.Boolean("Overdue", compute="_compute_is_overdue", search="_search_is_overdue")
    state = fields.Selection([("open", "Open"), ("in_progress", "In Progress"),
                              ("done", "Done"), ("cancelled", "Cancelled")],
                             default="open", required=True)
    note = fields.Text("Operational Note")

    @api.depends("due_at", "state")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for task in self:
            task.is_overdue = bool(task.due_at and task.due_at < now
                                   and task.state in ("open", "in_progress"))

    @api.model
    def _search_is_overdue(self, operator, value):
        if operator in ("=", "!=") and isinstance(value, bool):
            match_true = (True == value) if operator == "=" else (True != value)
            match_false = (False == value) if operator == "=" else (False != value)
        elif operator in ("in", "not in") and isinstance(value, Collection) and not isinstance(value, (str, bytes)):
            match_true = (True in value) if operator == "in" else (True not in value)
            match_false = (False in value) if operator == "in" else (False not in value)
        else:
            return NotImplemented
        if match_true and match_false:
            return []
        if not match_true and not match_false:
            return [("id", "=", 0)]
        now = fields.Datetime.now()
        if match_true:
            return [("due_at", "<", now), ("state", "in", ["open", "in_progress"])]
        return ["|", "|", ("due_at", "=", False), ("due_at", ">=", now),
                ("state", "not in", ["open", "in_progress"])]

    @api.constrains("owner_id", "handover_id")
    def _check_owner_company(self):
        for task in self:
            if task.owner_id and (task.company_id not in task.owner_id.company_ids
                                  or not task.owner_id.has_group("point_of_sale.group_pos_user")):
                raise ValidationError(_("Task owner must be a POS user with access to the handover company."))

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            visible_handovers = self.env["cyfr.pos.handover"]._search([], active_test=False)
            domain = Domain(domain) & Domain("handover_id", "in", visible_handovers)
        return super()._search(domain, offset=offset, limit=limit, order=order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        handovers = self.env["cyfr.pos.handover"].browse(self.sudo().mapped("handover_id").ids)
        if handovers._check_access("read"):
            return self, lambda: AccessError(_("The linked handover is no longer readable."))
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
        allowed = {"handover_id", "title", "priority", "owner_id", "due_at", "state", "note"}
        for vals in vals_list:
            if not self.env.su and (set(vals) - allowed or vals.get("state", "open") != "open"):
                raise AccessError(_("Only an open operational task may be created directly."))
            handover = self.env["cyfr.pos.handover"].browse(vals.get("handover_id") or self.env.context.get("default_handover_id"))
            if not handover.exists():
                raise ValidationError(_("Choose a handover for this task."))
            handover._check_operational_scope()
            if not self.env.su and (handover.target_session_id or handover.created_by_id != self.env.user):
                if not self.env.user.has_group("point_of_sale.group_pos_manager"):
                    raise AccessError(_("Only the preparer may add tasks before claim; managers may add later."))
            vals["handover_id"] = handover.id
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            self.check_access("write")
            if set(vals) - {"title", "priority", "owner_id", "due_at", "state", "note"}:
                raise AccessError(_("A task cannot be moved to another handover or company."))
            for task in self:
                task.handover_id._check_operational_scope()
                manager = self.env.user.has_group("point_of_sale.group_pos_manager")
                preparer = task.handover_id.created_by_id == self.env.user and not task.handover_id.target_session_id
                owner = task.owner_id == self.env.user
                if not (manager or preparer or owner):
                    raise AccessError(_("Only the preparer, task owner, or a POS manager may update this task."))
                if not manager and not preparer:
                    if set(vals) - {"state", "note"} or vals.get("state") in ("open", "cancelled"):
                        raise AccessError(_("Only a manager may reassign, cancel, or reopen a claimed task."))
                if not manager and task.state in ("done", "cancelled") and vals.get("state") != task.state:
                    raise AccessError(_("Only a manager may reopen a completed or cancelled task."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Handover tasks are retained for audit and cannot be deleted."))
        return super().unlink()
