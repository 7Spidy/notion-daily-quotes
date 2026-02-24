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
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            memory = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            ).strip()
            print("  ✅ Memory observation generated")
            return memory
        except Exception as e:
            print(f"  ⚠️ Memory generation error: {e}")
            ist = timezone(timedelta(hours=5, minutes=30))
            return (
                f"{datetime.now(ist).strftime('%Y-%m-%d')}: "
                f"Active goals — {'; '.join(active_goals[:2]) if active_goals else 'None'}. "
                f"Journal themes — {', '.join(journal_titles[:3])}. "
                f"Pending tasks — {'; '.join(checklist_items[:3])}. "
                f"Briefing generated successfully."
            )

    def save_agent_memory(self, observation):
        """
        Write a new page to AGENT_MEMORY_DB_ID with the observation as its title.
        Detects the correct title property name automatically via get_memory_db_title_property().
        """
        if not self.agent_memory_db_id:
            print("  ⚠️ AGENT_MEMORY_DB_ID not set — skipping memory save")
            return

        title_prop = self.get_memory_db_title_property()

        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        payload = {
            "parent": {"database_id": self.agent_memory_db_id},
            "properties": {
                title_prop: {
                    "title": [{"type": "text", "text": {"content": observation[:2000]}}]
                }
            }
        }

        try:
            r = requests.post(
                "https://api.notion.com/v1/pages",
                headers=headers, json=payload, timeout=15
            )
            if r.status_code in (200, 201):
                print(f"  ✅ Memory saved to DB: {observation[:80]}...")
            else:
                print(f"  ⚠️ Failed to save memory: HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"  ⚠️ Memory save error: {e}")

    # ─── Notion Data Fetches ──────────────────────────────────────────────────

    def _query_weekly_checklist(self):
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        r = requests.post(
            f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query",
            headers=headers,
            json={"filter": {"property": "Done?", "checkbox": {"equals": False}}, "page_size": 10},
            timeout=10
        )
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}: {r.text[:200]}")
        items = []
        for item in r.json().get('results', []):
            try:
                name = 'Untitled task'
                if 'Task' in item['properties'] and item['properties']['Task']['title']:
                    name = item['properties']['Task']['title'][0]['plain_text']
                items.append(name)
            except Exception as e:
                print(f"  ⚠️ Error parsing task: {e}")
        return items or ["All weekly items completed"]

    def get_weekly_checklist_items(self):
        try:
            items = self.notion_retry(self._query_weekly_checklist)
            print(f"  Found {len(items)} unchecked items")
            return items
        except Exception as e:
            print(f"❌ Weekly checklist failed: {e}")
            return ["Weekly planning review"]

    def _query_strategic_goals(self):
        """
        Fetch:
          - All goals with Status = 'In progress'
          - Goals with Status = 'Done' AND last_edited_time within the last 7 days
        Prevents stale Done goals from appearing in the briefing.
        """
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        ist = timezone(timedelta(hours=5, minutes=30))
        seven_days_ago = (datetime.now(ist) - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00+05:30")

        r = requests.post(
            f"https://api.notion.com/v1/databases/{self.strategic_goals_db_id}/query",
            headers=headers,
            json={
                "filter": {
                    "or": [
                        {
                            "property": "Status",
                            "status": {"equals": "In progress"}
                        },
                        {
                            "and": [
                                {"property": "Status", "status": {"equals": "Done"}},
                                {
                                    "timestamp": "last_edited_time",
                                    "last_edited_time": {"on_or_after": seven_days_ago}
                                }
                            ]
                        }
                    ]
                },
                "page_size": 10
            },
            timeout=10
        )
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}: {r.text[:200]}")
        goals = []
        for goal in r.json().get('results', []):
            try:
                name = 'Untitled Goal'
                if 'Name' in goal['properties'] and goal['properties']['Name']['title']:
                    name = goal['properties']['Name']['title'][0]['plain_text']
                progress = 0
                if 'Progress' in goal['properties'] and goal['properties']['Progress']['number'] is not None:
                    progress = int(goal['properties']['Progress']['number'])
                status = 'Unknown'
                if 'Status' in goal['properties'] and goal['properties']['Status']['status']:
                    status = goal['properties']['Status']['status']['name']
                tag = "✅ Done" if status == "Done" else "🔄 In Progress"
                goals.append(f"{name} ({progress}% — {tag})")
            except Exception as e:
                print(f"  ⚠️ Error parsing goal: {e}")
        return goals or ["Define new strategic goals"]

    def get_strategic_goals(self):
        try:
            goals = self.notion_retry(self._query_strategic_goals)
            print(f"  Found {len(goals)} goals")
            return goals
        except Exception as e:
            print(f"❌ Strategic goals failed: {e}")
            return ["Strategic milestone planning"]

    def _get_page_content(self, page_id):
        headers = {"Authorization": f"Bearer {self.notion_token}", "Notion-Version": "2022-06-28"}
        r = requests.get(f"https://api.notion.com/v1/blocks/{page_id}/children", headers=headers, timeout=15)
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}")

        def extract(rich_text):
            return ''.join(t.get('plain_text', '') for t in (rich_text or []))

        prefixes = {
            'paragraph': '', 'heading_1': '# ', 'heading_2': '## ', 'heading_3': '### ',
            'bulleted_list_item': '• ', 'numbered_list_item': '• ', 'quote': '> ', 'callout': '💡 '
        }
        parts = []
        for block in r.json().get('results', []):
            try:
                bt = block.get('type', '')
                if bt in prefixes:
                    text = extract(block[bt]['rich_text'])
                    if text.strip():
                        parts.append(f"{prefixes[bt]}{text}")
                elif bt == 'to_do':
                    text = extract(block['to_do']['rich_text'])
                    if text.strip():
                        parts.append(f"{'✅' if block['to_do']['checked'] else '☐'} {text}")
            except Exception:
                pass
        content = '\n'.join(parts)
        return content[:800] if content else "No content found"

    def _query_journal_entries(self):
        """Fetch journal entries from the last 7 days with full page content."""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        ist = timezone(timedelta(hours=5, minutes=30))
        seven_days_ago = (datetime.now(ist) - timedelta(days=7)).strftime("%Y-%m-%d")
        r = requests.post(
            f"https://api.notion.com/v1/databases/{self.daily_journal_db_id}/query",
            headers=headers,
            json={
                "filter": {
                    "property": "Created time",
                    "created_time": {"on_or_after": seven_days_ago}
                },
                "sorts": [{"property": "Created time", "direction": "descending"}],
                "page_size": 10
            },
            timeout=10
        )
        if r.status_code != 200:
            raise Exception(f"HTTP {r.status_code}: {r.text[:200]}")

        entries = []
        for entry in r.json().get('results', []):
            try:
                title = 'Journal Entry'
                if 'Name' in entry['properties'] and entry['properties']['Name']['title']:
                    title = entry['properties']['Name']['title'][0]['plain_text']
                life_areas = []
                if 'Life Area' in entry['properties'] and entry['properties']['Life Area']['multi_select']:
                    life_areas = [a['name'] for a in entry['properties']['Life Area']['multi_select']]
                created_date = 'Unknown'
                if 'Created time' in entry['properties'] and entry['properties']['Created time']['created_time']:
                    created_date = entry['properties']['Created time']['created_time'][:10]
                print(f"  📖 Reading: {title} ({created_date})")
                content = self._get_page_content(entry['id'])
                entries.append({'title': title, 'content': content, 'life_areas': life_areas, 'date': created_date})
                print(f"  ✅ Loaded: {len(content)} chars")
            except Exception as e:
                print(f"  ⚠️ Error: {e}")
                entries.append({'title': 'Recent journal entry', 'content': 'Unavailable', 'life_areas': [], 'date': 'Recent'})
        return entries or [{'title': 'Start journaling', 'content': 'Begin daily reflections', 'life_areas': ['Personal Growth'], 'date': 'Today'}]

    def get_journal_entries(self):
        try:
            entries = self.notion_retry(self._query_journal_entries)
            print(f"  ✅ Loaded {len(entries)} entries")
            return entries
        except Exception as e:
            print(f"❌ Journal failed: {e}")
            return [{'title': 'Daily reflection', 'content': 'Continue journaling', 'life_areas': ['Personal Growth'], 'date': 'Today'}]

    # ─── Block Comment Feedback ───────────────────────────────────────────────

    def find_block_id(self, marker_text):
        """Find a callout block on the page whose text contains marker_text."""
        try:
            headers = {"Authorization": f"Bearer {self.notion_token}", "Notion-Version": "2022-06-28"}
            r = requests.get(f"https://api.notion.com/v1/blocks/{self.page_id}/children", headers=headers, timeout=10)
            if r.status_code != 200:
                return None
            for block in r.json().get('results', []):
                if (block['type'] == 'callout' and
                        block.get('callout', {}).get('rich_text') and
                        marker_text in block['callout']['rich_text'][0].get('plain_text', '')):
                    return block['id']
        except Exception as e:
            print(f"  ⚠️ Could not find block ({marker_text}): {e}")
        return None

    def get_block_comments(self, block_id):
        """Read user comments on a Notion block."""
        if not block_id:
            return []
        try:
            headers = {"Authorization": f"Bearer {self.notion_token}", "Notion-Version": "2022-06-28"}
            r = requests.get(
                "https://api.notion.com/v1/comments",
                headers=headers, params={"block_id": block_id}, timeout=10
            )
            if r.status_code != 200:
                print(f"  ⚠️ Comments API {r.status_code} — enable 'Read comments' in integration settings")
                return []
            comments = []
            for c in r.json().get('results', []):
                text = ''.join(t.get('plain_text', '') for t in c.get('rich_text', []))
                created = c.get('created_time', '')[:10]
                if text.strip():
                    comments.append(f"[{created}] {text.strip()}")
            return comments
        except Exception as e:
            print(f"  ⚠️ Could not fetch comments: {e}")
            return []

    # ─── Part 1: Morning Insight (Stoic + Journal Prompt) ────────────────────

    def generate_morning_insight(self, ai_instructions="", memories=None, user_feedback=None):
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        day_of_year = now.timetuple().tm_yday
        day_of_week = now.strftime("%A")
        current_year = now.year

        memory_section = ""
        if memories:
            memory_section = f"\n\nAGENT MEMORY (long-term context): {'; '.join(memories[:10])}"

        feedback_section = ""
        if user_feedback:
            feedback_section = (
                f"\n\nUSER FEEDBACK ON PREVIOUS INSIGHTS: {'; '.join(user_feedback)}\n"
                "Adjust your style, tone, or content based on this feedback."
            )

        prompt = f"""Generate a brief 2-part morning insight. Be concise and profound. MAX 80 words total.

Today is {day_of_week}, Day {day_of_year} of {current_year}.{memory_section}{feedback_section}

CRITICAL RULES:
- Do NOT use **, *, or any markdown formatting — write plain text only
- Do NOT add any header, title, or date line

PART 1 - Stoic Time Reminder (1 sentence):
Start with "Day {day_of_year} of {current_year}." Then add a profound stoic thought about time, mortality, or living intentionally. Under 20 words.

PART 2 - Personal Journal Prompt:
An uplifting journaling prompt focused on POSITIVE emotions (joy, gratitude, fulfillment, love, contentment). NOT work-related. NOT about fears or negatives.
- Celebrate strengths, progress, or meaningful relationships
- Relate naturally to {day_of_week}'s energy
- Start with "📝 Journal Prompt:"
- Under 30 words

Format: TWO parts only, separated by a blank line. No labels except "📝 Journal Prompt:". Just the content."""

        try:
            print("  🤖 Generating Morning Insight with Claude Sonnet 4.6...")
            kwargs = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}]
            }
            if ai_instructions:
                kwargs["system"] = ai_instructions
            response = self.anthropic_client.messages.create(**kwargs)
            insight = "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
            print("  ✅ Morning Insight generated")
            return insight
        except Exception as e:
            print(f"  ❌ Claude error: {e}")
            fallback = f"Day {day_of_year} of {current_year}. Each morning is a gift; unwrap it with intention.\n\n"
            if day_of_week == 'Sunday':
                fallback += "📝 Journal Prompt: What moment this week filled you with genuine joy, and how can you create more of that feeling?"
            elif day_of_week == 'Saturday':
                fallback += "📝 Journal Prompt: What activity makes you feel most alive and authentically yourself?"
            else:
                fallback += "📝 Journal Prompt: What relationship in your life brings the most gratitude, and how can you celebrate it today?"
            return fallback

    # ─── Part 2: Daily Briefing (5-Part Strategic) ───────────────────────────

    def has_vacant_time_slots(self, calendar_events):
        if not calendar_events or calendar_events[0]['time'] == 'N/A':
            return True
        return len([e for e in calendar_events if e['time'] not in ('All day', 'N/A')]) < 6

    def generate_daily_briefing(self, checklist_items, strategic_goals, journal_entries,
                                 calendar_events, ai_instructions="", memories=None, user_feedback=None):
        current_datetime = self.get_current_ist_time()

        journal_text = ' | '.join(
            f"{e['title']} ({e['date']}) [{', '.join(e['life_areas']) or 'General'}]: {e['content'][:350]}"
            for e in journal_entries
        )
        calendar_lines = [f"{e['time']} {e['category']}: {e['summary']}" for e in calendar_events]
        active_goals = [g for g in strategic_goals if "In Progress" in g]
        done_goals = [g for g in strategic_goals if "Done" in g]
        has_vacant = self.has_vacant_time_slots(calendar_events)

        memory_section = ""
        if memories:
            memory_section = f"\n- AGENT MEMORY (long-term context): {'; '.join(memories[:10])}"

        feedback_section = ""
        if user_feedback:
            feedback_section = f"\n- USER FEEDBACK ON PREVIOUS BRIEFINGS: {'; '.join(user_feedback)}"

        prompt = f"""You are an AI briefing assistant. Today is {current_datetime}.

DATA:
- WEEKLY TASKS (pending): {'; '.join(checklist_items[:5])}
- ACTIVE GOALS: {'; '.join(active_goals[:4]) if active_goals else 'None'}
- RECENTLY COMPLETED GOALS (last 7 days only): {'; '.join(done_goals[:3]) if done_goals else 'None'}
- JOURNAL (last 7 days): {journal_text}
- TODAY'S CALENDAR: {'; '.join(calendar_lines)}
  Color key — 🔴 Fun/Play  🔵 Office  🟢 Health  🟡 Chores  ⚪ Other{memory_section}{feedback_section}
- VACANT SLOTS AVAILABLE: {"Yes" if has_vacant else "No"}

CRITICAL RULES:
- Start your response DIRECTLY with "1." — no header, no title, no date, no separator line
- Do NOT use **, *, or any markdown formatting — write plain text only
- ONLY reference information explicitly present in the DATA section above
- Do NOT invent connections, metaphors, or context not directly stated in the data
- If RECENTLY COMPLETED GOALS is "None", do not mention any completed goals

Create EXACTLY 5 brief numbered insights. Vary sentence structure — avoid starting every sentence with "You".

1. From journal + calendar, find something genuinely accomplished or experienced this week. Warm, grateful insight (2-3 sentences). If RECENTLY COMPLETED GOALS has entries, briefly celebrate them.

2. From Weekly Tasks, recommend ONE specific task for today and briefly explain why (1-2 sentences). Use language like "Today's priority could be...", "Worth tackling...", "Consider completing..."

3. From Active Goals, suggest ONE specific action to take today (1-2 sentences). Be direct and actionable.

4. {("Identify 2-3 time slots in today's calendar suited for focused work. Reference color categories where helpful. (2-3 suggestions)") if has_vacant else ("Calendar is packed — suggest 2-3 micro-tasks that fit into natural breaks. No specific times.")}

5. {("Suggest ONE relaxing or enjoyable activity for a free slot in the second half of the day. Only reference events or activities explicitly in the data.") if has_vacant else ("Suggest ONE relaxing activity that fits flexibly between commitments. No specific times. Only reference activities explicitly in the data.")}

Keep TOTAL response under 850 characters. Be warm, direct, and actionable."""

        try:
            print("  🤖 Generating Daily Briefing with Claude Sonnet 4.6...")
            kwargs = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 850,
                "messages": [{"role": "user", "content": prompt}]
            }
            if ai_instructions:
                kwargs["system"] = ai_instructions
            response = self.anthropic_client.messages.create(**kwargs)
            briefing = "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()
            print("  ✅ Daily Briefing generated")
            return briefing
        except Exception as e:
            print(f"  ❌ Claude error: {e}")
            return (
                "1. This week's journal reflects consistent effort across multiple life areas.\n\n"
                "2. Worth tackling the first pending item on the weekly checklist to keep momentum.\n\n"
                "3. Take one concrete step toward the top active goal today, however small.\n\n"
                f"4. {'Short calendar gaps work well for checklist items, quick reviews, or stretches.' if has_vacant else 'Quick breaks can handle micro-tasks without derailing focus.'}\n\n"
                f"5. {'Carve out evening time for something purely enjoyable — a game, book, or walk.' if has_vacant else 'Between commitments, something creative or playful offers a good reset.'}"
            )

    # ─── Notion Write (shared) ────────────────────────────────────────────────

    def _write_callout_block(self, content, emoji, color, existing_block_id, marker_text):
        """Create or update a single callout block. Returns 'updated' or 'created'."""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        # No emoji prefix in text — callout icon already shows it, avoids double emoji (☀️ ☀️)
        full_content = self.sanitize(f"{marker_text} - {self.get_current_ist_time()}\n\n{content}")
        print(f"  📊 Content size: {len(full_content)} characters")

        block_data = {
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": full_content}}],
                "icon": {"emoji": emoji},
                "color": color
            }
        }

        if existing_block_id:
            r = requests.patch(
                f"https://api.notion.com/v1/blocks/{existing_block_id}",
                headers=headers, json=block_data, timeout=15
            )
            if r.status_code != 200:
                raise Exception(f"Update failed: HTTP {r.status_code}: {r.text[:300]}")
            return "updated"
        else:
            r = requests.patch(
                f"https://api.notion.com/v1/blocks/{self.page_id}/children",
                headers=headers, json={"children": [block_data]}, timeout=15
            )
            if r.status_code != 200:
                raise Exception(f"Create failed: HTTP {r.status_code}: {r.text[:300]}")
            return "created"

    def write_block(self, content, emoji, color, existing_block_id, marker_text):
        try:
            action = self.notion_retry(
                self._write_callout_block, content, emoji, color, existing_block_id, marker_text
            )
            print(f"  ✅ Successfully {action} {emoji} block")
        except Exception as e:
            print(f"  ❌ Failed to write {emoji} block: {e}")

    # ─── Main ─────────────────────────────────────────────────────────────────

    def run(self):
        print(f"🌅 Morning Runner (Claude Sonnet 4.6)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay\n")

        # ── AI Instructions + Memory — read BEFORE generating ──────────────
        ai_instructions = self.get_agent_instructions()
        memories = self.get_agent_memories()

        # ── Find existing blocks + read feedback comments ──────────────────
        print("\n💬 Finding existing blocks and reading comments...")
        insight_block_id = self.find_block_id("Morning Insight")
        briefing_block_id = self.find_block_id("Daily Insight")

        insight_feedback = []
        briefing_feedback = []

        if insight_block_id:
            insight_feedback = self.get_block_comments(insight_block_id)
            print(f"  ☀️  Morning Insight block found | {len(insight_feedback)} comment(s)")
        else:
            print("  ☀️  Morning Insight block not found — will create")

        if briefing_block_id:
            briefing_feedback = self.get_block_comments(briefing_block_id)
            print(f"  🌅  Daily Insight block found | {len(briefing_feedback)} comment(s)")
        else:
            print("  🌅  Daily Insight block not found — will create")

        # ── Fetch data ─────────────────────────────────────────────────────
        print("\n📅 Getting calendar events...")
        calendar_events = self.get_calendar_events_today()
        print(f"  Found {len(calendar_events)} events")

        print("📋 Getting weekly checklist...")
        checklist_items = self.get_weekly_checklist_items()

        print("🎯 Getting strategic goals (In Progress + recently Done)...")
        strategic_goals = self.get_strategic_goals()

        print("📝 Getting journal entries (last 7 days)...")
        journal_entries = self.get_journal_entries()

        # ── Generate ───────────────────────────────────────────────────────
        print("\n🧠 Generating Morning Insight (Part 1)...")
        morning_insight = self.generate_morning_insight(ai_instructions, memories, insight_feedback)
        print(f"  📊 {len(morning_insight)} characters")

        print("\n🧠 Generating Daily Briefing (Part 2)...")
        daily_briefing = self.generate_daily_briefing(
            checklist_items, strategic_goals, journal_entries,
            calendar_events, ai_instructions, memories, briefing_feedback
        )
        print(f"  📊 {len(daily_briefing)} characters")

        # ── Write to Notion ────────────────────────────────────────────────
        print("\n📝 Writing to Notion...")
        self.write_block(morning_insight, "☀️", "orange_background", insight_block_id, "Morning Insight")
        self.write_block(daily_briefing, "🌅", "blue_background", briefing_block_id, "Daily Insight")

        # ── Save memory observation back to DB ─────────────────────────────
        if self.agent_memory_db_id:
            print("\n🧠 Saving agent memory observation...")
            observation = self.generate_memory_observation(
                checklist_items, strategic_goals, journal_entries,
                calendar_events, morning_insight, daily_briefing
            )
            print(f"  📝 Observation: {observation[:100]}...")
            self.save_agent_memory(observation)
        else:
            print("\n  ⚠️ AGENT_MEMORY_DB_ID not set — skipping memory save")

        print(f"\n✅ All done at: {self.get_current_ist_time()}")


if __name__ == "__main__":
    generator = MorningInsightGenerator()
    generator.run()
