# Lot Expiry Worklist for Odoo 19

This LGPL-3 addon adds an accountable stock worklist to Odoo Community's native `product_expiry` screens. It does not replace lot expiry alerts or change stock.

## Install and use

Install **Lot Expiry Worklist**. Odoo installs `product_expiry` and its `stock` dependency automatically. Give people the native Inventory User or Inventory Administrator role. In **Inventory → Lot Expiry → Scan**, an Inventory Administrator selects a company-owned internal location and a 0–365 day horizon. The scan includes its active internal descendants but keeps each exact location separate. Open **Inventory → Lot Expiry → Worklist** to see the last snapshots, including actions retained after stock leaves.

For each lot, exact location and stock owner, the administrator can assign one responsible Inventory User, next action and note. The assignee or administrator can acknowledge it. Reassignment resets acknowledgment. The action's chatter records assignment changes. Use **Open Native Lot** for Odoo's expiry dates and **Current Quants** for the underlying stock. Rerun the scan after transfers, reservations, expiry-date changes or owner changes.

## Quantity and date meaning

Rows group package quants within **company × lot × exact internal location × stock owner**. No external owner is a separate key from each consigned owner. Only positive net on-hand groups enter a new worklist; zero/negative stock, customer/vendor/transit locations, archived locations, companyless locations and products without native expiration tracking do not create active rows. Existing rows are refreshed with `stock_present = false` when their net on-hand becomes nonpositive. They remain for acknowledgment history. Scans do not forecast incoming stock or split reservations by package beyond the grouped totals.

**Physical unreserved** equals on-hand minus reserved in the product's base unit at the observed time. It is not Odoo's `available_quantity`: native `product_expiry` may set that value to zero after the removal date. The scan compares only the stored lot `expiration_date` with the current UTC timestamp plus the chosen number of 24-hour periods. `alert_date`, best-before `use_date`, and `removal_date` are displayed as separate native dates. An expired lot has `expiration_date <= now`; a future lot within the horizon is “Within Horizon.” The list is a snapshot, so its quantities and expiry state can become stale until refreshed.

One scan reads at most 5,000 lot quants and 1,000 lot positions, including prior actions, under the selected location. It stops with no partial refresh if either limit is exceeded; select a narrower shelf. The scan dialog states both limits. It is one capped run, not a resumable batch. No scheduled scan or automatic stock action is installed.

## Limits and support

The addon does not move, reserve, scrap or dispose of stock; edit lot dates; change accounting; or provide regulatory shelf-life advice. Native `product_expiry` alerts continue unchanged. Results depend on users' native lot, location, owner and company permissions. Odoo Online does not accept custom server addons. Enterprise was unavailable for this release check; self-hosted Community is the verified target. Report issues through the Digicyfr support path, with module version and steps to reproduce, without customer data or database exports.
