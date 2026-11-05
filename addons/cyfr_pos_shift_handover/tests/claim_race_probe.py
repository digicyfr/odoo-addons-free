"""Run with ``odoo shell`` against a disposable, installed Odoo 19 database.

This integration probe commits isolated fixtures before opening two concurrent
POS-user cursors. TransactionCase cannot do that safely because its outer
transaction holds Odoo menu/group locks. The probe removes every fixture and
verifies the cleanup before printing success.
"""

import json
from datetime import timedelta
from uuid import uuid4

from odoo import Command, api, fields
from odoo.exceptions import UserError


def run_claim_race(env):
    ids = {}
    suffix = uuid4().hex[:12]
    result = {"two_pos_users": False, "lock_retry": False,
              "loser_rejected_after_commit": False, "one_recipient": False,
              "cleaned": False, "demo_unchanged": False}
    demo = env.ref("cyfr_pos_shift_handover.demo_unclaimed_handover")
    demo_before = demo.read(["target_session_id", "claimed_by_id", "claimed_at"])[0]
    try:
        group = env.ref("point_of_sale.group_pos_user")
        company = env.company
        users = env["res.users"].create([{
            "name": "Shift Race " + label,
            "login": "shift-race-" + label.lower() + "-" + suffix,
            "company_id": company.id,
            "company_ids": [Command.link(company.id)],
            "group_ids": [Command.link(group.id)],
        } for label in ("First", "Second")])
        config = env["pos.config"].create({"name": "Shift Race " + suffix, "cash_control": False})
        now = fields.Datetime.now()
        source = env["pos.session"].create({
            "config_id": config.id, "user_id": users[0].id, "state": "closed",
            "start_at": now - timedelta(days=2), "stop_at": now - timedelta(days=1),
        })
        target = env["pos.session"].create({
            "config_id": config.id, "user_id": users[1].id, "state": "opened",
            "start_at": now - timedelta(hours=1),
        })
        handover = env["cyfr.pos.handover"].with_user(users[0]).create({
            "source_session_id": source.id,
        })
        ids = {"users": users.ids, "partners": users.partner_id.ids,
               "config": config.id, "source": source.id, "target": target.id,
               "handover": handover.id}
        result["actor_ids"] = users.ids
        result["target_session_id"] = target.id
        env.cr.commit()

        with env.registry.cursor() as first_cr:
            first = api.Environment(first_cr, ids["users"][0], {})
            with env.registry.cursor() as second_cr:
                second = api.Environment(second_cr, ids["users"][1], {})
                assert first.user.has_group("point_of_sale.group_pos_user")
                assert second.user.has_group("point_of_sale.group_pos_user")
                result["two_pos_users"] = first.uid != second.uid
                first["cyfr.pos.handover"].browse(ids["handover"]).action_claim()
                try:
                    second["cyfr.pos.handover"].browse(ids["handover"]).action_claim()
                except UserError as exc:
                    result["lock_retry"] = "Retry shortly" in str(exc)
                else:
                    raise AssertionError("Second POS user claimed while the first transaction held the lock")
            first_cr.commit()

        with env.registry.cursor() as retry_cr:
            retry = api.Environment(retry_cr, ids["users"][1], {})
            row = retry["cyfr.pos.handover"].browse(ids["handover"])
            try:
                row.action_claim()
            except UserError as exc:
                result["loser_rejected_after_commit"] = "already been claimed" in str(exc)
            else:
                raise AssertionError("Second POS user replaced the recorded recipient")
            row.invalidate_recordset()
            result["one_recipient"] = (row.target_session_id.id == ids["target"]
                                       and row.claimed_by_id.id == ids["users"][0]
                                       and bool(row.claimed_at))
        assert all(result[k] for k in ("two_pos_users", "lock_retry",
                                       "loser_rejected_after_commit", "one_recipient")), result
    finally:
        if ids:
            env.invalidate_all()
            env["cyfr.pos.handover"].browse(ids["handover"]).unlink()
            env["pos.session"].browse([ids["target"], ids["source"]]).unlink()
            env["pos.config"].browse(ids["config"]).unlink()
            env["res.users"].browse(ids["users"]).unlink()
            env["res.partner"].browse(ids["partners"]).unlink()
            env.cr.commit()
            env.invalidate_all()
            result["cleaned"] = not any((
                env["cyfr.pos.handover"].browse(ids["handover"]).exists(),
                env["pos.session"].browse([ids["target"], ids["source"]]).exists(),
                env["pos.config"].browse(ids["config"]).exists(),
                env["res.users"].browse(ids["users"]).exists(),
                env["res.partner"].browse(ids["partners"]).exists(),
            ))
    result["demo_unchanged"] = demo.read(["target_session_id", "claimed_by_id", "claimed_at"])[0] == demo_before
    assert result["cleaned"], result
    assert result["demo_unchanged"], result
    return result


print("SHIFT_CLAIM_RACE " + json.dumps(run_claim_race(env), sort_keys=True))
