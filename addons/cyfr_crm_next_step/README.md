# CRM Next Step Queue for Odoo 19

CRM Next Step Queue puts open leads and opportunities needing an activity in one saved CRM view. It uses Odoo's own CRM lead and activity records; it creates no parallel task list and never changes a lead when the queue is opened.

## Install

Install this folder as an Odoo 19 server addon. The only dependency is the standard `crm` module. The addon works independently of other Cyfr addons. It is intended for Odoo Community and Enterprise on Odoo.sh or a self-hosted server. An Enterprise build has not yet been verified. Odoo Online does not accept arbitrary server addons.

## Use

1. Open **CRM → Sales → Next Step Queue** as a CRM salesperson or manager.
2. The queue lists active leads and opportunities whose Odoo CRM status is pending and which have no active activity or at least one overdue activity. The **Next Step Status** column names the reason for each row.
3. Use **No Scheduled Activity** or **Overdue Activity** to focus the list. Search or group by salesperson, team, or company. Company filters appear when Odoo multi-company mode is enabled.
4. Open a lead to use Odoo's standard activity planner. The queue updates from Odoo's current activity state; there is no separate refresh job.

An activity due today is not overdue. An overdue activity keeps a lead in the queue even if another activity is planned for later. A completed activity no longer counts as scheduled, so a lead with only completed activities appears under **No Scheduled Activity**. Odoo evaluates deadlines in the activity assignee's timezone. A won lead is omitted based on Odoo's stored won/lost status; archived or lost leads are omitted.

The demo dataset (installed only with Odoo demo data) includes a lead with no activity, planned and overdue activities, won/lost examples, and a second-company lead. All names are synthetic.

## Scope and limits

The list is advisory. It has no threshold setting, digest, outgoing mail, network request, telemetry or automatic task creation. V1 does not estimate last customer contact: lead write dates and stage changes do not prove contact. The queue trusts the existing `crm.lead` ACLs and company/salesperson rules. In databases with custom CRM record rules, users see only the leads allowed by those rules.

See [SECURITY.md](SECURITY.md) for permissions and privacy details and [README.pl.md](README.pl.md) for the Polish guide. Licensed under [LGPL-3](LICENSE).
