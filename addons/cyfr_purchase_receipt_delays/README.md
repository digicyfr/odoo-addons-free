# Purchase Late Receipt Worklist

Free, independently installable Odoo 19 add-on for buyers following up on open warehouse receipts. License: LGPL-3. Dependency: `purchase_stock` only.

## Use

1. Install **Purchase Late Receipt Worklist** in an Odoo 19 database with Purchase and Inventory.
2. As a Purchase User, open **Purchase → Orders → Late Receipts**.
3. Set the due-soon horizon (0–90 days) and optionally narrow by vendor, buyer, company or expected-date range. Select **Scan Open Receipts**.
4. Review late and due-soon lines, remaining quantity, vendor, buyer, purchase order, and linked receipts. Use **Schedule Follow-up** to open Odoo's normal activity form for the purchase order, with the line reference prefilled. Saving the activity is a separate user action.

The scan is a snapshot. Return to the wizard and scan again after receipts or purchase orders change. Editing a filter clears the old snapshot. The result list can be filtered by status, vendor, buyer, company and expected day. A row whose promised date changed after scanning can still open the activity form: the buyer may need to follow up about that change. The action rechecks that the order remains confirmed, the quantity remains open, and the buyer still has access; refresh the scan for the current due status.

## What is counted

The worklist includes confirmed (`purchase`) order lines for physical products (`consu`) on ordinary warehouse purchase orders. It excludes RFQs, cancelled orders, sections, notes, down payments, fully received or over-received lines, services and direct dropship orders. This is a **warehouse receipt follow-up** list, not all procurement commitments.

Remaining quantity is the purchase line's ordered quantity minus its native `qty_received`, compared using its own unit of measure. Native Odoo stock-move rules determine received quantities, including eligible returns. The status uses the user's timezone and local expected day: before today is **Late**, today through the horizon is **Due Soon**. Missing expected dates are shown as **Date Missing** if exceptional migrated data has one; standard Odoo 19 constraints require a date for a normal accountable line.

The scan reads at most 2,000 candidate lines and displays at most 500 open lines. A warning appears when a limit was reached; narrow filters and scan again. It does not forecast new ETAs or modify vendor lead times, dates, stock moves, receipts, purchase orders, or accounting.

## Security and support

Purchase Users can scan only companies allowed in their session. Each transient snapshot belongs to its creator; another user cannot open it. Source purchase-line and purchase-order access is checked again when opening links or scheduling an activity. Odoo's normal activity form applies its own ACL and record rules when the user saves.

Tested against pinned Odoo Server **19.0-20260908** (`odoo@sha256:a627eda6b4154eead21c4fca55f84f1671d870ca111aa57f93ca305861bc4613`). See `CHANGELOG.md`, `SECURITY.md`, and the portfolio module specification for validation evidence and limits. Enterprise validation must be recorded separately.
