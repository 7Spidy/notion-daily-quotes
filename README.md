# 🧠 Life OS Daily Automation

> Your personal AI chief of staff — runs once a night while you sleep and
> briefs you when you wake up. No subscription. No app. Just a GitHub repo
> and a chained set of AI agents.

Powered by **Claude (Anthropic)**, **Notion**, and **Google Calendar**.

---

## What It Does

Once a day, a multi-agent AI pipeline reads your life data and writes a
morning briefing to your Notion dashboard.

| Time (IST) | What happens |
|---|---|
| **3 AM** | Full morning briefing written to Notion — journal synthesis, task focus, calendar context |

---

## The Agent Pipeline

It's not one big prompt. It's four focused agents that hand off to each other:

```
Raw data
   └─▶  Orchestrator   →  "Here's what matters today" (internal director's note)
            └─▶  Context Agent  →  "Here's what happened, with correct temporal labels"
                     └─▶  Planning Agent  →  Morning Insight + Daily Briefing
                                └─▶  Review Agent  →  Fact-checks, formats, generates a memory entry
                                         └─▶  Notion ✅
```

Each agent has **one job**. The Orchestrator never writes user content. The
Review Agent never fetches data. This keeps outputs clean and
hallucination-free.

---

## What Lands in Notion

**☀️ Morning Insight** — two-part callout (orange):
- A stoic one-liner about time and intention, keyed to the day number of the year
- A journal prompt tuned to the day of the week

**🌅 Daily Briefing** — five-point callout (blue):
1. What happened (references your actual journal entries, with temporal context like "Yesterday evening")
2. One task to focus on today
3. One action toward a strategic goal
4. How to use your free calendar slots (specific times, read from Google Calendar — informational only, nothing is booked)
5. One enjoyable thing to do

---

## What Makes It Actually Good

- **Temporal labels** — journal entries arrive with labels like "Yesterday morning (6:30 AM)" instead of raw dates. Claude knows what "recent" means.
- **Completed task tracking** — not just what's pending, but what you finished in the last 24 hours. Wins get acknowledged.
- **Calendar context, read-only** — today's events and free time are pulled in for the briefing; nothing is ever written back to the calendar.
- **Agent Memory** — observations saved to a Notion DB after every run. Agents read recent memory before generating content, so context compounds over time.
- **Sunday extras** — weekly tech audit of the automation itself + memory consolidation of entries older than 14 days.

---

## Stack

| Layer | Tool |
|---|---|
| AI | Claude (`claude-sonnet-5`) via Anthropic API |
| Dashboard | Notion (callout blocks, database queries) |
| Calendar | Google Calendar API (read-only, service account) |
| Scheduler | GitHub Actions (1 cron job + manual dispatch) |
| Runtime | Python 3.11, `anthropic`, `requests`, `PyJWT`, `cryptography` |

---

## Files

```
utils.py        — Notion + Calendar clients, temporal helpers
agents.py       — 5 agent classes: Orchestrator, Context, Planning, Review, TechAudit
morning_run.py  — 3 AM pipeline
.github/
  workflows/
    daily-quote.yml  — single cron schedule + workflow_dispatch
```

---

## Forking This

You'll need these GitHub secrets:

```
ANTHROPIC_API_KEY       NOTION_API_KEY          NOTION_PAGE_ID
GOOGLE_CREDENTIALS      GOOGLE_CALENDAR_ID
WEEKLY_CHECKLIST_DB_ID  STRATEGIC_GOALS_DB_ID   DAILY_JOURNAL_DB_ID
AGENT_MEMORY_PAGE_ID    AGENT_MEMORY_DB_ID
```

The Notion databases expected: Weekly Checklist, Strategic Goals, Daily Journal, Agent Memory Log.
The Google service account only needs read access to your calendar.

---

*Previously a single-file OpenAI script running at midnight, then a six-agent
Claude pipeline running three times daily. Now back down to one clean
morning run.*
