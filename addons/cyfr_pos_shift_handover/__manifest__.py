{
    "name": "POS Shift Handover",
    "summary": "Operational tasks between POS sessions on the same register",
    "version": "19.0.1.0.0",
    "category": "Sales/Point of Sale",
    "author": "Digicyfr",
    "website": "https://digicyfr.com",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "security/handover_rules.xml",
        "security/ir.model.access.csv",
        "views/handover_views.xml",
    ],
    "demo": ["demo/handover_demo.xml"],
    "installable": True,
    "application": False,
}
