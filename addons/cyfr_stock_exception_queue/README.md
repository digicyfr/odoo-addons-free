# Stock Exception Queue for Odoo 19

This free addon gives inventory teams a scan-backed queue of negative free stock, free stock below an active reorder rule's minimum, and zero free stock observed for a configured number of days. It depends only on Odoo Inventory (`stock`) and does not mutate inventory or create procurement.

## Setup

1. Install **Stock Exception Queue** and open **Inventory → Stock Exceptions → Scan Scopes**.
2. An Inventory Administrator creates a scope for one company, warehouse, and internal location beneath its stock root. The scope includes that location and at most 49 eligible internal descendants (50 locations total). Set **Zero Days** to the minimum elapsed days after the first zero scan; `0` flags on the second consecutive zero scan.
3. Click **Scan Next Batch** until the scope state is **Idle** and **Last Scan At** is recent. One click processes at most 200 candidate products across at most 50 locations. The scheduled job runs every five minutes and processes one batch for the least recently served active scope. The **Last Batch At** field shows this rotation. Large catalogs or many scopes may need manual extra batches to complete a scan within one day.
4. Open **Inventory → Stock Exceptions → Exception Queue**. Inventory Users can read the queue; Administrators can change scopes and scan. The form links to the matching replenishment rules.

The queue shows severity, product, location, scope, free quantity, minimum, last scan, and stale status by default. Use the list's column chooser or open a row to see on-hand, reserved, first zero, persistent-zero, and company fields. The scope list also shows stale status.

## Meaning of the numbers

**On Hand** is the sum of stored quant quantity at each eligible internal location. **Reserved** is the sum of reserved quant quantity. **Free Quantity** is on hand minus reserved, in the product's default unit of measure. **Orderpoint Minimum** is the active Odoo reorder rule minimum for that exact product and location. This is not forecasted quantity: incoming and outgoing moves are not predicted here. Consigned quants (those with an owner) are excluded. Quants are grouped across lots and packages. Products without quants or active orderpoints are outside scope.

**Persistent Zero** starts at the first scan that observes zero. It is never inferred from historical stock moves. **Zero Persisted** remains visible even when a reorder minimum makes **Below Minimum** the primary severity. A row with no active exception remains as history for zero tracking. **Stale Results** is shown when the scan has never completed, is in progress, or the last completed scan is more than 36 hours old. A failed cron batch leaves its short error on the scope; fix the cause and scan again.

## Compatibility and privacy

Tested against Odoo 19 Community image `19.0-20260908`. Enterprise remains unverified. The addon stores product/location quantity snapshots and scan timestamps in the same Odoo database; it sends no telemetry and makes no external network calls. No other Cyfr addon is required. See [Polish guide](README.pl.md), [security notes](SECURITY.md), and [change log](CHANGELOG.md).

## Limitations

Scope locations must belong to the selected company. Products owned by a parent company are eligible when Odoo permits them in the selected child company. Overlapping scopes can show the same product/location twice, with independent scan histories. The scheduled job is intentionally bounded to one scope batch per invocation; its five-minute rotation provides up to 288 batch slots per day across all active scopes. The queue never adjusts stock, reserves stock, places orders, or performs expiry analysis.
