#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evening_run.py — 7 PM IST daily run

One job: send an evening wrap-up to Discord that:
  - Celebrates what was completed today
  - Notes anything still open (for tomorrow, not as guilt)
  - Reminds you that your 8 PM journal entry is due
  - Gives a journal prompt relevant to today

Lightweight by design. No Orchestrator, no Notion writes.
The evening journal entry itself will be picked up in tomorrow's 3 AM context synthesis.
"""

from utils import NotionClient, CalendarClient, DiscordClient, format_ist, get_ist_now
from agents import NudgeAgent


def run():
    notion   = NotionClient()
    calendar = CalendarClient()
    discord  = DiscordClient()
    now      = get_ist_now()

    print(f"\n{'═'*60}")
    print(f"  Life OS · Evening Run (7 PM IST)")
    print(f"  {format_ist(now)}")
    print(f"{'═'*60}\n")

    # ── Load instructions ──────────────────────────────────────────────────────
    ai_instructions = notion.get_agent_instructions()

    # ── Fetch data ─────────────────────────────────────────────────────────────
    print("📋 Checking task status…")
    pending_tasks   = notion.get_pending_tasks()
    completed_today = notion.get_tasks_completed_last_24h()
    print(f"  Pending: {len(pending_tasks)} | Completed today: {len(completed_today)}")

    # ── Generate and send evening nudge ───────────────────────────────────────
    print("\n🤖 Generating evening wrap-up…")
    nudge_agent = NudgeAgent()
    message = nudge_agent.run_evening(
        pending_tasks   = pending_tasks,
        completed_today = completed_today,
        ai_instructions = ai_instructions,
    )

    discord.send(message)

    # ── Save a brief evening memory observation ────────────────────────────────
    # This captures the day's completion status — useful context for tomorrow's run.
    if completed_today:
        completed_summary = f"Completed {len(completed_today)} task(s): {', '.join(completed_today[:3])}"
        pending_summary   = f"{len(pending_tasks)} still open" if pending_tasks and pending_tasks != ['No pending tasks'] else "all clear"
        observation = (
            f"{now.strftime('%Y-%m-%d')} evening: {completed_summary}. "
            f"Task status at 7PM — {pending_summary}."
        )
        notion.save_memory(
            memory_text = observation,
            memory_type = "Pattern",
            source      = "Agent Auto",
        )

    print(f"\n✅ Evening run complete · {format_ist()}\n")


if __name__ == "__main__":
    run()
