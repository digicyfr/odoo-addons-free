{
    "name": "Website Language Audit",
    "summary": "Review static website translations, SEO fields, and image descriptions",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "author": "Cyfr Sp. z o.o.",
    "website": "https://digicyfr.com",
    "license": "LGPL-3",
    "depends": ["website"],
    "data": [
        "security/ir.model.access.csv",
        "security/rules.xml",
        "views/website_language_audit_views.xml",
    ],
    "demo": ["demo/website_language_audit_demo.xml"],
    "application": False,
    "installable": True,
    "auto_install": False,
}
