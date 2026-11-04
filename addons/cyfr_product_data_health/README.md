# Product Data Health for Odoo 19

Product Data Health gives catalog managers a repeatable, read-only checklist of missing product data. It scans active, saleable variants and records one issue row per variant with stable CSV codes. Results are advisory. The addon never changes products, prices or taxes.

## Install and setup

Install the `cyfr_product_data_health` folder as a normal Odoo 19 server addon. It depends only on Odoo's `product` module. Odoo 19's Product module does not define a standalone Products menu, so this independent addon adds a top-level **Data Health** app. A global default policy is installed with checks for internal reference, barcode, non-positive sale price, missing or configured generic category, and missing image. Product managers may edit it under **Data Health → Policies**. All checks are optional; a zero price can be a deliberate price.

Policy order is: company + category, company, global + category, global. Only one active policy is allowed in each scope. A policy that has no generic categories flags only products with no category. The pinned Odoo 19 Product module does not provide a `categ_id` default on product templates, so the missing-category check is active even with an empty generic-category list. Choose placeholder categories explicitly if your catalog uses them; the default Goods category is not assumed to be a placeholder. No policy means no issue row for that product.

With Odoo demo data enabled, the addon includes an invented **Demo Placeholder Category**, a category-scoped policy and a product in that category to demonstrate the generic-category warning. Demo policy data is not installed in production databases without demo mode.

## Run a scan

1. A user with Odoo's **Products: Create** (`product.group_product_manager`) access opens **Data Health → Scans**, creates a scan, and chooses an allowed company.
2. Click **Scan next 200 products** until the state is **Complete**. The progress fields show the number processed and the count when the scan began. Products added during a scan can change the final count; start another scan for a fresh snapshot.
3. Open **Current Issues** or the scan's **View issues** button. Search and group by company or product category. Open an issue, then click **Open Product** to edit in Odoo's normal product form. The issue list can be exported with Odoo's standard CSV export if your role permits exports.

A completed scan becomes current for its company and retires the previous current scan. An unfinished scan does not hide the last completed results. Historical scans stay available to managers. A manager can use **Delete old scan** on a completed, non-current scan under the organization's retention policy; its issue rows are removed with it. The current scan cannot be deleted until a newer one completes.

Internal users who may read Odoo products can see **current issues** for their allowed companies. They may read only scans they created; product managers may read all scans and historical issues in their allowed companies. The issue list shows readable labels and exports stable issue codes. A current issue can reference a manager-owned scan that an ordinary user cannot open.

## Semantics and limits

- Internal reference and barcode are checked on each **variant**. Sale price and category come from the template. The image check accepts a variant image or inherited template image.
- The sale price rule flags values `<= 0` when enabled. It does not evaluate pricelists, discounts, currencies or margin.
- Only active, saleable variants in the selected company or shared across companies are scanned. Product ACLs and company rules still apply. Archived and non-saleable products are ignored.
- Each button press scans at most 200 variants in one transaction. A scan is a snapshot, not an automatic live health score. Scans have no scheduler or network calls.
- Issue codes: `missing_internal_reference`, `missing_barcode`, `non_positive_sale_price`, `generic_or_missing_category`, `missing_image`.

## Compatibility and support

Designed for Odoo 19 Community and Enterprise on Odoo.sh or self-hosted Odoo. Odoo Online does not support arbitrary server addons. See `SECURITY.md` for data and access behavior. Report defects through the source repository issue tracker when published.
