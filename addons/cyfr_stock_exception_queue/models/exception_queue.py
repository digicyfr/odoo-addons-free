from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.orm.domains import Domain
from odoo.tools import float_compare, float_is_zero


BATCH_SIZE = 200
MAX_SCOPE_LOCATIONS = 50


class StockExceptionScope(models.Model):
    _name = "cyfr.stock.exception.scope"
    _description = "Stock Exception Scan Scope"
    _order = "company_id, warehouse_id, location_id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, ondelete="cascade", index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, ondelete="cascade", check_company=True)
    location_id = fields.Many2one("stock.location", required=True, ondelete="cascade", check_company=True,
                                  help="Scan this internal location and its internal descendants in the warehouse.")
    zero_days = fields.Integer(string="Zero Days", default=1, required=True,
                               help="Minimum elapsed whole days since the first module scan observed zero free quantity.")
    state = fields.Selection([("idle", "Idle"), ("running", "Scanning")], default="idle", required=True, readonly=True)
    scan_cursor = fields.Integer(readonly=True)
    scan_started_at = fields.Datetime(readonly=True)
    last_batch_at = fields.Datetime(readonly=True)
    last_scan_at = fields.Datetime(readonly=True)
    last_error = fields.Char(readonly=True)
    is_stale = fields.Boolean(compute="_compute_is_stale", string="Stale Results")
    row_ids = fields.One2many("cyfr.stock.exception.row", "scope_id", readonly=True)
    exception_count = fields.Integer(compute="_compute_exception_count")

    _scope_unique = models.Constraint("unique(company_id, warehouse_id, location_id)",
                                      "A scan scope already exists for this warehouse location.")
    _zero_days_positive = models.Constraint("CHECK(zero_days >= 0)", "Zero days cannot be negative.")

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            warehouse_query = self.env["stock.warehouse"]._search([], active_test=False)
            location_query = self.env["stock.location"]._search([], active_test=False)
            domain = (Domain(domain) & Domain("warehouse_id", "in", warehouse_query)
                      & Domain("location_id", "in", location_query))
        return super()._search(domain, offset=offset, limit=limit, order=order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        ids_by_model = {
            "stock.warehouse": set(self.sudo().mapped("warehouse_id").ids),
            "stock.location": set(self.sudo().mapped("location_id").ids),
        }
        for model, ids in ids_by_model.items():
            if self.env[model].browse(ids)._check_access("read"):
                return self, lambda: AccessError(self.env._("A linked warehouse location is not readable."))
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
            allowed = {"name", "active", "company_id", "warehouse_id", "location_id", "zero_days"}
            if any(set(vals) - allowed for vals in vals_list):
                raise AccessError(self.env._("Scan progress is maintained by the module."))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            allowed = {"name", "active", "zero_days", "warehouse_id", "location_id", "company_id"}
            if set(vals) - allowed:
                raise AccessError(self.env._("Scan progress is maintained by the module."))
            if {"warehouse_id", "location_id", "company_id"} & set(vals) and any(scope.row_ids for scope in self):
                raise ValidationError(self.env._("Create a new scope to change a location with scan history."))
        return super().write(vals)

    @api.depends("state", "last_scan_at")
    def _compute_is_stale(self):
        now = fields.Datetime.now()
        for scope in self:
            scope.is_stale = (scope.state == "running" or not scope.last_scan_at
                              or now - scope.last_scan_at > timedelta(hours=36))

    @api.depends("row_ids.is_exception")
    def _compute_exception_count(self):
        grouped = self.env["cyfr.stock.exception.row"]._read_group(
            [("scope_id", "in", self.ids), ("is_exception", "=", True)], ["scope_id"], ["__count"]
        ) if self else []
        counts = {scope.id: count for scope, count in grouped}
        for scope in self:
            scope.exception_count = counts.get(scope.id, 0)

    def _check_scope(self):
        for scope in self:
            if scope.company_id not in self.env.companies:
                raise AccessError(self.env._("The scan company must be active for your user."))
            if scope.warehouse_id.company_id != scope.company_id:
                raise ValidationError(self.env._("The warehouse must belong to the scan company."))
            root = scope.warehouse_id.lot_stock_id
            if (not root or not scope.location_id.active or scope.location_id.usage != "internal"
                    or scope.location_id.company_id != scope.company_id):
                raise ValidationError(self.env._("Select a company-owned internal warehouse location."))
            if not self.env["stock.location"].search_count([
                ("id", "=", scope.location_id.id), ("id", "child_of", root.id),
            ]):
                raise ValidationError(self.env._("The location must be inside the selected warehouse."))
            eligible = self.env["stock.location"].sudo().search([
                ("id", "child_of", scope.location_id.id),
                ("usage", "=", "internal"), ("active", "=", True),
                ("company_id", "=", scope.company_id.id),
            ], limit=MAX_SCOPE_LOCATIONS + 1)
            if len(eligible) > MAX_SCOPE_LOCATIONS:
                raise ValidationError(self.env._("A scan scope may contain at most 50 active internal locations."))
            if scope.zero_days < 0:
                raise ValidationError(self.env._("Zero days cannot be negative."))

    @api.constrains("company_id", "warehouse_id", "location_id", "zero_days")
    def _validate_scope(self):
        self._check_scope()

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(self.env._("Only an inventory administrator may refresh stock exceptions."))
        self.check_access("read")
        self._check_scope()

    def _location_domain(self):
        self.ensure_one()
        return [("location_id", "child_of", self.location_id.id),
                ("location_id.usage", "=", "internal"),
                ("location_id.active", "=", True),
                ("location_id.company_id", "=", self.company_id.id)]

    def _candidate_product_ids(self):
        """Keyset page over quant, orderpoint and prior-snapshot product IDs.

        SQL is used only for this bounded ID discovery. Every row and quantity is
        subsequently read through Odoo stock models under the scan company.
        """
        self.ensure_one()
        root_path = self.location_id.parent_path
        self.env.cr.execute("""
            SELECT product_id FROM (
                SELECT q.product_id FROM stock_quant q
                JOIN stock_location l ON l.id = q.location_id
                WHERE q.owner_id IS NULL AND l.parent_path LIKE %s
                  AND l.usage = 'internal' AND l.active AND l.company_id = %s
                  AND q.product_id > %s
                UNION
                SELECT o.product_id FROM stock_warehouse_orderpoint o
                JOIN stock_location l ON l.id = o.location_id
                WHERE o.active AND o.company_id = %s AND l.parent_path LIKE %s
                  AND l.usage = 'internal' AND l.active AND l.company_id = %s
                  AND o.product_id > %s
                UNION
                SELECT r.product_id FROM cyfr_stock_exception_row r
                WHERE r.scope_id = %s AND r.product_id > %s
            ) candidates ORDER BY product_id LIMIT %s
        """, (root_path + "%", self.company_id.id, self.scan_cursor,
              self.company_id.id, root_path + "%", self.company_id.id,
              self.scan_cursor, self.id, self.scan_cursor, BATCH_SIZE))
        return [row[0] for row in self.env.cr.fetchall()]

    def action_scan_batch(self):
        self.ensure_one()
        self._check_manager()
        self.lock_for_update(allow_referencing=True)
        self.invalidate_recordset(["state", "scan_cursor", "scan_started_at", "company_id", "location_id", "zero_days"])
        self._check_scope()
        now = fields.Datetime.now()
        if self.state == "idle":
            self.sudo().write({"state": "running", "scan_cursor": 0,
                               "scan_started_at": now, "last_error": False})
        product_ids = self._candidate_product_ids()
        if product_ids:
            self._scan_products(product_ids, now)
            self.sudo().write({"scan_cursor": product_ids[-1], "last_batch_at": now})
        else:
            self.sudo().write({"last_batch_at": now})
        if len(product_ids) < BATCH_SIZE:
            # A previous row whose quant and orderpoint disappeared is resolved.
            self.env["cyfr.stock.exception.row"].sudo().search([
                ("scope_id", "=", self.id), ("last_scan_at", "<", self.scan_started_at),
            ]).write({"is_exception": False, "severity": "normal", "first_zero_at": False,
                     "is_persistent_zero": False,
                     "on_hand": 0, "reserved": 0, "free_qty": 0, "minimum_qty": 0,
                     "last_scan_at": now})
            self.sudo().write({"state": "idle", "scan_cursor": 0,
                               "last_scan_at": now})
        return self.env.ref("cyfr_stock_exception_queue.action_stock_exception_row").read()[0]

    def _scan_products(self, product_ids, now):
        self.ensure_one()
        company = self.company_id
        Product = self.env["product.product"].with_company(company)
        products = Product.search([
            ("id", "in", product_ids), ("active", "=", True),
            ("is_storable", "=", True),
        ] + Product._check_company_domain(company))
        valid_ids = set(products.ids)
        quant_groups = self.env["stock.quant"].with_company(company)._read_group(
            self._location_domain() + [("product_id", "in", list(valid_ids)), ("owner_id", "=", False)],
            ["product_id", "location_id"], ["quantity:sum", "reserved_quantity:sum"],
        ) if valid_ids else []
        quantities = {(p.id, l.id): (qty, reserved) for p, l, qty, reserved in quant_groups}
        orderpoints = self.env["stock.warehouse.orderpoint"].with_company(company).search(
            self._location_domain() + [("company_id", "=", company.id),
                                       ("product_id", "in", list(valid_ids))]
        ) if valid_ids else self.env["stock.warehouse.orderpoint"]
        minimums = {(o.product_id.id, o.location_id.id): o.product_min_qty for o in orderpoints}
        keys = set(quantities) | set(minimums)
        rows = self.env["cyfr.stock.exception.row"].sudo().search([
            ("scope_id", "=", self.id), ("product_id", "in", product_ids),
        ])
        Row = self.env["cyfr.stock.exception.row"].sudo()
        old = {(r.product_id.id, r.location_id.id): r for r in rows}
        product_by_id = {p.id: p for p in products}
        to_create = []
        update_groups = {}

        def queue_update(row, vals):
            # Most rows share the same numeric state. One ORM write per value
            # group keeps a 200-product × 50-location batch practical.
            key = tuple(sorted(vals.items()))
            group = update_groups.setdefault(key, {"ids": [], "vals": vals})
            group["ids"].append(row.id)

        for product_id, location_id in sorted(keys | set(old)):
            row = old.get((product_id, location_id))
            if (product_id, location_id) not in keys:
                if row:
                    queue_update(row, {"is_exception": False, "severity": "normal", "first_zero_at": False,
                                       "is_persistent_zero": False,
                                       "on_hand": 0, "reserved": 0, "free_qty": 0, "minimum_qty": 0,
                                       "last_scan_at": now})
                continue
            product = product_by_id[product_id]
            on_hand, reserved = quantities.get((product_id, location_id), (0, 0))
            free = on_hand - reserved
            minimum = minimums.get((product_id, location_id), 0)
            rounding = product.uom_id.rounding
            is_zero = float_is_zero(free, precision_rounding=rounding)
            previously_zero = bool(row and row.first_zero_at)
            first_zero = (row.first_zero_at if previously_zero else now) if is_zero else False
            persistent_zero = bool(is_zero and previously_zero
                                   and now - first_zero >= timedelta(days=self.zero_days))
            if float_compare(free, 0, precision_rounding=rounding) < 0:
                severity = "negative"
            elif (product_id, location_id) in minimums and float_compare(free, minimum, precision_rounding=rounding) < 0:
                severity = "below_min"
            elif persistent_zero:
                severity = "persistent_zero"
            else:
                severity = "normal"
            vals = {"on_hand": on_hand, "reserved": reserved, "free_qty": free,
                    "minimum_qty": minimum, "first_zero_at": first_zero,
                    "is_persistent_zero": persistent_zero,
                    "last_scan_at": now, "severity": severity,
                    "is_exception": severity != "normal"}
            if row:
                queue_update(row, vals)
            else:
                to_create.append({
                    "scope_id": self.id, "company_id": company.id,
                    "product_id": product_id, "location_id": location_id, **vals,
                })
        for group in update_groups.values():
            Row.browse(group["ids"]).write(group["vals"])
        for start in range(0, len(to_create), 500):
            Row.create(to_create[start:start + 500])

    @api.model
    def cron_refresh(self):
        if not self.env.su:
            raise AccessError(self.env._("Only the system scheduler may refresh every scan scope."))
        Scope = self.sudo()
        # New scopes receive one batch first. Thereafter the least recently
        # processed scope runs; a long scan cannot starve other scopes.
        scope = (Scope.search([("active", "=", True), ("last_batch_at", "=", False)], order="id", limit=1)
                 or Scope.search([("active", "=", True)], order="last_batch_at asc, id", limit=1))
        if scope:
            try:
                with self.env.cr.savepoint():
                    scope.with_company(scope.company_id).action_scan_batch()
            except Exception as error:
                scope.sudo().write({"last_error": str(error)[:240], "last_batch_at": fields.Datetime.now()})


class StockExceptionRow(models.Model):
    _name = "cyfr.stock.exception.row"
    _description = "Stock Exception Scan Result"
    _order = "is_exception desc, severity, last_scan_at desc, id"
    _rec_name = "product_id"

    scope_id = fields.Many2one("cyfr.stock.exception.scope", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade", index=True)
    location_id = fields.Many2one("stock.location", required=True, ondelete="cascade", index=True)
    on_hand = fields.Float(readonly=True, digits="Product Unit")
    reserved = fields.Float(readonly=True, digits="Product Unit")
    free_qty = fields.Float(string="Free Quantity", readonly=True, digits="Product Unit")
    minimum_qty = fields.Float(string="Orderpoint Minimum", readonly=True, digits="Product Unit")
    first_zero_at = fields.Datetime(readonly=True)
    is_persistent_zero = fields.Boolean(string="Zero Persisted", readonly=True,
                                         help="Zero free quantity was observed on successive module scans for the configured duration.")
    last_scan_at = fields.Datetime(readonly=True)
    is_stale = fields.Boolean(related="scope_id.is_stale", readonly=True, string="Stale Results")
    severity = fields.Selection([
        ("normal", "Normal"), ("negative", "Negative Free"),
        ("below_min", "Below Minimum"), ("persistent_zero", "Persistent Zero"),
    ], required=True, default="normal", readonly=True)
    is_exception = fields.Boolean(readonly=True, index=True)

    _scope_product_location_unique = models.Constraint("unique(scope_id, product_id, location_id)",
                                                        "A product/location appears once per scan scope.")

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            product_query = self.env["product.product"]._search([], active_test=False)
            location_query = self.env["stock.location"]._search([], active_test=False)
            scope_query = self.env["cyfr.stock.exception.scope"]._search([], active_test=False)
            domain = (Domain(domain) & Domain("product_id", "in", product_query)
                      & Domain("location_id", "in", location_query)
                      & Domain("scope_id", "in", scope_query))
        return super()._search(domain, offset=offset, limit=limit, order=order,
                               active_test=active_test, bypass_access=bypass_access)

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        ids_by_model = {
            "product.product": set(self.sudo().mapped("product_id").ids),
            "stock.location": set(self.sudo().mapped("location_id").ids),
            "cyfr.stock.exception.scope": set(self.sudo().mapped("scope_id").ids),
        }
        for model, ids in ids_by_model.items():
            if self.env[model].browse(ids)._check_access("read"):
                return self, lambda: AccessError(self.env._("A linked stock record is not readable."))
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

    def action_open_orderpoints(self):
        self.ensure_one()
        self.check_access("read")
        return {"type": "ir.actions.act_window", "name": self.env._("Replenishment Rules"),
                "res_model": "stock.warehouse.orderpoint", "view_mode": "list,form",
                "domain": [("company_id", "=", self.company_id.id),
                           ("product_id", "=", self.product_id.id),
                           ("location_id", "=", self.location_id.id)]}
