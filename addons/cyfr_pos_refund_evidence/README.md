# POS Refund Evidence (Odoo 19)

A free backend evidence queue for native Odoo POS refunds. After native refund persistence or POS synchronization, the addon creates one case for each `is_refund` order, then lets the order's Odoo POS user or a POS manager enter a controlled reason and a condition note. Managers can review incomplete cases and group results by reason, POS, refund date and company. Every refund line shows its original sale line and order when Odoo provides `refunded_orderline_id`.

## Install and use

Install `cyfr_pos_refund_evidence` on Odoo 19 Community or Enterprise with the native Point of Sale app. Open **Point of Sale → Configuration → Refund Reasons** as a POS manager to create company-specific reasons. Process a normal POS refund. Open **Point of Sale → Orders → Refund Evidence** and complete the case. A POS user sees cases for orders whose native `user_id` is that Odoo user; this may be a shared login rather than an individual cashier. POS managers see all cases in their allowed companies. `recorded_by` identifies the user who last wrote the reason or condition, and is never inferred from the session opener.

The queue opens with an Incomplete filter. Clear it to see completed cases. Open a case to inspect each native refund line and its linked original sale line/order. An original order count of zero means the refund lines lack native source links. Such cases remain eligible for evidence entry but have no inferred original sale. Native Odoo POS frontend synchronization allows one original order per refund; the backend model can still represent multiple origins, and this addon shows all of them.

## Scope and compatibility

Only orders explicitly marked `is_refund=True` are captured. Standalone negative-quantity orders without that native flag are excluded. The addon does not change refund authorization, tender, taxes, stock moves, invoice or accounting logic. It does not add a cashier popup, offline capture, attachments or automatic accusations. A case appears after native refund persistence; it is not a refund prerequisite.

Dependency: `point_of_sale` only. Version `19.0.1.0.0`, LGPL-3. Tested against pinned Odoo 19.0-20260908 Community image. Enterprise runtime is unverified unless separately stated in release evidence.

## Data and retention

Cases link to native orders and lines; they do not copy customer names, addresses or receipt identifiers into another table. Store only operational condition notes, not customer personal data. Cases are removed when their refund order is removed; reason codes may be archived, and referenced reasons cannot be deleted. Odoo administrators should apply their usual retention and backup policy to POS orders and this linked evidence. Managers should periodically review incomplete cases.

This is an operational review queue, not a tamper-evident ledger: authorized POS users can revise evidence, and native permissions may allow an order to be deleted with its case.

## Demo and tests

Demo data supplies three reason codes in the main demo company. The automated tests create synthetic full, partial and multi-origin refunds, an incomplete case and an unflagged negative order. The module intentionally does not install persistent demo POS orders, sessions or a second company: native POS fixture dependencies and company-owned demo records can leave uninstall residue. The multi-origin case is a backend model test because native frontend sync rejects that combination.
