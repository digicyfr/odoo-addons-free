# Security review

- Purchase Users alone receive model ACL and the menu. The transient wizard and rows have global owner/company record rules; no broad `sudo()` is used.
- The scanner uses the caller's `purchase.order.line` search and its existing Purchase company rule. A selected company must be in the caller's allowed companies. Public wizard RPC permits filter fields only. Result rows cannot be created, changed or deleted directly by Purchase users; the scan writes only to its already-authorized transient snapshot.
- Result search, direct read and export also enforce current source purchase-line access, so later record-rule changes hide old snapshots. Row actions recheck owner, current company access and source-line read access. Activity scheduling additionally checks write access to the target purchase order. The add-on returns the native `mail.activity` form; it does not create an activity by itself.
- The scan stores only short-lived transient snapshots. Filters clear prior rows; Odoo's transient vacuum removes old snapshots. Data are not exposed via a public controller.
- The scanner bounds candidates at 2,000 and visible rows at 500. No unbounded stock aggregation, arbitrary URL fetch, email sending or privileged background job is added.
- The source purchase order and stock models remain governed by Odoo ACL, record rules and ordinary company checks.

Review on pinned Odoo 19.0-20260908. Validate again when upgrading Odoo or changing Purchase/Inventory security rules.
