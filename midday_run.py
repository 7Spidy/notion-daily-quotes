#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
midday_run.py — 1 PM IST daily run

Two jobs:
  1. Check if approved calendar blocks are waiting in Notion → create them
  2. Check pending tasks → send Discord nudge if anything is overdue

Deliberately lightweight. No Orchestrator. No Context Agent. Just:
  NudgeAgent → Discord
  CalendarClient.create_event() → Google Calendar
"""

from utils import NotionClient, CalendarClient, DiscordClient, format_ist, get_ist_now
from agents import NudgeAgent


def run():
    notion   = NotionClient()
    calendar = CalendarClient()
    discord  = DiscordClient()
    now      = get_ist_now()

    print(f"\n{'═'*60}")
    print(f"  Life OS · Midday Run (1 PM IST)")
    print(f"  {format_ist(now)}")
    print(f"{'═'*60}\n")

    # ── Load instructions (for nudge personalisation) ─────────────────────────
    ai_instructions = notion.get_agent_instructions()

    # ── Job 1: Process approved calendar blocks ───────────────────────────────
    print("📅 Checking Calendar Queue for approved blocks…")
    queue_block_id = notion.find_block_by_marker("📅 Calendar Queue")

    if queue_block_id:
        approved = notion.get_approved_calendar_blocks(queue_block_id)
        print(f"  {len(approved)} approved block(s) found")

        created = []
        for item in approved:
            success = calendar.create_event(
                title       = item["title"],
                start_hhmm  = item["start"],
                end_hhmm    = item["end"],
            )
            if success:
                created.append(item)
                # Archive the processed to_do block so it doesn't get double-created
                notion.archive_block(item["block_id"])

        if created:
            titles = ', '.join(f"{c['start']}: {c['title']}" for c in created)
            print(f"  ✅ Created {len(created)} calendar event(s): {titles}")
        else:
            print("  ℹ️  No new events to create")
    else:
        print("  ℹ️  No Calendar Queue block found on Notion page")

    # ── Job 2: Task status check + Discord nudge ──────────────────────────────
    print("\n📋 Checking task status…")
    pending_tasks   = notion.get_pending_tasks()
    completed_today = notion.get_tasks_completed_last_24h()
    calendar_events = calendar.get_today_events()

    print(f"  Pending: {len(pending_tasks)} | Completed today: {len(completed_today)}")

    # Only nudge if there are pending tasks. If everything's done, the user
    # doesn't need a distraction — just a brief "all good" would be overkill.
    if pending_tasks and pending_tasks != ["No pending tasks"]:
        print("\n🤖 Generating midday nudge…")
        nudge_agent = NudgeAgent()
        message = nudge_agent.run_midday(
            pending_tasks    = pending_tasks,
            completed_today  = completed_today,
            remaining_events = calendar_events,
            ai_instructions  = ai_instructions,
        )
        discord.send(message)
    else:
        print("\n  ✅ No pending tasks — skipping nudge")
        discord.send(
            f"🔔 Midday Check-In · {now.strftime('%I:%M %p')}\n\n"
            f"✅ All tasks clear. Solid morning — enjoy the rest of the day."
        )

    print(f"\n✅ Midday run complete · {format_ist()}\n")


if __name__ == "__main__":
    run()
