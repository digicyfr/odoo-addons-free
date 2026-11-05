# Security and privacy review

This addon defines one nonstored, read-only selection field on the existing `crm.lead` model, an `ir.actions.act_window`, two `ir.ui.view` records and one CRM menu. It adds no new model, controller, scheduled job, ACL, record rule, public method, export, attachment, or external request. The field derives its label from Odoo's `activity_state` for the current user; it does not store or copy lead data. Existing `crm.lead` and `mail.activity` records remain the source of truth. No credentials, customer data or snapshots are stored by the addon.

The menu is offered to Odoo CRM salespeople and managers. The action uses a normal `crm.lead` search without `sudo()`, so standard CRM access controls and active-company record rules apply to UI and direct RPC reads. The list disables inline edits; opening a lead uses the standard CRM form and the user's existing write permission. The list's activity widget uses Odoo's standard activity planner and its permissions.

The queue's action domain is advisory and is not an access rule. Users with access to the underlying CRM model can query their allowed leads outside this action. Any custom third-party CRM record rule remains in force; administrators should verify it in their deployment. Lead or activity retention and deletion remain governed by Odoo and the organization's policies.

No digest or outbound email ships in this version, so there is no recipient or mail-queue surface. There is no cross-company aggregation or elevated background task.
