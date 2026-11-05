{
    "name": "Purchase Late Receipt Worklist",
    "summary": "Review open warehouse receipt quantities on confirmed purchase orders",
    "version": "19.0.1.0.0",
    "category": "Purchases",
    "author": "Cyfr Sp. z o.o.",
    "website": "https://digicyfr.com",
    "license": "LGPL-3",
    "depends": ["purchase_stock"],
    "data": [
        "security/ir.model.access.csv",
        "security/receipt_worklist_rules.xml",
        "views/receipt_worklist_views.xml",
    ],
    "demo": ["demo/receipt_worklist_demo.xml"],
    "application": False,
    "installable": True,
    "auto_install": False,
}
