from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.orm.domains import Domain


ISSUE_CODES = (
    "missing_internal_reference",
    "missing_barcode",
    "non_positive_sale_price",
    "generic_or_missing_category",
    "missing_image",
)
BATCH_SIZE = 200


class ProductHealthPolicy(models.Model):
    _name = "cyfr.product.health.policy"
    _description = "Product Data Health Policy"
    _order = "company_id desc, categ_id desc, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", ondelete="cascade", index=True)
    categ_id = fields.Many2one("product.category", string="Applies to Category", ondelete="cascade")
    check_internal_reference = fields.Boolean(default=True)
    check_barcode = fields.Boolean(default=True)
    check_sale_price = fields.Boolean(default=True)
    check_category = fields.Boolean(default=True)
    check_image = fields.Boolean(default=True)
    generic_category_ids = fields.Many2many(
        "product.category", string="Categories Considered Generic",
        help="Select placeholder categories to flag. An empty selection flags only products with no category.",
    )

    @api.constrains("active", "company_id", "categ_id")
    def _check_unique_active_scope(self):
        for policy in self.filtered("active"):
            peers = self.search([
                ("id", "!=", policy.id),
                ("active", "=", True),
                ("company_id", "=", policy.company_id.id or False),
                ("categ_id", "=", policy.categ_id.id or False),
            ], limit=1)
            if peers:
                raise ValidationError(self.env._("Only one active policy is allowed for each company/category scope."))


class ProductHealthScan(models.Model):
    _name = "cyfr.product.health.scan"
    _description = "Product Data Health Scan"
    _order = "create_date desc, id desc"

    name = fields.Char(default=lambda self: self.env._("New scan"), required=True, readonly=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)
    state = fields.Selection([("draft", "Ready"), ("running", "Running"), ("done", "Complete")], default="draft", required=True, readonly=True)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    last_product_id = fields.Integer(readonly=True)
    total_count = fields.Integer(readonly=True)
    processed_count = fields.Integer(readonly=True)
    issue_count = fields.Integer(readonly=True)
    is_current = fields.Boolean(default=False, readonly=True, index=True)
    issue_ids = fields.One2many("cyfr.product.health.issue", "scan_id", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group("product.group_product_manager") and not self.env.su:
            raise AccessError(self.env._("Only a product manager may create data health scans."))
        for vals in vals_list:
            if set(vals) - {"company_id"}:
                raise AccessError(self.env._("Scan state and ownership are assigned by the module."))
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if company not in self.env.companies:
                raise AccessError(self.env._("The scan company must be one of your active companies."))
        return super().create(vals_list)

    def _check_scan_permission(self):
        if not self.env.user.has_group("product.group_product_manager"):
            raise AccessError(self.env._("Only a product manager may run data health scans."))
        for scan in self:
            if scan.company_id not in self.env.companies:
                raise AccessError(self.env._("The scan company must be one of your active companies."))

    def _product_domain(self):
        self.ensure_one()
        return [
            ("active", "=", True),
            ("product_tmpl_id.active", "=", True),
            ("sale_ok", "=", True),
            ("product_tmpl_id.company_id", "in", [False, self.company_id.id]),
        ]

    def _policy_for(self, product, policies):
        self.ensure_one()
        category_id = product.categ_id.id
        for company_id, categ_id in (
            (self.company_id.id, category_id),
            (self.company_id.id, False),
            (False, category_id),
            (False, False),
        ):
            policy = policies.get((company_id, categ_id))
            if policy:
                return policy
        return self.env["cyfr.product.health.policy"]

    @staticmethod
    def _issue_codes_for(product, policy):
        codes = []
        if policy.check_internal_reference and not product.default_code:
            codes.append("missing_internal_reference")
        if policy.check_barcode and not product.barcode:
            codes.append("missing_barcode")
        if policy.check_sale_price and product.product_tmpl_id.list_price <= 0:
            codes.append("non_positive_sale_price")
        if policy.check_category and (
            not product.categ_id or product.categ_id in policy.generic_category_ids
        ):
            codes.append("generic_or_missing_category")
        if policy.check_image and not product.image_128:
            codes.append("missing_image")
        return codes

    def action_scan_batch(self):
        self.ensure_one()
        self._check_scan_permission()
        self.lock_for_update(allow_referencing=True)
        self.invalidate_recordset(["state", "last_product_id", "processed_count", "issue_count", "company_id"])
        if self.state == "done":
            raise ValidationError(self.env._("This scan is complete. Create a new scan to refresh results."))

        products = self.env["product.product"].with_company(self.company_id)
        domain = self._product_domain()
        if self.state == "draft":
            self.sudo().write({
                "name": self.env._("Product scan %(company)s — %(time)s", company=self.company_id.name, time=fields.Datetime.now()),
                "started_at": fields.Datetime.now(),
                "total_count": products.search_count(domain),
                "state": "running",
            })

        policy_records = self.env["cyfr.product.health.policy"].search([
            ("active", "=", True),
            ("company_id", "in", [False, self.company_id.id]),
        ])
        policies = {(p.company_id.id or False, p.categ_id.id or False): p for p in policy_records}
        batch = products.search(domain + [("id", ">", self.last_product_id)], order="id", limit=BATCH_SIZE)
        values = []
        for product in batch:
            policy = self._policy_for(product, policies)
            if not policy:
                continue
            codes = self._issue_codes_for(product, policy)
            if codes:
                values.append({
                    "scan_id": self.id,
                    "company_id": self.company_id.id,
                    "product_id": product.id,
                    "policy_id": policy.id,
                    "issue_codes": ",".join(codes),
                })
        if values:
            self.env["cyfr.product.health.issue"].sudo().create(values)

        self.sudo().write({
            "last_product_id": batch[-1].id if batch else self.last_product_id,
            "processed_count": self.processed_count + len(batch),
            "issue_count": self.issue_count + len(values),
        })
        if len(batch) < BATCH_SIZE:
            # Two different scans for the same company can finish concurrently.
            # Serialize publication on their shared company row before finding
            # and retiring the previously current snapshot.
            self.company_id.lock_for_update(allow_referencing=True)
            previous = self.search([
                ("company_id", "=", self.company_id.id),
                ("is_current", "=", True),
                ("id", "!=", self.id),
            ])
            previous.sudo().write({"is_current": False})
            self.sudo().write({"state": "done", "completed_at": fields.Datetime.now(), "is_current": True})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_issues(self):
        self.ensure_one()
        self.check_access("read")
        action = self.env.ref("cyfr_product_data_health.action_product_health_issue").read()[0]
        action["domain"] = [("scan_id", "=", self.id)]
        return action

    def action_delete_old_scan(self):
        self.ensure_one()
        self._check_scan_permission()
        if self.state != "done" or self.is_current:
            raise ValidationError(self.env._("Only a completed, non-current scan can be deleted."))
        self.sudo().unlink()
        return self.env.ref("cyfr_product_data_health.action_product_health_scan").read()[0]


class ProductHealthIssue(models.Model):
    _name = "cyfr.product.health.issue"
    _description = "Product Data Health Issue"
    _order = "id desc"
    _rec_name = "product_id"

    scan_id = fields.Many2one("cyfr.product.health.scan", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one("res.company", required=True, ondelete="cascade", index=True, readonly=True)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade", index=True)
    categ_id = fields.Many2one("product.category", related="product_id.categ_id", store=True, index=True, readonly=True)
    policy_id = fields.Many2one("cyfr.product.health.policy", required=True, ondelete="restrict")
    issue_codes = fields.Char(required=True, readonly=True, help="Stable comma-separated issue codes for CSV export.")
    issue_summary = fields.Char(compute="_compute_issue_summary", string="Issues")
    scanned_at = fields.Datetime(related="scan_id.completed_at", readonly=True)
    is_current = fields.Boolean(related="scan_id.is_current", readonly=True, store=True)

    _scan_product_uniq = models.Constraint(
        "unique(scan_id, product_id)",
        "A product may appear only once in a scan.",
    )

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        if not self.env.su and not bypass_access:
            # A lazy subquery retains the caller's product ACL and record rules, including
            # rules added by other modules. Never materialize an unbounded ID list.
            product_query = self.env["product.product"]._search([], active_test=False)
            domain = Domain(domain) & Domain("product_id", "in", product_query)
        return super()._search(
            domain, offset=offset, limit=limit, order=order,
            active_test=active_test, bypass_access=bypass_access,
        )

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        issue_products = {issue.id: issue.sudo().product_id.id for issue in self}
        products = self.env["product.product"].browse(set(issue_products.values()))
        product_result = products._check_access("read")
        if product_result:
            forbidden_ids = set(product_result[0].ids)
            forbidden = self.browse([
                issue_id for issue_id, product_id in issue_products.items()
                if product_id in forbidden_ids
            ])
            return forbidden, lambda: AccessError(self.env._("The linked product is not readable."))
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

    @api.depends("issue_codes")
    def _compute_issue_summary(self):
        labels = {
            "missing_internal_reference": self.env._("Missing internal reference"),
            "missing_barcode": self.env._("Missing barcode"),
            "non_positive_sale_price": self.env._("Non-positive sale price"),
            "generic_or_missing_category": self.env._("Generic or missing category"),
            "missing_image": self.env._("Missing image"),
        }
        for issue in self:
            issue.issue_summary = ", ".join(labels.get(code, code) for code in (issue.issue_codes or "").split(",") if code)

    @api.constrains("issue_codes")
    def _check_issue_codes(self):
        for issue in self:
            codes = issue.issue_codes.split(",")
            if not codes or any(code not in ISSUE_CODES for code in codes) or len(codes) != len(set(codes)):
                raise ValidationError(self.env._("Invalid product health issue codes."))

    def action_open_product(self):
        self.ensure_one()
        self.check_access("read")
        self.product_id.check_access("read")
        return {
            "type": "ir.actions.act_window",
            "res_model": "product.product",
            "res_id": self.product_id.id,
            "view_mode": "form",
            "target": "current",
        }
