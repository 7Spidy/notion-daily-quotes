#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agents.py — Agent pipeline for Life OS Automation

Daily morning run uses a single consolidated DailyAgent (one Claude call).
Sunday additionally runs TechAuditAgent after the main run.
"""

import re
from anthropic import Anthropic
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


# ─── Daily Agent ───────────────────────────────────────────────────────────────

class DailyAgent:
    """
    Single consolidated Claude call replacing the old 4-agent pipeline
    (Orchestrator → Context → Planning → Review).

    One prompt produces Morning Insight, Daily Briefing, and Memory observation.
    Python-based structural validation replaces the Review Agent's checking role.
    """

    def run(
        self,
        journal_entries: list[dict],
        completed_today: list[str],
        pending_tasks: list[str],
        strategic_goals: list[str],
        calendar_events: list[dict],
        vacant_slots: list[dict],
        memories: list[str],
        ai_instructions: str,
        user_feedback: list[str],
        run_date: str,
        day_of_year: int,
        current_year: int,
        day_of_week: str,
    ) -> dict:
        # Store for fallback helpers
        self._day_of_year = day_of_year
        self._current_year = current_year

        # Format journal entries with date labels (temporal accuracy preserved)
        journal_text = "\n".join(
            f"  [{e['date_label']}] {e['title']}"
            + (f" ({', '.join(e['life_areas'])})" if e['life_areas'] else "")
            + f":\n  {e['content'][:300]}"
            for e in journal_entries[:6]
        ) or "No recent journal entries."

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

        active_goals = [g for g in strategic_goals if "In Progress" in g]
        memory_context = "; ".join(memories[:5]) if memories else "None"

        prompt = f"""You are Avinash's Life OS daily agent. Today is {day_of_week}, {run_date} (Day {day_of_year} of {current_year}).

JOURNAL ENTRIES (with temporal labels — use these exactly when referencing events):
{journal_text}

COMPLETED IN LAST 24 HOURS: {', '.join(completed_today) if completed_today else 'Nothing recorded'}
PENDING TASKS: {', '.join(pending_tasks[:5]) if pending_tasks else 'None'}
ACTIVE GOALS: {'; '.join(active_goals[:3]) if active_goals else 'None'}
RECENT MEMORY CONTEXT: {memory_context}

TODAY'S CALENDAR:
{calendar_lines}
Color key: 🔴 Fun/Play  🔵 Office  🟢 Health  🟡 Chores  ⚪ Other

VACANT SLOTS TODAY:
{vacant_lines}{feedback_section}

Your job: Produce three things in one response.

═══ PART 1 — MORNING INSIGHT ═══
Two parts separated by a blank line. No headers, no markdown symbols (no **, no *, no #).

Part 1 (Stoic): Start with "Day {day_of_year} of {current_year}." then one profound sentence about time, mortality, or intentional living. Under 20 words total.

Part 2 (Journal): "📝 Journal Prompt:" then an uplifting, non-work prompt. Relate to {day_of_week}'s energy. Under 30 words.

═══ PART 2 — DAILY BRIEFING ═══
Exactly 5 numbered insights. Plain text only (no **, no *, no # headers).
Under 850 characters total. Only reference tasks, goals, and journal entries given above — do not invent facts.

1. What happened + progress made (reference journal entries with their temporal date labels)
2. ONE task to focus on today (from pending tasks above)
3. ONE action toward a strategic goal
4. How to use vacant time slots (be specific with times from VACANT SLOTS)
5. ONE relaxing or enjoyable activity suggestion

═══ PART 3 — MEMORY ═══
One memory observation (max 80 words, plain text) capturing what was notable today: key patterns, goal status, task context useful for future runs.

Output EXACTLY this structure — no extra text before or after:
MORNING_INSIGHT:
[content]
---BRIEFING---
DAILY_BRIEFING:
[content]
---MEMORY---
MEMORY:
[content]"""

        raw_prompt_kwargs = {
            "prompt": prompt,
            "system": ai_instructions,
            "max_tokens": 1400,
            "label": "Daily Agent",
        }

        return self._get_validated_output(raw_prompt_kwargs)

    def _parse_output(self, raw: str) -> dict:
        """Parses the structured output and strips markdown symbols."""
        result = {
            "morning_insight": "",
            "daily_briefing": "",
            "memory_text": "",
            "memory_detail": "",
        }
        if not raw:
            return result

        parts = raw.split("---BRIEFING---")
        if len(parts) >= 1:
            insight = parts[0].replace("MORNING_INSIGHT:", "").strip()
            result["morning_insight"] = re.sub(r'[\*#]+', '', insight)

        if len(parts) >= 2:
            remainder = parts[1]
            mem_parts = remainder.split("---MEMORY---")
            briefing = mem_parts[0].replace("DAILY_BRIEFING:", "").strip()
            result["daily_briefing"] = re.sub(r'[\*#]+', '', briefing)
            if len(mem_parts) >= 2:
                result["memory_text"] = mem_parts[1].replace("MEMORY:", "").strip()

        return result

    def _validate(self, parsed: dict) -> bool:
        """Checks structural requirements. Returns True only if all pass."""
        briefing = parsed.get("daily_briefing", "")
        insight = parsed.get("morning_insight", "")

        if not briefing or not insight:
            return False

        numbered = [l for l in briefing.splitlines() if re.match(r'^\d+\.', l.strip())]
        if len(numbered) != 5:
            return False

        if len(briefing) > 850:
            return False

        paragraphs = [p for p in insight.split("\n\n") if p.strip()]
        if len(paragraphs) != 2:
            return False

        return True

    def _truncate_and_pad(self, parsed: dict) -> dict:
        """Programmatically fixes point count and length without a Claude call."""
        result = dict(parsed)
        briefing = result.get("daily_briefing", "")

        lines = briefing.splitlines()
        point_starts = [i for i, l in enumerate(lines) if re.match(r'^\d+\.', l.strip())]

        if len(point_starts) > 5:
            briefing = "\n".join(lines[:point_starts[5]])
        elif len(point_starts) < 5:
            for i in range(len(point_starts) + 1, 6):
                briefing += f"\n{i}. Focus on making steady progress today."

        if len(briefing) > 850:
            truncated = briefing[:850]
            last_end = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
            if last_end > 0:
                briefing = truncated[:last_end + 1] + "…"
            else:
                briefing = truncated.rstrip() + "…"

        result["daily_briefing"] = briefing
        return result

    def _static_fallback(self, day_of_year: int, current_year: int) -> dict:
        """Last-resort static content so morning_run.py never crashes on key access."""
        return {
            "morning_insight": (
                f"Day {day_of_year} of {current_year}. Time moves regardless of intention — "
                f"act before the day decides for you.\n\n"
                f"📝 Journal Prompt: What small thing today deserves more appreciation than you've given it?"
            ),
            "daily_briefing": (
                "1. Context synthesis unavailable for this run.\n"
                "2. Start with the first pending task on your checklist.\n"
                "3. Take one small action toward your most active goal.\n"
                "4. Use any free time for focused work or creative thinking.\n"
                "5. End the day with something you genuinely enjoy."
            ),
            "memory_text": "",
            "memory_detail": "",
        }

    def _get_validated_output(self, raw_prompt_kwargs: dict, max_retries: int = 1) -> dict:
        """Orchestrates validation layers: clean pass → retry → truncate/pad → static fallback."""
        raw = _call_claude(**raw_prompt_kwargs)
        parsed = self._parse_output(raw)
        if self._validate(parsed):
            print("  ✅ Validation passed (layer 0 — clean pass)")
            return parsed

        # Layer 1: retry once with corrective note
        if max_retries > 0:
            print("  ⚠️  Validation failed — retrying with corrective prompt (layer 1)")
            corrective_kwargs = dict(raw_prompt_kwargs)
            corrective_kwargs["prompt"] = raw_prompt_kwargs["prompt"] + (
                "\n\nIMPORTANT: Your previous output did not match the required "
                "format exactly. Daily Briefing must have EXACTLY 5 numbered "
                "points, under 850 characters, no markdown symbols."
            )
            raw2 = _call_claude(**corrective_kwargs)
            parsed2 = self._parse_output(raw2)
            if self._validate(parsed2):
                print("  ✅ Validation passed (layer 1 — retry)")
                return parsed2
            parsed = parsed2

        # Layer 2: truncate/pad programmatically
        print("  ⚠️  Retry failed — applying truncate/pad (layer 2)")
        parsed = self._truncate_and_pad(parsed)
        if self._validate(parsed):
            print("  ✅ Validation passed (layer 2 — truncate/pad)")
            return parsed

        # Layer 3: static fallback
        print("  ❌ All validation layers exhausted — using static fallback (layer 3)")
        return self._static_fallback(self._day_of_year, self._current_year)


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
