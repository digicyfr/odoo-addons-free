# Security and retention

- POS user and POS manager groups receive read/create/write access to handovers and tasks, with no delete ACL. A global company rule limits both models to allowed companies. The manager group implies the POS user group.
- Handover search, direct read/export, and write also check current native `pos.session` and `pos.config` visibility. Task search/read/export/write check their handover. Native record rule changes therefore remove linked handover access without waiting for a rescan.
- Model methods reject direct writes to source/target session, claim identity/times, acknowledgement identity/times, and task parent/company. Claims lock the handover row and recheck it before writing one target; a concurrent lock conflict asks the user to retry. Retry by the original claimant is idempotent. A different claimant cannot take over the record.
- Only a POS user can claim. Only the recorded claimant or a POS manager can acknowledge; the acting `env.uid` is stored. Manager reassignment and reopening affect operational tasks only.
- Native POS access is company based and has no per-register user assignment. A shared database login cannot identify the human. The module verifies register consistency, not physical presence at a register.
- No automatic deletion or purge is installed. Normal users and managers cannot delete records. Database administrators must define retention according to their own obligations.
- No secrets, external API calls, or customer data are included. Demo records are synthetic and attach to Odoo's own closed POS demo session.
