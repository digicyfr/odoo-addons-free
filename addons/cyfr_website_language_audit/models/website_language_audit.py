"""Read-only review of selected, published website pages.

The scan deliberately keeps only issue metadata and hashes. Page architecture
and localized field values are read from Odoo and never copied into this model.
"""

import logging
import time

from lxml import etree
from psycopg2.errors import LockNotAvailable

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import SQL
from odoo.tools.translate import _

from . import static_analysis


_logger = logging.getLogger(__name__)
MAX_CANDIDATES = 600
MAX_PAGES = 200
MAX_ISSUES = 2000
MAX_SECONDS = 30

# A global page is no longer the effective page for a website as soon as a
# website-specific page with the same key or URL exists, even if that local
# page is unpublished. Keep this check on live records, not scan snapshots.
LOCAL_OVERRIDE_EXISTS = """
EXISTS (
    SELECT 1
      FROM website_page AS global_page
      JOIN ir_ui_view AS global_view ON global_view.id = global_page.view_id
      JOIN ir_ui_view AS local_view
        ON local_view.website_id = cyfr_website_audit_issue.website_id
      JOIN website_page AS local_page ON local_page.view_id = local_view.id
     WHERE global_page.id = cyfr_website_audit_issue.page_id
       AND global_view.website_id IS NULL
       AND local_view.active
       AND local_page.url IS NOT NULL AND local_page.url != ''
       AND (local_view.key = global_view.key OR local_page.url = global_page.url)
)
"""


class WebsiteAuditRun(models.Model):
    _name = "cyfr.website.audit.run"
    _description = "Website Language Audit Run"
    _order = "id desc"

    name = fields.Char(compute="_compute_name", store=True)
    website_id = fields.Many2one("website", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(
        "res.company", related="website_id.company_id", store=True, readonly=True, index=True
    )
    lang_id = fields.Many2one("res.lang", string="Target Language", required=True)
    user_id = fields.Many2one(
        "res.users", string="Started by", required=True, default=lambda self: self.env.user,
        readonly=True, ondelete="restrict",
    )
    ignored_terms = fields.Char(
        string="Exact terms to ignore",
        help="Comma-separated short names or brands that may stay identical between languages.",
    )
    state = fields.Selection(
        [("draft", "Ready"), ("done", "Done"), ("truncated", "Truncated"), ("failed", "Failed")],
        required=True, default="draft", readonly=True,
    )
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    total_count = fields.Integer(string="Pages selected", readonly=True)
    processed_count = fields.Integer(string="Pages checked", readonly=True)
    issue_count = fields.Integer(string="Issues", readonly=True)
    failure_count = fields.Integer(string="Pages that could not be parsed", readonly=True)
    issue_ids = fields.One2many("cyfr.website.audit.issue", "run_id", readonly=True)

    @api.depends("website_id", "lang_id")
    def _compute_name(self):
        for run in self:
            run.name = "%s · %s" % (
                run.website_id.name or _("Website"), run.lang_id.name or _("Language")
            )

    @api.constrains("website_id", "lang_id", "ignored_terms")
    def _check_scope(self):
        for run in self:
            if run.website_id and run.lang_id:
                if run.lang_id == run.website_id.default_lang_id:
                    raise ValidationError(_("Choose a non-default language for the selected website."))
                if run.lang_id not in run.website_id.language_ids:
                    raise ValidationError(_("The target language must be enabled on the selected website."))
            if len(run.ignored_terms or "") > 200:
                raise ValidationError(_("The ignored-terms list is limited to 200 characters."))

    @api.model_create_multi
    def create(self, vals_list):
        allowed = {"website_id", "lang_id", "ignored_terms"}
        if any(set(vals) - allowed for vals in vals_list):
            raise AccessError(_("Only website, language, and ignored terms can be set on a new audit."))
        for vals in vals_list:
            website = self.env["website"].browse(vals.get("website_id"))
            if website.exists() and website.company_id not in self.env.companies:
                raise AccessError(_("The selected website is outside your allowed companies."))
        runs = super().create(vals_list)
        return runs

    def write(self, vals):
        allowed = {"website_id", "lang_id", "ignored_terms"}
        if set(vals) - allowed or any(run.state != "draft" for run in self):
            raise AccessError(_("Completed audits cannot be edited."))
        if "website_id" in vals:
            website = self.env["website"].browse(vals["website_id"])
            if website.exists() and website.company_id not in self.env.companies:
                raise AccessError(_("The selected website is outside your allowed companies."))
        return super().write(vals)

    def unlink(self):
        if any(run.state not in ("draft", "done", "truncated", "failed") for run in self):
            raise AccessError(_("This audit cannot be removed while it is running."))
        return super().unlink()

    def _check_scan_permission(self):
        self.ensure_one()
        self.check_access("write")
        if not self.env.user.has_group("website.group_website_designer"):
            raise AccessError(_("Only website designers can run an audit."))
        if self.company_id not in self.env.companies:
            raise AccessError(_("The selected website is outside your allowed companies."))
        if self.lang_id not in self.website_id.language_ids or self.lang_id == self.website_id.default_lang_id:
            raise ValidationError(_("Choose an enabled non-default website language."))

    def action_open_issues(self):
        self.ensure_one()
        self.check_access("read")
        action = self.env["ir.actions.actions"]._for_xml_id(
            "cyfr_website_language_audit.action_website_audit_issue"
        )
        action["domain"] = [("run_id", "=", self.id)]
        return action

    def _pages_for_scan(self):
        """Apply website-specific overrides before considering publication."""
        self.ensure_one()
        Page = self.env["website.page"].with_context(website_id=self.website_id.id)
        specific = Page.search(
            [("website_id", "=", self.website_id.id), ("url", "!=", False),
             ("url", "!=", ""), ("active", "=", True)],
            order="id", limit=MAX_CANDIDATES + 1,
        )
        # If the override set is incomplete, a global page could wrongly be
        # included when its unpublished website-specific copy lies beyond the cap.
        if len(specific) > MAX_CANDIDATES:
            return [], 0, True
        generic = Page.search(
            [("website_id", "=", False), ("url", "!=", False), ("url", "!=", "")],
            order="id", limit=MAX_CANDIDATES + 1,
        )
        candidate_bound = len(generic) > MAX_CANDIDATES
        candidates = specific + generic[:MAX_CANDIDATES]
        specific_keys = {page.key for page in candidates if page.website_id and page.key}
        specific_urls = {page.url for page in candidates if page.website_id}
        now = fields.Datetime.now()
        pages = []
        for page in candidates:
            if not page.website_id and (page.key in specific_keys or page.url in specific_urls):
                continue
            if not page.is_published or page.visibility or not page.view_id.active:
                continue
            if page.date_publish and page.date_publish > now:
                continue
            pages.append(page)
        pages.sort(key=lambda page: (page.url, page.id))
        return pages[:MAX_PAGES], len(pages), candidate_bound or len(pages) > MAX_PAGES

    def _seo_issues(self, page):
        """Read stored translations, since ordinary translated reads fall back."""
        view = page.view_id
        source_view = view.with_context(lang=self.website_id.default_lang_id.code)
        findings = []
        for field_name, issue_type in (
            ("website_meta_title", "missing_meta_title"),
            ("website_meta_description", "missing_meta_description"),
        ):
            stored = view._fields[field_name]._get_stored_translations(view) or {}
            if not (stored.get(self.lang_id.code) or "").strip():
                findings.append((
                    issue_type, "info", field_name,
                    static_analysis.digest(static_analysis.normalize(source_view[field_name])),
                ))
        return findings

    def _analyze_page(self, page):
        view = page.view_id
        source = view.with_context(lang=self.website_id.default_lang_id.code).arch_db
        target = view.with_context(lang=self.lang_id.code).arch_db
        ignored = [self.website_id.name, self.company_id.name]
        ignored.extend((self.ignored_terms or "").split(","))
        return self._seo_issues(page) + static_analysis.compare_arches(source, target, ignored)

    def action_scan(self):
        self.ensure_one()
        self._check_scan_permission()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "SELECT id FROM cyfr_website_audit_run WHERE id = %s FOR UPDATE NOWAIT", (self.id,)
                )
        except LockNotAvailable as exc:
            raise UserError(_("This audit is already being scanned.")) from exc
        self.invalidate_recordset(["state"])
        if self.state != "draft":
            raise UserError(_("Create a new audit to scan again."))

        started = fields.Datetime.now()
        super().write({"started_at": started})
        processed = 0
        failed = 0
        issue_vals = []
        total = 0
        truncated = False
        try:
            with self.env.cr.savepoint():
                pages, total, truncated = self._pages_for_scan()
                deadline = time.monotonic() + MAX_SECONDS
                for page in pages:
                    if time.monotonic() >= deadline:
                        truncated = True
                        break
                    try:
                        findings = self._analyze_page(page)
                    except static_analysis.AnalysisLimit:
                        truncated = True
                        break
                    except (static_analysis.UnsafeArchitecture, etree.XMLSyntaxError, ValueError):
                        failed += 1
                        continue
                    remaining = MAX_ISSUES - len(issue_vals)
                    if len(findings) > remaining:
                        findings = findings[:remaining]
                        truncated = True
                    issue_vals.extend({
                        "run_id": self.id, "page_id": page.id, "page_url": page.url,
                        "issue_type": issue_type, "severity": severity,
                        "node_ref": node_ref, "source_hash": source_hash,
                    } for issue_type, severity, node_ref, source_hash in findings)
                    processed += 1
                    if truncated or len(issue_vals) >= MAX_ISSUES:
                        truncated = True
                        break
                if issue_vals:
                    self.env["cyfr.website.audit.issue"]._create_for_scan(issue_vals)
        except Exception:
            _logger.exception("Website language audit %s failed", self.id)
            super().write({
                "state": "failed", "completed_at": fields.Datetime.now(),
                "processed_count": 0, "total_count": total, "issue_count": 0,
                "failure_count": 1,
            })
            return True

        super().write({
            "state": "failed" if failed else "truncated" if truncated else "done",
            "completed_at": fields.Datetime.now(),
            "processed_count": processed, "total_count": total,
            "issue_count": len(issue_vals), "failure_count": failed,
        })
        return True


class WebsiteAuditIssue(models.Model):
    _name = "cyfr.website.audit.issue"
    _description = "Website Language Audit Issue"
    _order = "run_id desc, page_url, id"

    run_id = fields.Many2one(
        "cyfr.website.audit.run", required=True, ondelete="cascade", index=True, readonly=True
    )
    website_id = fields.Many2one(
        "website", related="run_id.website_id", store=True, readonly=True, index=True
    )
    company_id = fields.Many2one(
        "res.company", related="run_id.company_id", store=True, readonly=True, index=True
    )
    lang_id = fields.Many2one("res.lang", related="run_id.lang_id", store=True, readonly=True)
    page_id = fields.Many2one(
        "website.page", required=True, ondelete="cascade", index=True, readonly=True
    )
    page_url = fields.Char(string="Page URL", required=True, readonly=True)
    issue_type = fields.Selection(
        [
            ("missing_meta_title", "No localized SEO title"),
            ("missing_meta_description", "No localized SEO description"),
            ("missing_alt", "Image without a description"),
            ("identical_text", "Identical static text — review"),
        ], required=True, readonly=True,
    )
    severity = fields.Selection(
        [("info", "Review"), ("warning", "Attention")], required=True, readonly=True
    )
    node_ref = fields.Char(string="Field or node", required=True, readonly=True)
    source_hash = fields.Char(string="Source SHA-256", size=64, readonly=True)
    page_currently_public = fields.Boolean(
        compute="_compute_page_currently_public", search="_search_page_currently_public"
    )

    def _hidden_by_local_override(self):
        if not self:
            return self
        self.env.cr.execute(
            f"SELECT id FROM {self._table} WHERE id IN %s AND {LOCAL_OVERRIDE_EXISTS}",
            (tuple(self.ids),),
        )
        return self.browse([row[0] for row in self.env.cr.fetchall()])

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        query = super()._search(
            domain, offset=offset, limit=limit, order=order,
            active_test=active_test, bypass_access=bypass_access,
        )
        if not self.env.su and not bypass_access:
            query.add_where(SQL("NOT " + LOCAL_OVERRIDE_EXISTS))
        return query

    def _check_access(self, operation):
        result = super()._check_access(operation)
        if result or operation != "read" or not self or self.env.su:
            return result
        if hidden := self._hidden_by_local_override():
            return hidden, lambda: AccessError(_("This page is no longer effective for this website."))
        return None

    def _compute_page_currently_public(self):
        now = fields.Datetime.now()
        overridden = set(self._hidden_by_local_override().ids)
        for issue in self:
            page = issue.page_id
            issue.page_currently_public = bool(
                issue.id not in overridden and page.is_published and page.active and not page.visibility
                and (not page.date_publish or page.date_publish <= now)
            )

    @api.model
    def _search_page_currently_public(self, operator, value):
        if not (
            (operator == "=" and value is True)
            or (operator == "in" and list(value) == [True])
        ):
            return NotImplemented
        return [
            ("page_id.is_published", "=", True),
            ("page_id.active", "=", True),
            ("page_id.visibility", "=", False),
            "|", ("page_id.date_publish", "=", False),
            ("page_id.date_publish", "<=", fields.Datetime.now()),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_("Audit issues are created only by a scan."))

    @api.model_create_multi
    def _create_for_scan(self, vals_list):
        return super().create(vals_list)

    def action_open_page(self):
        self.ensure_one()
        self.check_access("read")
        if self._hidden_by_local_override():
            raise AccessError(_("This page is no longer effective for this website."))
        if not self.env.user.has_group("website.group_website_designer"):
            raise AccessError(_("Only website designers can open the page editor."))
        self.page_id.check_access("read")
        if self.page_id.website_id and self.page_id.website_id != self.website_id:
            raise AccessError(_("The page is outside this audit's website."))
        if (
            not self.page_id.is_published or not self.page_id.active or self.page_id.visibility
            or (self.page_id.date_publish and self.page_id.date_publish > fields.Datetime.now())
        ):
            raise AccessError(_("This page is no longer public."))
        # A full native action navigation lets Odoo initialize its preview
        # iframe before entering edit mode (the in-place action can race it).
        action_url = self.env["website"].get_client_action_url(self.page_id.url, True)
        return {
            "type": "ir.actions.act_url",
            "url": f"{action_url}&website_id={self.website_id.id}",
            "target": "self",
        }
