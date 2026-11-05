# Website Language Audit for Odoo 19

Review published website pages in one enabled non-default language. The audit flags static text that matches the website's default-language text, missing explicit localized SEO title or description, and literal images without an alt description. It is an advisory worklist: identical copy may be intentional, and an empty SEO title may intentionally use Odoo's default title.

## Install and use

Install the `website` application, then install this addon. Enable the target language under **Website → Configuration → Settings**. A website designer opens **Website → Reporting → Language Audits**, creates a run with a website and target language, optionally lists exact brand terms to ignore, and clicks **Scan published pages**. Restricted website editors can read the resulting metadata worklist. Designers can open a result in Odoo's native page editor, choose the target language there, correct content, and create a new run to review again.

The scan checks website-specific pages plus global pages that have no active local override with a URL. It excludes unpublished, inactive, password or group-restricted, and future-scheduled pages. An active website-specific unpublished page suppresses its global source in that website context. If such an override appears after a scan, the earlier global-page findings are hidden from readers. Odoo 19 has one publication flag per page, not one per language; a language disabled on the selected website cannot be scanned.

## Scope and limits

- Maximum 600 website-specific and 600 global candidates, 200 selected pages, 256 KiB of architecture and 2,500 XML nodes per page, 2,000 issues, and 30 seconds of scan processing. The run shows **Truncated** when a bound is reached. An unsafe or malformed page architecture makes the run **Failed** with a failure count; completed results may be partial.
- Static XML nodes are compared at the same structural path, including content inside Odoo's standard `website.layout` page wrapper. Other template calls, dynamic QWeb expressions, conditional subtrees, scripts, styles, code, and changed XML structures are skipped. The module does not render pages, run JavaScript, crawl URLs, or check all accessibility rules.
- `alt=""`, `role="presentation"`, and `aria-hidden="true"` are explicit decorative-image exceptions. Literal images with a missing, whitespace-only, or common generic alt such as “image” are flagged. A short text under 12 characters is skipped; configured brand terms are ignored only on exact match.
- A missing target SEO value is detected from Odoo's stored translation keys. Odoo's ordinary translated read may display an English fallback even when the target value is absent. SEO findings are advisory.

## Data and maintenance

Each run stores website, language, initiating user, timestamps, state, counts, and optional ignored terms. Each issue stores a page reference and URL, type, severity, XML path or field name, and a SHA-256 hash of the source term or node path. It stores no page body, translation, screenshot, or attachment. Runs are snapshots; a designer may delete old runs, which removes their issues. There is no scheduled job, external call, telemetry, or automatic translation.

Community 19.0 is the verified target. Enterprise uses the same `website` dependency but must be verified separately. The addon is LGPL-3 and has no dependency on other Cyfr modules.
