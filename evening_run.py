#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evening_run.py — 7 PM IST daily run

Two outputs:
  1. Discord message — evening wrap-up with completed/pending tasks + journal reminder
  2. Notion callout — 🌙 Evening Summary block on the dashboard page (same content)

Bugs fixed:
  - CalendarClient was imported but never used (removed)
  - NotionClient() crashed because NOTION_PAGE_ID was missing from the workflow env
    (fixed in utils.py __init__ — now uses os.getenv with empty string default)
  - No Notion write at 7 PM existed at all (added below)
"""

from utils import NotionClient, DiscordClient, format_ist, get_ist_now
from agents import NudgeAgent


def run():
    notion  = NotionClient()
    discord = DiscordClient()
    now     = get_ist_now()

    print(f"\n{'═'*60}")
    print(f"  Life OS · Evening Run (7 PM IST)")
    print(f"  {format_ist(now)}")
    print(f"{'═'*60}\n")

    # ── Load instructions ──────────────────────────────────────────────────────
    ai_instructions = notion.get_agent_instructions()

    # ── Fetch task data ────────────────────────────────────────────────────────
    print("📋 Checking task status…")
    pending_tasks   = notion.get_pending_tasks()
    completed_today = notion.get_tasks_completed_last_24h()
    print(f"  Pending: {len(pending_tasks)} | Completed today: {len(completed_today)}")

    # ── Generate evening wrap-up message ───────────────────────────────────────
    print("\n🤖 Generating evening wrap-up…")
    nudge_agent = NudgeAgent()
    message = nudge_agent.run_evening(
        pending_tasks   = pending_tasks,
        completed_today = completed_today,
        ai_instructions = ai_instructions,
    )

    # ── Send to Discord ────────────────────────────────────────────────────────
    print("\n💬 Sending to Discord…")
    discord.send(message)

    # ── Write to Notion dashboard ──────────────────────────────────────────────
    # Writes the same content as the Discord message into a 🌙 callout block on
    # the dashboard page. This is the Notion alert the user expected at 7 PM.
    print("\n📝 Writing evening summary to Notion…")
    if notion.page_id:
        existing_evening_id = notion.find_block_by_marker("🌙 Evening Summary")
        notion.write_callout(
            content     = message,
            emoji       = "🌙",
            color       = "purple_background",
            marker      = "🌙 Evening Summary",
            existing_id = existing_evening_id,
        )
    else:
        print("  ⚠️  NOTION_PAGE_ID not set — skipping Notion write")

    # ── Save brief memory observation ─────────────────────────────────────────
    if completed_today:
        pending_note = (
            f"{len(pending_tasks)} still open"
            if pending_tasks and pending_tasks != ["No pending tasks"]
            else "all clear"
        )
        observation = (
            f"{now.strftime('%Y-%m-%d')} evening: Completed "
            f"{len(completed_today)} task(s): {', '.join(completed_today[:3])}. "
            f"Task status at 7 PM — {pending_note}."
        )
        notion.save_memory(
            memory_text = observation,
            memory_type = "Pattern",
            source      = "Agent Auto",
        )

    print(f"\n✅ Evening run complete · {format_ist()}\n")


if __name__ == "__main__":
    run()
