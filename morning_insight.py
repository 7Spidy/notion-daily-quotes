#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from anthropic import Anthropic
import requests
import json
import os
import re
from datetime import datetime, timezone, timedelta
import jwt
import time

# Google Calendar colorId → (emoji, category label)
CALENDAR_COLOR_MAP = {
    "11": ("🔴", "Fun/Play"),
    "4":  ("🔴", "Fun/Play"),
    "6":  ("🔴", "Fun/Play"),
    "9":  ("🔵", "Office"),
    "1":  ("🔵", "Office"),
    "7":  ("🔵", "Office"),
    "3":  ("🔵", "Office"),
    "10": ("🟢", "Health"),
    "2":  ("🟢", "Health"),
    "5":  ("🟡", "Chores"),
    "8":  ("🟡", "Chores"),
}


class MorningInsightGenerator:
    """
    Single-file morning runner.
    Produces two Notion callout blocks:
      ☀️  Morning Insight  — 2-part: Stoic reminder + Journal prompt
      🌅  Daily Insight    — 5-part: Strategic briefing
    Creates today's journal entry in Daily Journal DB with prompt pre-filled.
    After writing, saves one memory entry back to AGENT_MEMORY_DB_ID.
    """

    def __init__(self):
        self.anthropic_client = Anthropic()
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')

        self.weekly_checklist_db_id = os.getenv('WEEKLY_CHECKLIST_DB_ID')
        self.strategic_goals_db_id = os.getenv('STRATEGIC_GOALS_DB_ID')
        self.daily_journal_db_id = os.getenv('DAILY_JOURNAL_DB_ID')

        # AI Agent long-term memory and instructions
        self.agent_instructions_page_id = os.getenv('AGENT_MEMORY_PAGE_ID')
        self.agent_memory_db_id = os.getenv('AGENT_MEMORY_DB_ID')

        self.max_retries = 3
        self.retry_delay = 3

        try:
            self.google_credentials = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        except Exception as e:
            print(f"Google setup error: {e}")
            self.google_credentials = None

    # ─── Shared Helpers ───────────────────────────────────────────────────────

    def get_current_ist_time(self):
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).strftime("%A, %B %d, %Y - %I:%M %p IST")

    def notion_retry(self, func, *args, **kwargs):
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    print(f"  Attempt {attempt}/{self.max_retries}...")
                result = func(*args, **kwargs)
                if attempt > 1:
                    print(f"  ✅ Succeeded on attempt {attempt}")
                return result
            except Exception as e:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    print(f"  ⚠️ Attempt {attempt} failed: {str(e)[:100]}")
                    print(f"  ⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"  ❌ All {self.max_retries} attempts failed")
                    raise e

    def sanitize(self, content, fallback="Content unavailable"):
        if not content:
            return fallback
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)
        content = content.encode('utf-8', errors='ignore').decode('utf-8')
        if len(content) > 1950:
            content = content[:1950] + "..."
            print("  ⚠️ Content truncated to 1950 characters")
        return content.strip() or fallback

    # ─── Google Calendar ──────────────────────────────────────────────────────

    def _get_google_access_token(self):
        try:
            now = int(time.time())
            payload = {
                'iss': self.google_credentials['client_email'],
                'scope': 'https://www.googleapis.com/auth/calendar.readonly',
                'aud': 'https://oauth2.googleapis.com/token',
                'exp': now + 3600,
                'iat': now
            }
            token = jwt.encode(payload, self.google_credentials['private_key'], algorithm='RS256')
            r = requests.post('https://oauth2.googleapis.com/token', data={
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'assertion': token
            })
            return r.json().get('access_token')
        except Exception as e:
            print(f"  Token error: {e}")
            return None

    def get_calendar_events_today(self):
        try:
            access_token = self._get_google_access_token()
            if not access_token:
                return [{"time": "N/A", "summary": "Calendar access unavailable", "category": "⚪ Other"}]

            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            params = {
                'timeMin': now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                'timeMax': now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat(),
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            r = requests.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events",
                headers={'Authorization': f'Bearer {access_token}'}, params=params
            )
            if r.status_code != 200:
                return [{"time": "N/A", "summary": "Calendar access error", "category": "⚪ Other"}]

            events = []
            for event in r.json().get('items', []):
                start = event.get('start', {})
                start_dt = start.get('dateTime', start.get('date', ''))
                time_str = start_dt.split('T')[1][:5] if 'T' in start_dt else 'All day'
                color_id = str(event.get('colorId', ''))
                emoji, label = CALENDAR_COLOR_MAP.get(color_id, ("⚪", "Other"))
                events.append({
                    "time": time_str,
                    "summary": event.get('summary', 'No title'),
                    "category": f"{emoji} {label}"
                })
            return events or [{"time": "N/A", "summary": "No events today", "category": "⚪ Other"}]
        except Exception as e:
            print(f"  Calendar error: {e}")
            return [{"time": "N/A", "summary": "Calendar temporarily unavailable", "category": "⚪ Other"}]

    # ─── AI Agent Instructions & Memory (READ) ────────────────────────────────

    def get_agent_instructions(self):
        """Fetch AI agent instructions from Notion page (AGENT_MEMORY_PAGE_ID)."""
        if not self.agent_instructions_page_id:
            print("  ⚠️ AGENT_MEMORY_PAGE_ID not set — skipping")
            return ""
        try:
            print("📖 Reading AI Instructions page...")
            content = self._get_page_content(self.agent_instructions_page_id)
            print(f"  ✅ AI Instructions loaded: {len(content)} chars")
            return content
        except Exception as e:
            print(f"  ⚠️ Could not load AI Instructions: {e}")
            return ""

    def _query_agent_memories(self):
        """Query recent entries from Agent Memory DB."""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        r = requests.post(
            f"https://api.notion.com/v1/databases/{self.agent_memory_db_id}/query",
            headers=headers,
            json={
                "sorts": [{"property": "Created time", "direction": "descending"}],
                "page_size": 20
            },
            timeout=10
        )
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}: {r.text[:200]}")

        memories = []
        for entry in r.json().get('results', []):
            try:
                props = entry.get('properties', {})
                content = ''
                for key in ['Memory', 'Name', 'Content', 'Observation', 'Note', 'Title']:
                    if key in props:
                        prop = props[key]
                        if prop.get('title') and prop['title']:
                            content = prop['title'][0]['plain_text']
                            break
                        elif prop.get('rich_text') and prop['rich_text']:
                            content = prop['rich_text'][0]['plain_text']
                            break
                if not content:
                    for key, val in props.items():
                        if val.get('rich_text') and val['rich_text']:
                            content = val['rich_text'][0]['plain_text']
                            break
                        elif val.get('title') and val['title']:
                            content = val['title'][0]['plain_text']
                            break
                if content.strip():
                    memories.append(content.strip())
            except Exception:
                pass
        return memories

    def get_agent_memories(self):
        """Fetch recent agent memory entries from Notion DB (AGENT_MEMORY_DB_ID)."""
        if not self.agent_memory_db_id:
            print("  ⚠️ AGENT_MEMORY_DB_ID not set — skipping")
            return []
        try:
            print("🧠 Reading Agent Memory DB...")
            memories = self.notion_retry(self._query_agent_memories)
            print(f"  ✅ Loaded {len(memories)} memory entries")
            return memories
        except Exception as e:
            print(f"  ⚠️ Could not load Agent Memory: {e}")
            return []

    # ─── AI Agent Memory (WRITE) ──────────────────────────────────────────────

    def get_memory_db_title_property(self):
        """
        Fetch DB schema and return the name of the title-type property.
        Falls back to 'Name' if the schema cannot be read.
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Notion-Version": "2022-06-28"
            }
            r = requests.get(
                f"https://api.notion.com/v1/databases/{self.agent_memory_db_id}",
                headers=headers, timeout=10
            )
            if r.status_code != 200:
                print(f"  ⚠️ Could not read DB schema: HTTP {r.status_code} — defaulting to 'Name'")
                return "Name"
            for prop_name, prop_meta in r.json().get('properties', {}).items():
                if prop_meta.get('type') == 'title':
                    print(f"  ℹ️ Memory DB title property: '{prop_name}'")
                    return prop_name
        except Exception as e:
            print(f"  ⚠️ Schema read error: {e} — defaulting to 'Name'")
        return "Name"

    def generate_memory_observation(self, checklist_items, strategic_goals,
                                     journal_entries, calendar_events,
                                     morning_insight, daily_briefing):
        """
        Ask Claude to write one concise memory entry summarising this run —
        patterns, preferences, context useful for future runs.
        """
        ist = timezone(timedelta(hours=5, minutes=30))
        run_date = datetime.now(ist).strftime("%Y-%m-%d")
        active_goals = [g for g in strategic_goals if "In Progress" in g]
        done_goals = [g for g in strategic_goals if "Done" in g]
        journal_titles = [e['title'] for e in journal_entries[:4]]
        calendar_summary = [f"{e['time']} {e['category']}: {e['summary']}" for e in calendar_events[:5]]

        prompt = f"""You are an AI agent maintaining a long-term memory log about the user.

After today's run, write ONE concise memory entry (max 80 words, plain text, no headers) capturing:
- Notable patterns, preferences, or context about the user visible today
- Key goals and their status
- Journal themes and what the user seems focused on
- Any context useful for improving tomorrow's briefing

Run date: {run_date}
Active goals: {'; '.join(active_goals[:4]) if active_goals else 'None'}
Recently done goals: {'; '.join(done_goals[:3]) if done_goals else 'None'}
Journal entries reviewed: {'; '.join(journal_titles)}
Today's calendar: {'; '.join(calendar_summary)}
Pending tasks: {'; '.join(checklist_items[:4])}
Morning insight generated: {morning_insight[:120]}
Daily briefing focus: {daily_briefing[:200]}

Write a single plain-text paragraph. No labels, no markdown, no bullet points."""

        try:
            print("  🤖 Generating memory observation with Claude Sonnet 4.6...")
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-6",
