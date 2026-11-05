{
    "name": "Lot Expiry Worklist",
    "summary": "Assign and acknowledge expiring stock by lot, location and owner",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "author": "Cyfr Sp. z o.o.",
    "website": "https://www.digicyfr.com",
    "license": "LGPL-3",
    "depends": ["product_expiry"],
    "data": [
        "security/ir.model.access.csv",
        "security/rules.xml",
        "views/expiry_worklist_views.xml",
    ],
    "demo": ["demo/expiry_worklist_demo.xml"],
    "application": True,
    "installable": True,
    "auto_install": False,
}
