# Digicyfr free Odoo 19 add-ons

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
Use [GitHub Issues](https://github.com/digicyfr/odoo-addons-free/issues) for
reproducible defects. Do not post credentials, session cookies, private product
data, or database exports. See each module's `SECURITY.md` for its data-access
and disclosure policy.

The module source, documentation, translations, and icon in this repository
were created for this project. Odoo is a trademark of Odoo S.A.; this repository
is not an official Odoo project.

## License

LGPL-3. See [LICENSE](LICENSE) and each module's license copy.
