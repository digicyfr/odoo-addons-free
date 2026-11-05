from hashlib import sha256
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import config

from ..models import static_analysis, website_language_audit


@tagged("post_install", "-at_install")
class TestWebsiteLanguageAudit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.en = cls.env.ref("base.lang_en")
        cls.pl = cls.env.ref("base.lang_pl")
        if not cls.pl.active:
            cls.env["res.lang"]._activate_lang("pl_PL")
        cls.website = cls.env.ref("website.default_website")
        cls.website.write({
            "default_lang_id": cls.en.id,
            "language_ids": [Command.link(cls.pl.id)],
        })
        cls.second_website = cls.env["website"].create({
            "name": "Audit Test Second Website",
            "company_id": cls.env.company.id,
            "default_lang_id": cls.en.id,
            "language_ids": [Command.set([cls.en.id, cls.pl.id])],
        })

    def _page(self, slug, body, website=None, published=True, key=None, **seo):
        website = self.website if website is None else website
        key = key or "cyfr_website_language_audit.test_%s" % slug.replace("-", "_")
        view = self.env["ir.ui.view"].create({
            "name": "Audit Test %s" % slug, "type": "qweb", "key": key,
            "website_id": website.id if website else False,
            "arch_db": '<t t-name="%s"><main>%s</main></t>' % (key, body),
            **seo,
        })
        page = self.env["website.page"].create({
            "view_id": view.id, "url": "/cyfr-audit-test-%s" % slug,
            "is_published": published,
        })
        return page

    def _translate_arch(self, page, translations):
        view = page.view_id
        source = view.with_context(lang="en_US").arch_db
        terms = view._fields["arch_db"].get_trans_terms(source)
        mapping = {
            sha256(term.encode()).hexdigest(): translations[term]
            for term in terms if term in translations
        }
        view._update_field_translations(
            "arch_db", {"pl_PL": mapping},
            lambda term: sha256(term.encode()).hexdigest(), source_lang="en_US",
        )

    def _run(self, website=None, ignored_terms=""):
        return self.env["cyfr.website.audit.run"].create({
            "website_id": (website or self.website).id,
            "lang_id": self.pl.id,
            "ignored_terms": ignored_terms,
        })

    def test_translated_arch_fallback_and_issue_classes(self):
        page = self._page(
            "translation", "<h1>Original published headline</h1>"
            "<p>Review this identical sentence.</p>"
            '<img src="/web/static/img/placeholder.png" alt="A useful description"/>'
            '<img src="/web/static/img/placeholder.png"/>'
            '<img src="/web/static/img/placeholder.png" alt=""/>'
            '<p t-if="condition">Dynamic sentence must be skipped.</p>',
            website_meta_title="Original SEO title",
            website_meta_description="Original SEO description",
        )
        self._translate_arch(page, {
            "Original published headline": "Przetłumaczony nagłówek strony",
            "A useful description": "Przydatny opis",
        })
        page.view_id.with_context(lang="pl_PL").write({"website_meta_title": "Polski tytuł"})
        self.assertIn("Original published headline", page.with_context(lang="en_US").arch_db)
        self.assertIn("Przetłumaczony nagłówek strony", page.with_context(lang="pl_PL").arch_db)

        run = self._run()
        run.action_scan()
        self.assertEqual(run.state, "done")
        rows = run.issue_ids.filtered(lambda issue: issue.page_id == page)
        self.assertEqual(len(rows.filtered(lambda issue: issue.issue_type == "identical_text")), 1)
        self.assertEqual(len(rows.filtered(lambda issue: issue.issue_type == "missing_alt")), 1)
        self.assertEqual(len(rows.filtered(lambda issue: issue.issue_type == "missing_meta_description")), 1)
        self.assertFalse(rows.filtered(lambda issue: issue.issue_type == "missing_meta_title"))
        self.assertFalse(any("Dynamic" in issue.node_ref for issue in rows))
        self.assertTrue(all(len(issue.source_hash) == 64 for issue in rows))

    def test_website_override_publication_and_language_scope(self):
        first = self._page("first-site", "<p>First site only, published content.</p>")
        second = self._page(
            "second-site", "<p>Second site only, published content.</p>", website=self.second_website,
        )
        unpublished = self._page(
            "unpublished", "<p>Never show this unpublished page.</p>",
            website=self.second_website, published=False,
        )
        shared_key = "cyfr_website_language_audit.global_override"
        generic = self._page(
            "global-override", "<p>Global page hidden by local override.</p>",
            website=self.env["website"], key=shared_key,
        )
        self._page(
            "local-override", "<p>Local page is also unpublished.</p>",
            website=self.second_website, published=False, key=shared_key,
        )
        inactive_override = self._page(
            "inactive-override", "<p>Inactive local page is not an override.</p>",
            website=self.website, published=False, key=shared_key,
        )
        inactive_override.view_id.active = False
        first_run = self._run()
        second_run = self._run(self.second_website)
        first_run.action_scan()
        second_run.action_scan()
        self.assertIn(first.id, first_run.issue_ids.mapped("page_id").ids)
        self.assertNotIn(second.id, first_run.issue_ids.mapped("page_id").ids)
        self.assertIn(second.id, second_run.issue_ids.mapped("page_id").ids)
        self.assertNotIn(first.id, second_run.issue_ids.mapped("page_id").ids)
        self.assertNotIn(unpublished.id, second_run.issue_ids.mapped("page_id").ids)
        self.assertNotIn(generic.id, second_run.issue_ids.mapped("page_id").ids)
        self.assertIn(generic.id, first_run.issue_ids.mapped("page_id").ids)
        self.assertEqual(len(first_run.issue_ids.filtered(lambda row: row.page_id == generic and row.issue_type == "identical_text")), 1)

    def test_read_only_roles_and_company_scope(self):
        page = self._page("acl", "<p>Published content for role testing.</p>")
        shared_key = "cyfr_website_language_audit.post_scan_override"
        global_page = self._page(
            "post-scan-override", "<p>Global content before a local override exists.</p>",
            website=self.env["website"], key=shared_key,
        )
        run = self._run()
        run.action_scan()
        global_issue = run.issue_ids.filtered(lambda issue: issue.page_id == global_page)[:1]
        self.assertTrue(global_issue)
        editor_action = global_issue.action_open_page()
        editor_url = urlparse(editor_action["url"])
        editor_query = parse_qs(editor_url.query)
        self.assertEqual(editor_action["type"], "ir.actions.act_url")
        self.assertEqual(editor_action["target"], "self")
        self.assertEqual(editor_url.path, "/odoo/action-website.website_preview")
        self.assertEqual(editor_query["path"], [global_page.url])
        self.assertEqual(editor_query["enable_editor"], ["1"])
        self.assertEqual(editor_query["website_id"], [str(self.website.id)])
        reader = self.env["res.users"].create({
            "name": "Audit Restricted Editor", "login": "audit-restricted-editor-test",
            "company_id": self.env.company.id,
            "company_ids": [Command.link(self.env.company.id)],
            "group_ids": [
                Command.link(self.env.ref("website.group_website_restricted_editor").id),
                Command.link(self.env.ref("base.group_allow_export").id),
            ],
        })
        self.assertTrue(self.env["cyfr.website.audit.run"].with_user(reader).search([("id", "=", run.id)]))
        self.assertTrue(self.env["cyfr.website.audit.issue"].with_user(reader).search_read(
            [("run_id", "=", run.id), ("page_id", "=", page.id)], ["page_url", "issue_type"]
        ))
        self.assertTrue(global_issue.with_user(reader).read(["page_url"]))
        local_override = self._page(
            "post-scan-override", "<p>Unpublished local replacement.</p>",
            website=self.website, published=False, key=shared_key,
        )
        self.assertFalse(self.env["cyfr.website.audit.issue"].with_user(reader).search([
            ("id", "=", global_issue.id),
        ]))
        self.assertFalse(self.env["cyfr.website.audit.issue"].with_user(reader).search_read(
            [("id", "=", global_issue.id)], ["page_url"],
        ))
        with self.assertRaises(AccessError):
            global_issue.with_user(reader).read(["page_url"])
        with self.assertRaises(AccessError):
            global_issue.with_user(reader).export_data(["page_url"])
        with self.assertRaises(AccessError):
            global_issue.action_open_page()
        local_override.view_id.active = False
        self.assertTrue(self.env["cyfr.website.audit.issue"].with_user(reader).search([
            ("id", "=", global_issue.id),
        ]))
        second_page = self._page(
            "same-company-reader", "Published content on another website.",
            website=self.second_website,
        )
        second_run = self._run(self.second_website)
        second_run.action_scan()
        self.assertTrue(self.env["cyfr.website.audit.issue"].with_user(reader).search([
            ("run_id", "=", second_run.id), ("page_id", "=", second_page.id),
        ]))
        page.date_publish = fields.Datetime.now() + timedelta(days=1)
        self.assertFalse(self.env["cyfr.website.audit.issue"].with_user(reader).search(
            [("run_id", "=", run.id), ("page_id", "=", page.id)]
        ))
        page.date_publish = False
        with self.assertRaises(AccessError):
            self._run().with_user(reader).action_scan()
        with self.assertRaises(AccessError):
            self.env["cyfr.website.audit.issue"].create({})
        with self.assertRaises(AccessError):
            run.issue_ids.filtered(lambda issue: issue.page_id == page)[:1].with_user(reader).action_open_page()
        foreign = self.env["res.company"].create({"name": "Audit Foreign Company"})
        foreign_website = self.env["website"].create({
            "name": "Audit Foreign Website", "company_id": foreign.id,
            "default_lang_id": self.en.id,
            "language_ids": [Command.set([self.en.id, self.pl.id])],
        })
        with self.assertRaises(AccessError):
            self.env["cyfr.website.audit.run"].with_user(reader).create({
                "website_id": foreign_website.id, "lang_id": self.pl.id,
            })
        self.assertFalse(self.env["cyfr.website.audit.run"].with_user(reader).search(
            [("website_id", "=", foreign_website.id)]
        ))

    def test_repeat_scope_and_data_minimization(self):
        page = self._page("repeat", "<p>Synthetic page body that must never be copied.</p>")
        run = self._run(ignored_terms="Synthetic page body that must never be copied.")
        run.action_scan()
        self.assertEqual(run.state, "done")
        self.assertFalse(run.issue_ids.filtered(lambda row: row.page_id == page and row.issue_type == "identical_text"))
        with self.assertRaises(UserError):
            run.action_scan()
        with self.assertRaises(AccessError):
            run.write({"state": "draft"})
        with self.assertRaises(AccessError):
            self.env["cyfr.website.audit.run"].create({
                "website_id": self.website.id, "lang_id": self.pl.id, "state": "done",
            })
        with self.assertRaises(ValidationError):
            self.env["cyfr.website.audit.run"].create({
                "website_id": self.website.id, "lang_id": self.en.id,
            })
        for row in run.issue_ids:
            values = row.read(["page_url", "issue_type", "node_ref", "source_hash"])[0]
            self.assertNotIn("Synthetic page body", repr(values))

    def test_safe_parser_and_decorative_exception(self):
        source = (
            '<t t-name="test"><t t-call="website.layout"><main><p>Identical static sentence.</p>'
            '<p t-if="condition">Dynamic sentence is ignored.</p>'
            '<t t-call="some.template"><p>Called content is ignored.</p></t>'
            '<img src="/a"/><img src="/b" alt=""/>'
            '<img src="/c" role="presentation"/>'
            '<img src="/generic" alt="image"/>'
            '<img src="/d" aria-hidden="true"/></main></t></t>'
        )
        results = static_analysis.compare_arches(source, source)
        self.assertEqual([row[0] for row in results].count("missing_alt"), 2)
        self.assertEqual([row[0] for row in results].count("identical_text"), 1)
        with self.assertRaises(static_analysis.UnsafeArchitecture):
            static_analysis.parse_arch('<!DOCTYPE t [<!ENTITY x SYSTEM "file:///etc/passwd">]><t>&x;</t>')
        with self.assertRaises(static_analysis.AnalysisLimit):
            static_analysis.parse_arch("<t>" + ("a" * (static_analysis.MAX_ARCH_BYTES + 1)) + "</t>")
        with self.assertRaises(etree.XMLSyntaxError):
            static_analysis.parse_arch("<t><p></t>")

    def test_bounded_and_failed_run_states(self):
        self._page("bound", "<p>Long sentence for a bounded scan.</p>")
        with patch.object(website_language_audit, "MAX_PAGES", 1):
            bounded = self._run()
            bounded.action_scan()
        self.assertEqual(bounded.state, "truncated")
        self.assertLessEqual(bounded.processed_count, 1)
        with patch.object(
            website_language_audit.WebsiteAuditRun, "_analyze_page",
            side_effect=static_analysis.UnsafeArchitecture("synthetic malformed XML"),
        ):
            failed = self._run()
            failed.action_scan()
        self.assertEqual(failed.state, "failed")
        self.assertGreater(failed.failure_count, 0)

    def test_demo_scope_when_loaded(self):
        if not config["with_demo"]:
            return
        demo = self.env.ref("cyfr_website_language_audit.audit_demo_main_run")
        self.assertEqual(demo.lang_id, self.pl)
        self.assertEqual(demo.website_id.default_lang_id.code, "en_US")
        self.assertTrue(demo.website_id.default_lang_id.active)
        self.assertTrue(demo.website_id.language_ids & self.env.ref("base.lang_en"))
        self.assertTrue(demo.website_id.language_ids & self.pl)
        self.assertEqual(demo.state, "draft")
        self.assertTrue(self.env.ref("cyfr_website_language_audit.audit_demo_second_run"))
        main_page = self.env.ref("cyfr_website_language_audit.audit_demo_main_page")
        self.assertTrue(main_page.is_published)
        self.assertIn("Website language audit demonstration", main_page.with_context(lang="en_US").arch_db)
        self.assertIn("Demonstracja audytu językowego witryny", main_page.with_context(lang="pl_PL").arch_db)
        self.assertTrue(self.env.ref("cyfr_website_language_audit.audit_demo_second_page").is_published)
        self.assertFalse(self.env.ref("cyfr_website_language_audit.audit_demo_unpublished_page").is_published)
