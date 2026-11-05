# Quote Follow-up Watchlist for Odoo 19

A manual Sales worklist for quotations that need attention. It combines quotation validity dates with **future** scheduled activities, without changing quotations or contacting customers.

## Use

1. Open **Sales → Orders → Quote Watchlist**. The company horizon defaults to seven days; a Sales manager can set 0–90 days in **Sales → Configuration → Quote Watchlist Horizon**.
2. Optionally narrow the company, salesperson, team, or validity date range, then select **Scan Quotations**. The scan records at most 2,000 newest draft/sent quotations and shows at most 500 result rows. If either limit is reached, the scan stays on the form to show its warning and counts. Open the partial result with **View Last Scan**, or narrow filters and scan again.
3. Review reason, customer, owner, validity and next future activity. **Open Quote** uses Odoo's native quotation form; **Schedule Follow-up** opens Odoo's native activity dialog. The activity is created only if the user saves that dialog.

An activity dated tomorrow or later is future. An activity due today or overdue is not future; the worklist flags those separately. A missing validity date is shown as **Validity Date Missing**. An expired or soon-expiring quote remains visible even when it already has a future activity. A quotation outside the horizon appears when it has no future activity. The date filters exclude quotations with no validity date.

The scan is a temporary snapshot belonging to its creator. Rescanning replaces it; Odoo eventually purges old transient records. The result is rechecked against current Sales quotation access on every search, read, export and drill-down. The scan does not alter quotations, send email, schedule activities, cancel sales, or create a persistent duplicate quote table.

## Install

Install `cyfr_quote_watchlist` from your custom addons path. It depends only on Odoo 19's `sale_management`, which activates the Sales application menu. Sales users can scan; Sales managers may change the company horizon. The module works with Odoo 19 Community. Enterprise remains unverified.

## Limits

This is a review queue, not a notification service. Dates are Odoo Date values evaluated against the scanning user's local calendar day. Activity lookup uses the caller's access to `mail.activity`; hidden activities cannot be inferred. A scan sees up to 2,000 newest matching quotations, so filter or rerun for large databases. A salesperson cannot see quotations outside Odoo's standard Sales access rules.

## License

LGPL-3. See [LICENSE](LICENSE).
