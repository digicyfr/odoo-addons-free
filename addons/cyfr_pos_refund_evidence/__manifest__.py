{
    "name": "POS Refund Evidence",
    "summary": "Record return reasons and trace each refund line to its original sale",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Cyfr Sp. z o.o.",
    "website": "https://digicyfr.com",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "security/refund_evidence_rules.xml",
        "views/refund_evidence_views.xml",
    ],
    "demo": ["demo/refund_evidence_demo.xml"],
    "application": False,
    "installable": True,
    "auto_install": False,
}
