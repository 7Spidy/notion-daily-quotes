#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
morning_run.py — 3 AM IST daily run

WHAT THIS REPLACES: morning_insight.py
WHAT'S DIFFERENT:
  - Runs at 3 AM (not midnight) so both yesterday's journal entries are complete
  - Multi-agent pipeline: Orchestrator → Context → Planning → Review
  - Temporal labels on journal entries ("Yesterday morning (6:30 AM)")
  - Queries completed tasks from last 24h (new — was invisible before)
  - Vacant slot detection replaced with actual time-gap computation
  - Calendar block suggestions written to Notion for approval
  - Memory saved with correct property names + Type + Source
  - Sunday: also runs TechAuditAgent and memory consolidation
"""

from utils import NotionClient, CalendarClient, format_ist, get_ist_now
from agents import OrchestratorAgent, ContextAgent, PlanningAgent, ReviewAgent, TechAuditAgent


def run():
    notion   = NotionClient()
    calendar = CalendarClient()
    now      = get_ist_now()

    print(f"\n{'═'*60}")
    print(f"  Life OS · Morning Run (3 AM IST)")
    print(f"  {format_ist(now)}")
    print(f"{'═'*60}\n")

    # ── Step 1: Load agent instructions + memory (before anything else) ───────
    print("📖 Loading agent instructions and memory…")
    ai_instructions = notion.get_agent_instructions()
    memories        = notion.get_agent_memories(limit=15)
    print(f"  Instructions: {len(ai_instructions)} chars | Memories: {len(memories)} entries")

    # ── Step 2: Find existing Notion blocks + read feedback comments ──────────
    print("\n💬 Finding existing blocks…")
    insight_block_id  = notion.find_block_by_marker("☀️ Morning Insight")
    briefing_block_id = notion.find_block_by_marker("🌅 Daily Insight")
    queue_block_id    = notion.find_block_by_marker("📅 Calendar Queue")

    insight_feedback  = notion.get_block_comments(insight_block_id)  if insight_block_id  else []
    briefing_feedback = notion.get_block_comments(briefing_block_id) if briefing_block_id else []
    all_feedback = insight_feedback + briefing_feedback

    print(f"  Morning Insight block: {'found' if insight_block_id else 'will create'}")
    print(f"  Daily Insight block:   {'found' if briefing_block_id else 'will create'}")
    print(f"  Calendar Queue block:  {'found' if queue_block_id else 'will create'}")
    print(f"  User feedback comments: {len(all_feedback)}")

    # ── Step 3: Fetch all data ────────────────────────────────────────────────
    print("\n📅 Fetching calendar events…")
    calendar_events = calendar.get_today_events()
    vacant_slots    = calendar.get_vacant_slots(calendar_events)
    print(f"  {len(calendar_events)} events | {len(vacant_slots)} vacant slot(s)")

    print("\n📋 Fetching task data…")
    pending_tasks   = notion.get_pending_tasks()
    completed_today = notion.get_tasks_completed_last_24h()
    print(f"  Pending: {len(pending_tasks)} | Completed last 24h: {len(completed_today)}")

    print("\n🎯 Fetching strategic goals…")
    strategic_goals = notion.get_strategic_goals()
    print(f"  {len(strategic_goals)} goals")

    print("\n📝 Fetching journal entries (last 7 days)…")
    journal_entries = notion.get_journal_entries(days_back=7, limit=8)
    # Log the date labels so you can see the temporal fix working in the GitHub logs
    for e in journal_entries[:4]:
        print(f"  [{e['date_label']}] {e['title']}")

    # ── Step 4: Multi-agent pipeline ──────────────────────────────────────────
    run_date    = now.strftime("%B %d, %Y")
    day_of_year = now.timetuple().tm_yday
    day_of_week = now.strftime("%A")

    print("\n🧠 Agent pipeline starting…")

    # 4a. Orchestrator: set the agenda
    orchestrator = OrchestratorAgent()
    orchestrator_brief = orchestrator.run(
        pending_tasks    = pending_tasks,
        completed_today  = completed_today,
        strategic_goals  = strategic_goals,
        calendar_events  = calendar_events,
        memories         = memories,
        ai_instructions  = ai_instructions,
        run_date         = run_date,
    )
    print(f"\n  Orchestrator brief preview: {orchestrator_brief[:80]}…")

    # 4b. Context Agent: synthesise what happened with temporal accuracy
    context_agent = ContextAgent()
    context_synthesis = context_agent.run(
        journal_entries    = journal_entries,
        completed_today    = completed_today,
        pending_tasks      = pending_tasks,
        strategic_goals    = strategic_goals,
        orchestrator_brief = orchestrator_brief,
        ai_instructions    = ai_instructions,
    )

    # 4c. Planning Agent: create the morning insight + daily briefing + suggestions
    planning_agent = PlanningAgent()
    plan = planning_agent.run(
        context_synthesis  = context_synthesis,
        orchestrator_brief = orchestrator_brief,
        calendar_events    = calendar_events,
        vacant_slots       = vacant_slots,
        pending_tasks      = pending_tasks,
        ai_instructions    = ai_instructions,
        day_of_year        = day_of_year,
        current_year       = now.year,
        day_of_week        = day_of_week,
        user_feedback      = all_feedback,
    )

    # 4d. Review Agent: validate facts, format, and generate memory observation
    review_agent = ReviewAgent()
    final = review_agent.run(
        morning_insight  = plan["morning_insight"],
        daily_briefing   = plan["daily_briefing"],
        context_synthesis= context_synthesis,
        ai_instructions  = ai_instructions,
        pending_tasks    = pending_tasks,
        completed_today  = completed_today,
        strategic_goals  = strategic_goals,
    )

    # ── Step 5: Write to Notion ───────────────────────────────────────────────
    print("\n📝 Writing to Notion…")

    notion.write_callout(
        content     = final["morning_insight"],
        emoji       = "☀️",
        color       = "orange_background",
        marker      = "☀️ Morning Insight",
        existing_id = insight_block_id,
    )

    notion.write_callout(
        content     = final["daily_briefing"],
        emoji       = "🌅",
        color       = "blue_background",
        marker      = "🌅 Daily Insight",
        existing_id = briefing_block_id,
    )

    # Freeze the journal prompt into today's Daily Journal entry.
    # The homepage callout above still receives the full morning_insight string
    # (stoic line + prompt) unchanged. Here we extract only the prompt half so
    # the journal page gets a clean, standalone prompt rather than the full text.
    PROMPT_MARKER = "📝 Journal Prompt:"
    morning_insight_text = final["morning_insight"]
    if PROMPT_MARKER in morning_insight_text:
        _, after_marker = morning_insight_text.split(PROMPT_MARKER, 1)
        journal_prompt = f"{PROMPT_MARKER}{after_marker.rstrip()}"
    else:
        journal_prompt = morning_insight_text  # fallback: whole string if marker absent

    print("\n📝 Freezing journal prompt into today's Daily Journal entry…")
    notion.freeze_prompt_into_journal(journal_prompt)

    # Write calendar block suggestions if the planning agent found any
    if plan["calendar_suggestions"]:
        print(f"\n📅 Writing {len(plan['calendar_suggestions'])} calendar suggestion(s) to Notion…")
        notion.write_calendar_queue(
            suggestions  = plan["calendar_suggestions"],
            existing_id  = queue_block_id,
        )
    else:
        print("\n  ℹ️  No vacant slots suitable for calendar blocking today")

    # ── Step 6: Save memory observation ──────────────────────────────────────
    if final.get("memory_text"):
        print("\n🧠 Saving memory observation…")
        notion.save_memory(
            memory_text = final["memory_text"],
            detail      = final.get("memory_detail", context_synthesis[:500]),
            memory_type = "Pattern",
            source      = "Agent Auto",
        )

    # ── Step 7: Sunday extras — tech audit + memory consolidation ────────────
    if day_of_week == "Sunday":
        print("\n🔧 Sunday: Running Tech Audit Agent…")
        tech_audit = TechAuditAgent()
        audit_report = tech_audit.run(
            recent_memories = memories,
            ai_instructions = ai_instructions,
        )
        notion.write_callout(
            content     = audit_report,
            emoji       = "🔧",
            color       = "gray_background",
            marker      = "🔧 System Audit",
            existing_id = notion.find_block_by_marker("🔧 System Audit"),
        )

        print("\n🗂️  Running weekly memory consolidation…")
        notion.refactor_old_memories()
    else:
        print(f"\n  ℹ️  Not Sunday — skipping audit and memory consolidation")

    print(f"\n✅ Morning run complete · {format_ist()}\n")


if __name__ == "__main__":
    run()
