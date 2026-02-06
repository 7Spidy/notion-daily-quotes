# 🤯 Notion Daily Insights & Strategic Briefing

> 💡 Let GPT update your Notion home page every day using your own data — without relying on Notion AI.

Automated daily insights for your Notion dashboard, powered by **OpenAI**, **Notion**, and **Google Calendar**.

This system (a GitHub repository with a scheduled workflow) generates:

1. **Morning Insight** – a short stoic reminder + positive journal prompt  
2. **Strategic Daily Briefing** – a 5‑part, context‑aware briefing using your:
   - Recent journal entries  
   - Weekly checklist  
   - Strategic goals  
   - Google Calendar schedule  

All content is written directly into a Notion page as carefully formatted **callout blocks**.

---

## 📚 What You Get

### 1. Morning Insight (2‑Part)

- Stoic reminder about time, mortality, and intentional living  
- Positive psychology–inspired journal prompt (non‑work, uplifting, concise)  
- Adapts tone based on the day of the week (workday vs weekend)

### 2. Strategic Daily Briefing (5‑Part)

- Reflection on recent journal entries  
- Recommendation of **one weekly task** to focus on today  
- Suggestion of **one action** aligned with a strategic goal  
- Suggestions on how to use **vacant time slots** in your calendar  
- **One fun, relaxing activity** to balance your day  

### 3. Rich Context Integration

- Reads your **3 most recent Notion journal entries**, including full page content  
- Uses Notion databases for:
  - Weekly checklist  
  - Strategic goals (with progress %)  
- Uses Google Calendar to:
  - List today’s events  
  - Detect vacant time blocks  

### 4. Built‑In Safety & Resilience

- Retry logic with exponential backoff for Notion API calls  
- Sanitization of content before writing to Notion (control characters removed, length limited)  
- Fallback messages if OpenAI or external APIs fail  

---

## 🧱 High‑Level Architecture

```text
GitHub Actions (Daily at 12:30 AM IST)
        │
        ├── Job 1: Morning Insight (morning_insight.py)
        │       ├─ Uses OpenAI to generate:
        │       │    -  Stoic time reminder
        │       │    -  Positive journal prompt
        │       └─ Updates Notion page callout block "☀️ Morning Insight"
        │
        └── Job 2: Strategic Daily Briefing (daily_briefing.py)
                ├─ Fetches from:
                │    -  Notion Weekly Checklist DB
                │    -  Notion Strategic Goals DB
                │    -  Notion Daily Journal DB (3 latest entries, full content)
                │    -  Google Calendar (today’s events)
                ├─ Uses OpenAI to generate a 5-part briefing
                └─ Updates/creates a "🌅 Daily Insight" callout block in Notion
