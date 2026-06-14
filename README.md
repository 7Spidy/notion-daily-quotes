# 🧠 Life OS Daily Automation

> Your personal AI chief of staff — runs while you sleep, briefs you when you wake up, nudges you at lunch, and wraps up your day. No subscription. No app. Just a GitHub repo and some cleverly chained AI agents.

Powered by **Claude (Anthropic)**, **Notion**, **Google Calendar**, and **Discord**.

---

## What It Does

Three times a day, a multi-agent AI pipeline reads your life data and either writes to your Notion dashboard or pings your Discord:

| Time (IST) | What happens |
|---|---|
| **3 AM** | Full morning briefing written to Notion — journal synthesis, task focus, calendar suggestions |
| **1 PM** | Midday Discord nudge + approved calendar blocks get created in Google Calendar |
| **7 PM** | Evening wrap-up on Discord — wins celebrated, open items noted, journal prompt dropped |

---

## The Agent Pipeline (Morning)

It's not one big prompt. It's four focused agents that hand off to each other:

```
Raw data
   └─▶  Orchestrator   →  "Here's what matters today" (internal director's note)
            └─▶  Context Agent  →  "Here's what happened, with correct temporal labels"
                     └─▶  Planning Agent  →  Morning Insight + Daily Briefing + Calendar suggestions
                                └─▶  Review Agent  →  Fact-checks, formats, generates a memory entry
                                         └─▶  Notion ✅
```

Each agent has **one job**. The Orchestrator never writes user content. The Review Agent never fetches data. This keeps outputs clean and hallucination-free.

---

## What Lands in Notion

**☀️ Morning Insight** — two-part callout (orange):
- A stoic one-liner about time and intention, keyed to the day number of the year
- A journal prompt tuned to the day of the week

**🌅 Daily Briefing** — five-point callout (blue):
1. What happened (references your actual journal entries, with temporal context like "Yesterday evening")
2. One task to focus on today
3. One action toward a strategic goal
4. How to use your free calendar slots (specific times, not vague advice)
5. One enjoyable thing to do

**📅 Calendar Queue** — checkbox list you can approve before 1 PM. Check the ones you want → Google Calendar events get created automatically at the midday run.

---

## What Lands in Discord

**🔔 Midday Check-In** — still-pending tasks called out by name, remaining calendar events, one specific suggestion for the next 2 hours.

**🌙 Evening Wrap** — day summary, wins celebrated, open items noted without guilt, 8 PM journal reminder + prompt.

---

## What Makes It Actually Good

- **Temporal labels** — journal entries arrive with labels like "Yesterday morning (6:30 AM)" instead of raw dates. Claude knows what "recent" means.
- **Completed task tracking** — not just what's pending, but what you finished in the last 24 hours. Wins get acknowledged.
- **Calendar approval flow** — Claude suggests time blocks, you approve them in Notion, they appear in your calendar. No auto-booking.
- **Agent Memory** — observations saved to a Notion DB after every run. Agents read recent memory before generating content, so context compounds over time.
- **Sunday extras** — weekly tech audit of the automation itself + memory consolidation of entries older than 14 days.

---

## Stack

| Layer | Tool |
|---|---|
| AI | Claude (`claude-sonnet-4-6`) via Anthropic API |
| Dashboard | Notion (callout blocks, to-do blocks, database queries) |
| Calendar | Google Calendar API (read + write, service account) |
| Nudges | Discord (webhook, no bot needed) |
| Scheduler | GitHub Actions (3 cron jobs + manual dispatch) |
| Runtime | Python 3.11, `anthropic`, `requests`, `PyJWT`, `cryptography` |

---

## Files

```
utils.py        — Notion, Calendar, Discord clients + temporal helpers
agents.py       — 6 agent classes: Orchestrator, Context, Planning, Review, Nudge, TechAudit
morning_run.py  — 3 AM pipeline
midday_run.py   — 1 PM calendar + nudge
evening_run.py  — 7 PM wrap-up
.github/
  workflows/
    daily-quote.yml  — 3 cron schedules + workflow_dispatch
```

---

## Forking This

You'll need these GitHub secrets:

```
ANTHROPIC_API_KEY       NOTION_API_KEY          NOTION_PAGE_ID
GOOGLE_CREDENTIALS      GOOGLE_CALENDAR_ID
WEEKLY_CHECKLIST_DB_ID  STRATEGIC_GOALS_DB_ID   DAILY_JOURNAL_DB_ID
AGENT_MEMORY_PAGE_ID    AGENT_MEMORY_DB_ID
DISCORD_WEBHOOK_URL
```

The Notion databases expected: Weekly Checklist, Strategic Goals, Daily Journal, Agent Memory Log.
The Google service account needs "Make changes to events" permission on your calendar.

---

*Previously a single-file OpenAI script running at midnight. Now a six-agent Claude pipeline running three times daily. Glow-up complete.*
