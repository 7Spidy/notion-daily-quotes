#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agents.py — Multi-agent pipeline for Life OS Automation

Each agent is a focused Claude call with a specific job.
They run sequentially (not in parallel) to avoid rate limits and
to let each agent build on the previous one's output.

Flow per morning run:
  Orchestrator → Context Agent → Planning Agent → Review Agent

Flow on Sundays (in addition to morning run):
  Tech Audit Agent
"""

from anthropic import Anthropic
from datetime import datetime
from utils import get_ist_now, format_ist

client = Anthropic()


def _call_claude(
    prompt: str,
    system: str = "",
    max_tokens: int = 500,
    label: str = ""
) -> str:
    """
    Single Claude API call. All agents use this.
    Returns the text response, stripped of leading/trailing whitespace.
    """
    kwargs = {
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    try:
        print(f"  🤖 {label or 'Claude'} call…")
        resp = client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        print(f"  ✅ {label or 'Done'} ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"  ❌ Claude call failed ({label}): {e}")
        return ""


# ─── Orchestrator Agent ────────────────────────────────────────────────────────

class OrchestratorAgent:
    """
    The meta-agent. Reads the raw data and writes a "director's note" for
    the other agents — what to prioritise, what patterns to highlight,
    what to avoid repeating from recent memory.

    It does NOT write any user-facing content. Its output is internal
    context passed to Context → Planning → Review.
    """

    def run(
        self,
        pending_tasks: list[str],
        completed_today: list[str],
        strategic_goals: list[str],
        calendar_events: list[dict],
        memories: list[str],
        ai_instructions: str,
        run_date: str,
    ) -> str:
        now = get_ist_now()
        day_of_week = now.strftime("%A")
        active_goals = [g for g in strategic_goals if "In Progress" in g]
        done_goals   = [g for g in strategic_goals if "Done" in g]
        calendar_summary = "; ".join(
            f"{e['time']} {e['category']}: {e['summary']}" for e in calendar_events[:5]
        )

        prompt = f"""You are the orchestrator for Avinash's Life OS. Today is {day_of_week}, {run_date}.

Your job: Write a 4-6 sentence internal "director's note" for the other agents.
Tell them what matters today, what to focus on, what to skip. Be specific — reference actual data.

Raw data:
- Completed in last 24h: {', '.join(completed_today) if completed_today else 'Nothing recorded'}
- Still pending: {', '.join(pending_tasks[:5]) if pending_tasks else 'None'}
- Active goals: {', '.join(active_goals[:3]) if active_goals else 'None'}
- Recently done goals: {', '.join(done_goals[:2]) if done_goals else 'None'}
- Today's calendar: {calendar_summary or 'Empty'}
- Recent memory context: {'; '.join(memories[:5]) if memories else 'None'}

Write 4-6 sentences. Be direct. This note guides the other agents — not the user."""

        result = _call_claude(
            prompt,
            system=ai_instructions,
            max_tokens=200,
            label="Orchestrator"
        )
        return result or f"Today is {day_of_week}. Focus on pending tasks and active goals."


# ─── Context Agent ─────────────────────────────────────────────────────────────

class ContextAgent:
    """
    Synthesises raw data into a structured "state of life" summary.

    This is where the temporal fix matters most. The agent receives journal
    entries with labels like "Yesterday morning (6:30 AM)" and "Yesterday evening
    (8:00 PM)" so it can accurately summarise what happened vs what's current.

    Output is a prose synthesis used by the Planning Agent as its primary input.
    """

    def run(
        self,
        journal_entries: list[dict],
        completed_today: list[str],
        pending_tasks: list[str],
        strategic_goals: list[str],
        orchestrator_brief: str,
        ai_instructions: str,
    ) -> str:

        # Format journal entries with date labels (THE KEY CHANGE)
        journal_text = "\n".join(
            f"  [{e['date_label']}] {e['title']}"
            + (f" ({', '.join(e['life_areas'])})" if e['life_areas'] else "")
            + f":\n  {e['content'][:300]}"
            for e in journal_entries[:6]
        ) or "No recent journal entries."

        prompt = f"""You are the Context Agent for Avinash's Life OS.

Orchestrator direction: {orchestrator_brief}

Your job: Write a 150-200 word synthesis of Avinash's current state.
Use the exact date labels given — they distinguish between events that happened
yesterday morning vs yesterday evening vs 2 days ago. This temporal accuracy matters.

JOURNAL ENTRIES (with temporal labels):
{journal_text}

COMPLETED IN LAST 24 HOURS: {', '.join(completed_today) if completed_today else 'None recorded'}
STILL PENDING: {', '.join(pending_tasks[:5]) if pending_tasks else 'None'}
ACTIVE GOALS: {'; '.join(g for g in strategic_goals if 'In Progress' in g) or 'None'}

Structure your synthesis:
1. What happened (reference specific journal entries with their date labels)
2. What was completed (celebrate any wins from last 24h)
3. What's in progress (goals + pending tasks)
4. Key themes or patterns you notice

Write plain prose, no headers, no bullets. 150-200 words."""

        result = _call_claude(
            prompt,
            system=ai_instructions,
            max_tokens=350,
            label="Context Agent"
        )
        return result or "Context synthesis unavailable."


# ─── Planning Agent ─────────────────────────────────────────────────────────────

class PlanningAgent:
    """
    Takes the context synthesis and creates all user-facing content:
      - Morning Insight (stoic + journal prompt)
      - Daily Briefing (5-part strategic brief)
      - Calendar block suggestions (for approval via Notion)

    The calendar suggestions are returned as a structured list, separate from
    the briefing text, so they can be written as to_do blocks in Notion.
    """

    def run(
        self,
        context_synthesis: str,
        orchestrator_brief: str,
        calendar_events: list[dict],
        vacant_slots: list[dict],
        pending_tasks: list[str],
        ai_instructions: str,
        day_of_year: int,
        current_year: int,
        day_of_week: str,
        user_feedback: list[str],
    ) -> dict:
        """
        Returns a dict with:
          morning_insight: str
          daily_briefing: str
        """
        calendar_lines = "\n".join(
            f"  {e['time']} {e['category']}: {e['summary']}"
            for e in calendar_events
        ) or "  No events today"

        vacant_lines = "\n".join(
            f"  {s['start']}–{s['end']} ({s['duration_h']}h free)"
            for s in vacant_slots
        ) or "  No clear gaps found"

        feedback_section = ""
        if user_feedback:
            feedback_section = (
                f"\n\nUser feedback on previous briefings (use to improve): "
                f"{'; '.join(user_feedback)}"
            )

        prompt = f"""You are the Planning Agent for Avinash's Life OS.
Today is {day_of_week}, Day {day_of_year} of {current_year}.

CONTEXT SYNTHESIS (from Context Agent):
{context_synthesis}

ORCHESTRATOR DIRECTION:
{orchestrator_brief}

TODAY'S CALENDAR:
{calendar_lines}
Color key: 🔴 Fun/Play  🔵 Office  🟢 Health  🟡 Chores  ⚪ Other

VACANT SLOTS TODAY:
{vacant_lines}
{feedback_section}

Your job: Create three things.

═══ PART 1 — MORNING INSIGHT ═══
Two parts, separated by a blank line. No headers, no markdown.

Part 1 (Stoic): Start with "Day {day_of_year} of {current_year}." then one profound sentence about time, mortality, or intentional living. Under 20 words total.

Part 2 (Journal): "📝 Journal Prompt:" then an uplifting, non-work prompt. Relate to {day_of_week}'s energy. Under 30 words.

═══ PART 2 — DAILY BRIEFING ═══
Exactly 5 numbered insights. Plain text only (no **, no headers).
Under 850 characters total. Vary sentence structure.

1. What happened + progress made (reference journal with temporal labels from the context synthesis)
2. ONE task to focus on today (from pending: {', '.join(pending_tasks[:3])})
3. ONE action toward a strategic goal
4. How to use vacant time slots (be specific with times from VACANT SLOTS)
5. ONE relaxing or enjoyable activity suggestion

Output exactly this structure:
MORNING_INSIGHT:
[content]
---BRIEFING---
[5-part briefing content]"""

        raw = _call_claude(
            prompt,
            system=ai_instructions,
            max_tokens=1200,
            label="Planning Agent"
        )

        return self._parse_output(raw, day_of_year, current_year)

    def _parse_output(self, raw: str, day_of_year: int, current_year: int) -> dict:
        """Parses the Planning Agent's structured output into components."""

        result = {
            "morning_insight": "",
            "daily_briefing": "",
        }

        if not raw:
            return result

        # Split on section marker
        parts = raw.split("---BRIEFING---")
        if len(parts) >= 1:
            insight_part = parts[0].replace("MORNING_INSIGHT:", "").strip()
            result["morning_insight"] = insight_part

        if len(parts) >= 2:
            result["daily_briefing"] = parts[1].strip()

        # Fallback if parsing failed
        if not result["morning_insight"]:
            result["morning_insight"] = (
                f"Day {day_of_year} of {current_year}. Time moves regardless of intention — "
                f"act before the day decides for you.\n\n"
                f"📝 Journal Prompt: What small thing today deserves more appreciation than you've given it?"
            )
        if not result["daily_briefing"]:
            result["daily_briefing"] = (
                "1. Context synthesis unavailable for this run.\n\n"
                "2. Start with the first pending task on your checklist.\n\n"
                "3. Take one small action toward your most active goal.\n\n"
                "4. Use any free time for focused work or creative thinking.\n\n"
                "5. End the day with something you genuinely enjoy."
            )

        return result


# ─── Review Agent ──────────────────────────────────────────────────────────────

class ReviewAgent:
    """
    Quality gate before content hits Notion.

    Checks:
    1. No hallucinated facts (dates, task names, goal names must match context)
    2. Morning Insight has exactly 2 parts
    3. Daily Briefing has exactly 5 numbered points
    4. Briefing is under 850 characters
    5. No markdown formatting (no **, no #)

    Also generates the memory observation to save to the Memory DB.
    """

    def run(
        self,
        morning_insight: str,
        daily_briefing: str,
        context_synthesis: str,
        ai_instructions: str,
        pending_tasks: list[str],
        completed_today: list[str],
        strategic_goals: list[str],
    ) -> dict:
        """
        Returns:
          morning_insight: validated/corrected str
          daily_briefing:  validated/corrected str
          memory_text:     str for Memory DB (title field, ~80 words)
          memory_detail:   str for Memory DB (detail field, extended context)
        """
        now = get_ist_now()

        prompt = f"""You are the Quality Review Agent for Avinash's Life OS.
Today is {now.strftime('%A, %B %d, %Y')}.

VERIFIED CONTEXT (ground truth — do not let the drafts contradict this):
{context_synthesis}

MORNING INSIGHT DRAFT:
{morning_insight}

DAILY BRIEFING DRAFT:
{daily_briefing}

Your job:
1. Check both drafts against the verified context. Fix any hallucinated facts.
2. Ensure Morning Insight has exactly 2 parts (stoic sentence + journal prompt).
3. Ensure Daily Briefing has exactly 5 numbered points.
4. Ensure briefing is under 850 characters total.
5. Remove any **, *, or markdown formatting.
6. Write one memory observation (max 80 words, plain text) that captures:
   - What was notable about today's data
   - Key patterns, goals, task status
   - Context useful for future runs

Output exactly this format:
MORNING_INSIGHT:
[final content]
---
DAILY_BRIEFING:
[final content]
---
MEMORY:
[80-word observation]"""

        raw = _call_claude(
            prompt,
            system=ai_instructions,
            max_tokens=1000,
            label="Review Agent"
        )

        return self._parse(raw, morning_insight, daily_briefing, context_synthesis)

    def _parse(
        self,
        raw: str,
        fallback_insight: str,
        fallback_briefing: str,
        context_synthesis: str,
    ) -> dict:
        result = {
            "morning_insight": fallback_insight,
            "daily_briefing":  fallback_briefing,
            "memory_text":     "",
            "memory_detail":   context_synthesis[:500],
        }
        if not raw:
            return result

        sections = raw.split("---")
        for section in sections:
            if section.strip().startswith("MORNING_INSIGHT:"):
                result["morning_insight"] = section.replace("MORNING_INSIGHT:", "").strip()
            elif section.strip().startswith("DAILY_BRIEFING:"):
                result["daily_briefing"] = section.replace("DAILY_BRIEFING:", "").strip()
            elif section.strip().startswith("MEMORY:"):
                result["memory_text"] = section.replace("MEMORY:", "").strip()

        return result


# ─── Tech Audit Agent (Sunday only) ───────────────────────────────────────────

class TechAuditAgent:
    """
    Weekly code + system health review. Runs Sunday morning after the main run.

    Reads:
    - Last 7 agent memory entries (for error patterns, output quality)
    - Key sections of the codebase (files are on disk during GitHub Actions run)

    Writes a "🔧 System Audit" callout to Notion with health status and
    any suggested code improvements.

    This is the "technical changes" agent the user requested — it analyses
    whether the automation code itself needs updates.
    """

    MAX_CODE_CHARS = 3000  # Limit code context to avoid token overuse

    def read_code_snapshot(self) -> str:
        """Reads key functions from the codebase for the audit."""
        files_to_check = ["morning_run.py", "agents.py", "utils.py"]
        snapshot = []
        for fname in files_to_check:
            try:
                with open(fname, 'r') as f:
                    content = f.read()
                snapshot.append(f"=== {fname} ({len(content)} chars) ===\n{content[:1000]}")
            except FileNotFoundError:
                snapshot.append(f"=== {fname} === [not found]")
        return "\n\n".join(snapshot)[:self.MAX_CODE_CHARS]

    def run(self, recent_memories: list[str], ai_instructions: str) -> str:
        code_snapshot = self.read_code_snapshot()

        # Look for error patterns in memory
        error_memories = [m for m in recent_memories if any(
            kw in m.lower() for kw in ['error', 'failed', 'unavailable', 'timeout', 'http']
        )]

        prompt = f"""You are the Technical Audit Agent for Avinash's Life OS automation.

Your job: Review last week's performance and the codebase. Produce a concise audit.

RECENT MEMORY ENTRIES (last 7 days, most recent first):
{chr(10).join(f'  • {m}' for m in recent_memories[:7]) or '  None available'}

ERROR PATTERNS DETECTED IN MEMORY:
{chr(10).join(f'  ⚠️ {m}' for m in error_memories[:3]) or '  None detected'}

CODE SNAPSHOT (key sections):
{code_snapshot}

Write an audit report (under 250 words) with:

System Health: [Good / Needs Attention / Critical]

Issues found (if any):
[List specific issues. Reference function names if relevant.]

Suggested improvements (if any):
[Concrete, specific. Reference what to change and why.]

Outlook:
[1-2 sentences on overall system quality]

Be direct. Only flag real issues. If everything looks fine, say so briefly."""

        result = _call_claude(
            prompt,
            system=ai_instructions,
            max_tokens=400,
            label="Tech Audit Agent"
        )
        return result or "System Health: Good\n\nNo issues detected this week."
