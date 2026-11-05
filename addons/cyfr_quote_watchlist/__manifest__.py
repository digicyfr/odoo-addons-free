{
    "name": "Quote Follow-up Watchlist",
    "summary": "Review expiring quotations and missing future follow-ups",
    "version": "19.0.1.0.0",
    "category": "Sales",
    "author": "Cyfr Sp. z o.o.",
    "website": "https://digicyfr.com",
    "license": "LGPL-3",
    "depends": ["sale_management"],
    "data": [
        "security/ir.model.access.csv",
        "security/quote_watchlist_rules.xml",
        "views/quote_watchlist_views.xml",
    ],
    "demo": ["demo/quote_watchlist_demo.xml"],
    "application": False,
    "installable": True,
    "auto_install": False,
}
