# POS Shift Handover for Odoo 19

An operational task handover between Point of Sale sessions on the same register. It is a backend workflow for POS database users and managers. It does not change cash counts, journal entries, orders, the financial closing note, or Odoo's native session close.

## Use

1. Open **Point of Sale → Sessions**, select the outgoing session, and click **Outgoing Handover**. Create one handover and add tasks using its **Tasks** button. Each task can have a priority, owner, due time, status, and operational note.
2. Close the outgoing session with Odoo's normal **Close Session & Post Entries** workflow. The handover remains available whether or not tasks are complete.
3. Open the next session on the same POS register. Its **Incoming Handovers** button shows unclaimed work. Open a handover and click **Claim Current Session**, then **Acknowledge Receipt**. The logged-in database user and actual action times are recorded. A later opened session can claim a handover if an intervening shift skipped it.
4. POS managers can use **Point of Sale → Overdue Handover Tasks** to reassign, cancel, or reopen tasks. A task owner can update its progress and note; the preparer can edit tasks before claim.

The overdue queue compares each task's due time with the current server time, so tasks due earlier today appear immediately. If two users try to claim at once, one receives a retry message while the other transaction holds the claim lock. Refresh and retry after the first action finishes; a successful claim remains assigned to its first recipient.

Claim requires the outgoing session to be closed and the receiving session to be open, regular, later, and on the same POS configuration and company. A handover can stay unclaimed after close. A claimed handover cannot be redirected to another session. Repeating a claim or acknowledgement by the same recorded user is safe.

The safe demo contains an unclaimed handover on an Odoo demo session that Odoo itself closed. It does not create an active POS session or fabricate a financially posted one. Automated tests cover a synthetic A→B transition, wrong register/company, separate-transaction claim contention, permissions, idempotence, and finance-field preservation.

## Identity and security

Use a separate Odoo database login for each person who must be identified in the audit trail. `pos.session.user_id` means **Opened By** and may differ from the person who presses Claim or Acknowledge. If employees share a database login, this module records that shared login and cannot establish which human acted. Native POS access is company based; the backend cannot prove which physical register a logged-in user is standing at.

Only POS users have model access. Company record rules and live read checks on linked native sessions/configurations protect list, form, export, and button actions. The preparer may change an unclaimed handover. Managers may edit handover labels and reassign/reopen tasks. Operators cannot directly write session, claim, or acknowledgement fields. Handover and task deletion is disabled for normal users and managers; records are retained until a database administrator applies an approved retention process. No automatic purge is installed.

## Scope

This release has no POS frontend component, offline flow, automatic reminders, cash-discrepancy logic, forced close condition, employee timekeeping, or automatic task creation. It depends only on `point_of_sale` and is independently installable on Odoo 19 Community. Enterprise behavior is not verified.

License: LGPL-3. See [LICENSE](LICENSE), [SECURITY.md](SECURITY.md), and [CHANGELOG.md](CHANGELOG.md).
