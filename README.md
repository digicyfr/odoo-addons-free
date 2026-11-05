# Digicyfr free Odoo 19 add-ons

> **Repository moved:** Each addon now has its own public repository, release, and
> protected exact-version branch. This combined repository remains available for
> historical source and release provenance. Use the standalone repositories for
> new installations and issues.

| Addon | Current repository |
| --- | --- |
| `cyfr_product_data_health` | [digicyfr/odoo-addon-cyfr-product-data-health](https://github.com/digicyfr/odoo-addon-cyfr-product-data-health) |
| `cyfr_pos_tax_audit` | [digicyfr/odoo-addon-cyfr-pos-tax-audit](https://github.com/digicyfr/odoo-addon-cyfr-pos-tax-audit) |
| `cyfr_crm_next_step` | [digicyfr/odoo-addon-cyfr-crm-next-step](https://github.com/digicyfr/odoo-addon-cyfr-crm-next-step) |
| `cyfr_stock_exception_queue` | [digicyfr/odoo-addon-cyfr-stock-exception-queue](https://github.com/digicyfr/odoo-addon-cyfr-stock-exception-queue) |
| `cyfr_purchase_receipt_delays` | [digicyfr/odoo-addon-cyfr-purchase-receipt-delays](https://github.com/digicyfr/odoo-addon-cyfr-purchase-receipt-delays) |
| `cyfr_website_language_audit` | [digicyfr/odoo-addon-cyfr-website-language-audit](https://github.com/digicyfr/odoo-addon-cyfr-website-language-audit) |
| `cyfr_pos_refund_evidence` | [digicyfr/odoo-addon-cyfr-pos-refund-evidence](https://github.com/digicyfr/odoo-addon-cyfr-pos-refund-evidence) |
| `cyfr_quote_watchlist` | [digicyfr/odoo-addon-cyfr-quote-watchlist](https://github.com/digicyfr/odoo-addon-cyfr-quote-watchlist) |
| `cyfr_lot_expiry_worklist` | [digicyfr/odoo-addon-cyfr-lot-expiry-worklist](https://github.com/digicyfr/odoo-addon-cyfr-lot-expiry-worklist) |
| `cyfr_pos_shift_handover` | [digicyfr/odoo-addon-cyfr-pos-shift-handover](https://github.com/digicyfr/odoo-addon-cyfr-pos-shift-handover) |

Original, independently installable Odoo 19 add-ons from Digicyfr. This public
repository contains only free add-on source. Each module has its own LGPL-3
license copy, English and Polish guides, demo data, and tests.

| Module | Purpose | Required Odoo app |
| --- | --- | --- |
| [`cyfr_product_data_health`](addons/cyfr_product_data_health/README.md) | Review missing product identifiers, prices, categories, and images after a catalog import | `product` |
| [`cyfr_crm_next_step`](addons/cyfr_crm_next_step/README.md) | Find open CRM leads with no scheduled activity or an overdue activity | `crm` |
| [`cyfr_pos_tax_audit`](addons/cyfr_pos_tax_audit/README.md) | Review POS catalog taxes and configured fiscal-position mappings before opening a till | `point_of_sale` |
| [`cyfr_stock_exception_queue`](addons/cyfr_stock_exception_queue/README.md) | Review negative, below-minimum, and persistently unavailable stock in a bounded advisory queue | `stock` |
| [`cyfr_purchase_receipt_delays`](addons/cyfr_purchase_receipt_delays/README.md) | Review late or soon-due open physical purchase receipts and schedule follow-up activities | `purchase_stock` |
| [`cyfr_website_language_audit`](addons/cyfr_website_language_audit/README.md) | Review static multilingual page content, missing localized SEO fields, and image descriptions | `website` |
| [`cyfr_quote_watchlist`](addons/cyfr_quote_watchlist/README.md) | Review draft and sent quotations by expiry and missing future activity without sending customer messages | `sale_management` |
| [`cyfr_pos_refund_evidence`](addons/cyfr_pos_refund_evidence/README.md) | Record controlled refund reasons, condition and original-sale provenance after native POS returns | `point_of_sale` |
| [`cyfr_lot_expiry_worklist`](addons/cyfr_lot_expiry_worklist/README.md) | Assign and acknowledge action for expiring lot stock at each exact internal location and owner | `product_expiry` |
| [`cyfr_pos_shift_handover`](addons/cyfr_pos_shift_handover/README.md) | Record operational tasks between closed and later opened POS sessions on the same register | `point_of_sale` |

## Install

Use a self-hosted Odoo 19 server or Odoo.sh deployment that permits custom
add-ons. Place the module directory on the Odoo add-ons path, update the Apps
list, and install the selected module. The versioned ZIP attached to each
module's GitHub release contains one add-on directory and a separate SHA-256
checksum file. Verify the checksum before installation.

Odoo Online does not support installing arbitrary server add-ons. Odoo 19
Community was tested on the pinned build described in the module release notes;
Enterprise compatibility has not yet been tested.

## Source and support

Each release tag is named `<module>-<version>` and contains the matching source.
Use the issue tracker in the relevant standalone repository for
reproducible defects. Do not post credentials, session cookies, private product
data, or database exports. See each module's `SECURITY.md` for its data-access
and disclosure policy.

The module source, documentation, translations, and icon in this repository
were created for this project. Odoo is a trademark of Odoo S.A.; this repository
is not an official Odoo project.

## License

LGPL-3. See [LICENSE](LICENSE) and each module's license copy.
