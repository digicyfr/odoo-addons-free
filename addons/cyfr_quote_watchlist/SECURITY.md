# Security review

- Sales users may create and read only their own temporary scan and rows. Company rules limit both to allowed companies; the row search additionally intersects live `sale.order` record access. Direct row read/export and actions recheck the linked quotation.
- Only Sales managers can create or change company horizon settings. The setting has a company rule and validates 0–90 days. Wizard RPC cannot override a manager's horizon or forge result rows.
- The scan searches `sale.order` and groups `mail.activity` under the caller's permissions. It never applies `sudo()` to quotes, partners or activities. `sudo()` is confined to writing the caller's computed transient snapshot after scope checks.
- Scheduling returns Odoo's native activity form only after current quotation read/write and state checks. Opening the form does not create an activity.
- No customer email, automatic cancellation, background job, external service, credentials or analytics endpoint.
- Future activity means a date strictly later than the user's local today. A hidden activity is not inferred.
