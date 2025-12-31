# ✨ Morning Insight - Setup & Integration Guide

## Overview

`morning_insight.py` is a new automation script that generates a **3-part dynamic daily briefing** to greet you every morning. It's designed to be **brief, time-aware, and thought-provoking**.

### What It Does

**Part 1: Stoic Wisdom (1 line, max 12 words)**
- `Day X of 2025. [Fresh GPT-generated wisdom about time/action]`
- Generated fresh each day by GPT-4o-mini
- Temperature: 0.8 (creative but grounded)
- Examples:
  - "Day 365 of 2025. What will you build with today?"
  - "Day 100 of 2025. Time compounds. Act now."

**Part 2: Special Calendar Events (2 lines, if exists)**
- Detects birthdays/anniversaries from your Google Calendar
- Formats: `🎂 [Name]'s Birthday - Reach out and celebrate`
- If none exist: **skipped entirely** (not shown)

**Part 3: Day-Aware Insight (2-3 sentences, 50-70 words)**
- **Smart detection**: Checks if today has a 💼 Work block (2+ hours)
- **Workday** → Focus on breakthrough projects, growth, power
- **Non-workday** → Connection, creation, presence, joy, rest
- Ends with **one thought-provoking question** (journal prompt)
- Temperature: 0.9 (more creative)

---

## Output Format

Notion block: **✨ Morning Insight Callout** (Orange background)

```
Day 365 of 2025. Every moment shapes your legacy.

🎂 Sarah's Birthday - Reach out and celebrate

You're stepping into your power this week. Focus on one breakthrough 
project that challenges you—that's where real growth lives. What's the 
smallest first step you can take today?
```

---

## Installation & Configuration

### Step 1: Verify Environment Variables

Make sure you have these in your `.env` file (same as `daily_briefing.py`):

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Notion
NOTION_API_KEY=ntn_...
NOTION_PAGE_ID=abc123...

# Google Calendar (service account)
GOOGLE_CREDENTIALS={"type": "service_account", "project_id": "...", ...}
GOOGLE_CALENDAR_ID=your-calendar@gmail.com
```

### Step 2: Install Dependencies

All dependencies are already required by `daily_briefing.py`:

```bash
pip install openai requests pyjwt
```

### Step 3: Add to Your Scheduler

#### Option A: GitHub Actions (Recommended)

Add to `.github/workflows/` (same time as your current daily_briefing job):

```yaml
name: Morning Insight

on:
  schedule:
    - cron: '1 1 * * *'  # 1:01 AM UTC = 6:31 AM IST
  workflow_dispatch:

jobs:
  generate-insight:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install openai requests pyjwt
      - run: python morning_insight.py
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          NOTION_PAGE_ID: ${{ secrets.NOTION_PAGE_ID }}
          GOOGLE_CREDENTIALS: ${{ secrets.GOOGLE_CREDENTIALS }}
          GOOGLE_CALENDAR_ID: ${{ secrets.GOOGLE_CALENDAR_ID }}
```

#### Option B: Cron Job (Local)

```bash
# Run at 6:30 AM IST every day
1 1 * * * cd /path/to/notion-daily-quotes && python morning_insight.py >> logs/morning_insight.log 2>&1
```

#### Option C: Python Scheduler (APScheduler)

```python
from apscheduler.schedulers.background import BackgroundScheduler
from morning_insight import MorningInsight

scheduler = BackgroundScheduler()
scheduler.add_job(MorningInsight().run, 'cron', hour=1, minute=1)  # 6:31 AM IST
scheduler.start()
```

---

## How It Works

### Flow Diagram

```
1. Get Day of Year
   ⮕️ Day 365 of 2025

2. Check Work Block
   ⮕️ Query Google Calendar for 2+ hour "Work" event
   ⮕️ is_workday = True/False

3. Check Birthdays/Anniversaries
   ⮕️ Query Google Calendar for events with "Birthday" or "Anniversary"
   ⮕️ special_event = event_name or None

4. Generate 3 Parts (Parallel)
   ⮕️ GPT: Stoic wisdom (12 words max, temp 0.8)
   ⮕️ Format: Birthday reminder (if exists)
   ⮕️ GPT: Day-aware insight (50-70 words, temp 0.9)

5. Update Notion
   ⮕️ Find existing Morning Insight block
   ⮕️ Update if exists, create if not
   ⮕️ Callout: ✨ emoji, orange background
```

### Key Functions

| Function | Purpose | Output |
|----------|---------|--------|
| `get_day_of_year()` | Calculate current day of year | `(365, 2025)` |
| `check_is_workday()` | Check for 2+ hour Work block | `True/False` |
| `get_special_calendar_events_today()` | Find birthdays/anniversaries | `"Sarah's Birthday"` or `None` |
| `generate_stoic_wisdom()` | GPT: Fresh stoic line | `"Day 365 of 2025. Every moment..."` |
| `generate_day_aware_insight()` | GPT: Context-aware insight | `"You're stepping into your..."` |
| `generate_birthday_reminder()` | Format special event | `"🎂 Sarah's Birthday - Reach out..."` |
| `_update_notion_block_safe()` | Create/update Notion block | `"created" / "updated"` |

---

## Customization

### Change Work Block Detection

Edit line in `check_is_workday()`:

```python
if duration_hours >= 2:  # ← Change this threshold
```

### Change Block Emoji/Color

Edit line in `_update_notion_block_safe()`:

```python
"icon": {
    "emoji": "✨"  # Change emoji
},
"color": "orange_background"  # or: red_bg, blue_bg, green_bg, etc.
```

### Adjust GPT Temperature (Creativity)

```python
# In generate_stoic_wisdom():
temperature=0.8,  # Lower = more grounded (0.3)
                  # Higher = more creative (1.0)

# In generate_day_aware_insight():
temperature=0.9,  # Slightly higher for more variety
```

### Customize Prompt Context

Edit the prompt strings in:
- `generate_stoic_wisdom()` - Stoic wisdom tone
- `generate_day_aware_insight()` - Workday vs non-workday insight

---

## Testing

### Test Run Locally

```bash
python morning_insight.py
```

Expected output:
```
======================================================================
✨ Morning Insight Generator
🕐 Wednesday, December 31, 2025 - 10:43 AM IST
======================================================================

📅 Calculating day of year...
   Day 365 of 2025

📊 Checking if today is a workday...
   💼 Work block detected: 8.0 hours - WORKDAY

🎂 Checking for birthdays/anniversaries...
   ℹ️ No special events today

📖 Part 1: Stoic Wisdom
   🤖 Generating stoic wisdom...
   ✅ Wisdom: Day 365 of 2025. What will you build with today?

💡 Part 3: Day-Aware Insight
   🤖 Generating work day insight...
   ✅ Insight generated: 147 characters

🔄 Updating Notion...
📝 Updating Notion page with Morning Insight...
   📝 Updating existing Morning Insight block...
   ✅ Block updated successfully

======================================================================
✅ Morning Insight generated successfully!
======================================================================
```

### Verify in Notion

1. Open your Notion page
2. Scroll to find the **✨ Morning Insight** callout block
3. Verify it has 3 parts (or 2 if no birthday)
4. Check timestamps are recent

---

## Comparison: Old vs New

### `daily_briefing.py` (Strategic Briefing)
- **Purpose**: Analyze journal + goals + calendar → 5 detailed strategic insights
- **Length**: 300+ words
- **Timing**: Deep analysis
- **When to read**: Throughout the day for reference
- **Block**: 🤖 Blue background

### `morning_insight.py` (Morning Insight) **NEW**
- **Purpose**: 3-part morning wake-up briefing
- **Length**: 100-150 words
- **Timing**: First thing at 6:30 AM
- **When to read**: Before getting out of bed
- **Block**: ✨ Orange background

**You will have BOTH running** - they serve different purposes!

---

## Troubleshooting

### Issue: "Calendar access unavailable - assuming workday"

**Solution**: Check Google credentials JSON in your `.env`

```bash
# Verify credentials format
echo $GOOGLE_CREDENTIALS | jq .
```

### Issue: No special events showing up

**Solution**: Verify birthday/anniversary event names in Google Calendar

- Must contain word: `birthday` or `anniversary` (case-insensitive)
- Example: `Sarah's Birthday`, `Mom's Anniversary`
- Must be a full-day event or show in today's calendar

### Issue: GPT generation is slow

**Solution**: Model is using gpt-4o-mini (faster and cheaper)

- First run: ~3-5 seconds
- Subsequent: ~2-3 seconds

If slower, check:
- OpenAI API status
- Network connectivity
- Rate limits

### Issue: Notion block not updating

**Solution**: Verify Notion integration

```bash
# Test Notion connection
curl -H "Authorization: Bearer $NOTION_API_KEY" \
  https://api.notion.com/v1/pages/$NOTION_PAGE_ID
```

---

## Cost Analysis

### Daily Cost

**OpenAI (gpt-4o-mini)**:
- Stoic wisdom: ~30 tokens
- Day-aware insight: ~90 tokens
- **Total**: ~120 tokens/day
- **Cost**: ~$0.0015/day = ~$0.045/month

**Google Calendar**: Free (quota: 1,000,000 requests/day)

**Notion**: Free (API calls)

**Total monthly**: ~$0.045

---

## Next Steps

1. ✅ Copy `morning_insight.py` to your repository
2. ✅ Verify environment variables are set
3. ✅ Test locally: `python morning_insight.py`
4. ✅ Add to your scheduler (GitHub Actions / Cron / APScheduler)
5. ✅ Monitor logs for 3-5 days
6. ✅ Once working, disable `daily_briefing.py` if desired

---

## Questions?

If you encounter issues:

1. Check logs: `tail -f logs/morning_insight.log`
2. Run locally with verbose output
3. Verify environment variables
4. Check Notion page permissions
5. Verify Google Calendar event names

---

**Enjoy your fresh, daily morning insights! ✨**
