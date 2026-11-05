# POS Tax Setup Audit for Odoo 19

A free, read-only catalog tax review for Point of Sale managers. It reports the company sales taxes on eligible POS product variants and the result after each configured fiscal position. Flags are **advisory**: an empty or multiple-tax result can be deliberate. Ask your accountant or localization owner to decide the legally correct rate.

## Install and use

Install the `cyfr_pos_tax_audit` directory as an Odoo 19 addon. Its only declared dependency is `point_of_sale`. Open **Point of Sale → Configuration → Tax Setup Audit**, create a scan for one POS, and select a page size (1–100). Click **Scan This Page**. Review the matrix, use **Next Page** for the remaining variants, or **Export CSV** for the current page. Open a matrix row to follow product or fiscal-position links; **Open Source Taxes** and **Open Result Taxes** open the tax form or a filtered tax list. **Tax Matrix** is a searchable view of your current transient scan rows. All screens are limited to POS managers.

The scan uses Odoo 19's normal `product.template._load_pos_data_domain({}, config)` (company, active, saleable, available in POS, configured category restriction), then includes each matching variant. It uses a stable ID page order. POS may additionally load special/tip products, combo components, optional products, or products already in an order; those contextual extras are outside this report. POS limited loading can display a different initial subset. Customer-specific or preset fiscal positions are outside the configured-scenario matrix. Each page is limited to 1,000 rows, 2,000 distinct source/mapped tax candidates, and 19 configured fiscal positions plus base. Reduce the page size or configured fiscal positions if a bound is exceeded.

`No Company Tax` means the configured company tax set is empty. `Multiple Taxes` is descriptive, not an error. `Other Company Tax Excluded` means the product has a tax outside the selected POS company domain; its name is not copied into the report. `Empty Mapped Result` can be a valid fiscal-position exemption. The CSV includes these flags and is escaped against spreadsheet formula execution.

Demo data includes taxed and zero-tax items, a restricted POS category, and two fiscal-position scenarios. Cross-company isolation is covered by disposable test records rather than a demo company, so uninstall can remove all module-owned demo records cleanly.

## Data and compatibility

Scans and rows are Odoo transient records and expire with Odoo's normal transient cleanup. A new scan of the same page replaces its rows. Product, tax, fiscal-position, order and receipt records are never changed by this addon. Uninstall removes its menus, models and transient reports, leaving business data untouched. Version `19.0.1.0.0` supports Odoo 19 Community on Odoo.sh and self-hosted servers. Enterprise compatibility requires a separate acceptance run. Odoo Online does not install custom server addons.

The module uses LGPL-3 (see `LICENSE`). Report bugs and security issues using the contact in `SECURITY.md`. Polish instructions are in `README.pl.md`.
