{
    "name": "POS Tax Setup Audit",
    "summary": "Review POS catalog tax mappings before opening a till",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Cyfr Sp. z o.o.",
    "website": "https://digicyfr.com",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "security/rules.xml",
        "views/pos_tax_audit_views.xml",
    ],
    "demo": ["demo/pos_tax_audit_demo.xml"],
    "application": False,
    "installable": True,
    "auto_install": False,
}
