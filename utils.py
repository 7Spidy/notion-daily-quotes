#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils.py — Shared utilities for Life OS Automation

Three clients (Notion, Calendar, Discord) + temporal helpers.
Everything the agents need to read/write data lives here.
"""

import json
import os
import re
import time
import requests
import jwt
from datetime import datetime, timezone, timedelta

# ─── Constants ────────────────────────────────────────────────────────────────

IST = timezone(timedelta(hours=5, minutes=30))

CALENDAR_COLOR_MAP = {
    "11": ("🔴", "Fun/Play"), "4": ("🔴", "Fun/Play"), "6": ("🔴", "Fun/Play"),
    "9":  ("🔵", "Office"),   "1": ("🔵", "Office"),   "7": ("🔵", "Office"),
    "3":  ("🔵", "Office"),
    "10": ("🟢", "Health"),   "2": ("🟢", "Health"),
    "5":  ("🟡", "Chores"),   "8": ("🟡", "Chores"),
}


# ─── Temporal Helpers ─────────────────────────────────────────────────────────

def get_ist_now() -> datetime:
    return datetime.now(IST)

def label_entry_datetime(iso_timestamp: str) -> str:
    """
    THE CORE TEMPORAL FIX.

    Previously the code just passed raw dates like "2026-06-14" to Claude
    with no relational context. Claude had no way to know that June 14 was
    "yesterday" when the 3 AM run was processing it.

    This function converts a Notion UTC timestamp → IST → human-readable label.

    Examples (when run at 3 AM IST on June 15):
      "2026-06-14T14:30:00Z" (8 PM IST Jun 14) → "Yesterday evening (8:00 PM)"
      "2026-06-14T01:00:00Z" (6:30 AM IST Jun 14) → "Yesterday morning (6:30 AM)"
      "2026-06-13T14:30:00Z" → "2 days ago (evening)"
    """
    now = get_ist_now()

    # Notion timestamps end in 'Z' (UTC). fromisoformat needs '+00:00'.
    if iso_timestamp.endswith('Z'):
        iso_timestamp = iso_timestamp[:-1] + '+00:00'

    entry_dt = datetime.fromisoformat(iso_timestamp).astimezone(IST)
    days_ago = (now.date() - entry_dt.date()).days
    hour = entry_dt.hour

    # Morning = 5 AM–11:59 AM, Afternoon = 12–4:59 PM, Evening = 5 PM onward
    if 5 <= hour < 12:
        time_part = f"morning ({entry_dt.strftime('%-I:%M %p')})"
    elif 12 <= hour < 17:
        time_part = f"afternoon ({entry_dt.strftime('%-I:%M %p')})"
    else:
        time_part = f"evening ({entry_dt.strftime('%-I:%M %p')})"

    if days_ago == 0:
        return f"Today {time_part}"
    elif days_ago == 1:
        return f"Yesterday {time_part}"
    elif days_ago == 2:
        return f"2 days ago ({time_part.split(' ')[0]})"
    else:
        return f"{days_ago} days ago ({time_part.split(' ')[0]})"

def format_ist(dt: datetime = None) -> str:
    if dt is None:
        dt = get_ist_now()
    return dt.strftime("%A, %B %d, %Y · %I:%M %p IST")


# ─── Notion Client ────────────────────────────────────────────────────────────

class NotionClient:
    """
    All Notion API operations.

    Key fixes over the original:
    - Journal entries now include full timestamps → temporal labels work correctly
    - Memory DB uses confirmed property names: Memory (title), Detail, Type, Source
    - New: get_tasks_completed_last_24h() — "what did I finish yesterday?"
    - New: write_calendar_queue() — approval-based calendar blocking
    - Block marker now written at the TOP of callout text so find_block never misses it
    """

    VERSION = "2022-06-28"

    def __init__(self):
        # Hard fail — every run type needs these two
        self.token                  = os.environ["NOTION_API_KEY"]
        self.weekly_checklist_db_id = os.environ["WEEKLY_CHECKLIST_DB_ID"]
        # Soft fail — not every run type needs these; missing = empty string, not crash
        # (e.g. evening run doesn't need page_id at init but may write to it later)
        self.page_id                = os.getenv("NOTION_PAGE_ID", "")
        self.strategic_goals_db_id  = os.getenv("STRATEGIC_GOALS_DB_ID", "")
        self.daily_journal_db_id    = os.getenv("DAILY_JOURNAL_DB_ID", "")
        self.agent_memory_page_id   = os.getenv("AGENT_MEMORY_PAGE_ID", "")
        self.agent_memory_db_id     = os.getenv("AGENT_MEMORY_DB_ID", "")

    @property
    def _h(self) -> dict:
        """Request headers (rebuilt each call so token changes mid-run don't break things)."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": self.VERSION,
        }

    def _retry(self, func, *args, retries=3, delay=3, **kwargs):
        """Exponential-backoff retry. Raises on final failure."""
        for attempt in range(1, retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt < retries:
                    wait = delay * attempt
                    print(f"  ⚠️  Attempt {attempt} failed ({e!s:.60}) — retry in {wait}s")
                    time.sleep(wait)
                else:
                    raise

    def _sanitize(self, text: str, limit: int = 1900) -> str:
        """Strip control chars, enforce Notion's single-block text limit."""
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text or "")
        text = text.encode('utf-8', errors='ignore').decode('utf-8')
        return (text[:limit] + "…") if len(text) > limit else text.strip()

    # ── Read: Agent Instructions & Memory ────────────────────────────────────

    def get_agent_instructions(self) -> str:
        """
        Reads the Initial Instructions section from the Agent Memory page.
        These become the system prompt for every Claude call — personality, rules, tone.
        """
        if not self.agent_memory_page_id:
            return ""
        try:
            r = requests.get(
                f"https://api.notion.com/v1/blocks/{self.agent_memory_page_id}/children",
                headers=self._h, timeout=15
            )
            if r.status_code != 200:
                return ""
            parts = []
            for block in r.json().get("results", []):
                bt = block.get("type", "")
                rt = block.get(bt, {}).get("rich_text", [])
                text = "".join(t.get("plain_text", "") for t in rt)
                if text.strip():
                    parts.append(text)
            return "\n".join(parts)[:2000]
        except Exception as e:
            print(f"  ⚠️  Agent instructions load failed: {e}")
            return ""

    def get_agent_memories(self, limit: int = 15) -> list[str]:
        """
        Reads recent entries from Agent Memory Log Database.
        Now includes Type tag and Detail for richer context.
        Property names confirmed from DB schema: Memory (title), Detail, Type, Source.
        """
        if not self.agent_memory_db_id:
            return []

        def _query():
            r = requests.post(
                f"https://api.notion.com/v1/databases/{self.agent_memory_db_id}/query",
                headers=self._h,
                json={"sorts": [{"property": "Created time", "direction": "descending"}],
                      "page_size": limit},
                timeout=10
            )
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")

            memories = []
            for entry in r.json().get("results", []):
                try:
                    props = entry["properties"]
                    # "Memory" is the confirmed title property
                    text = (props.get("Memory", {}).get("title") or [{}])[0].get("plain_text", "")
                    detail = ""
                    if props.get("Detail", {}).get("rich_text"):
                        detail = props["Detail"]["rich_text"][0].get("plain_text", "")
                    type_tag = ""
                    if props.get("Type", {}).get("select"):
                        type_tag = f"[{props['Type']['select']['name']}] "
                    combined = f"{type_tag}{text}" + (f" | {detail[:80]}" if detail else "")
                    if combined.strip():
                        memories.append(combined.strip())
                except Exception:
                    pass
            return memories

        try:
            return self._retry(_query)
        except Exception as e:
            print(f"  ⚠️  Memory read failed: {e}")
            return []

    # ── Read: Tasks ───────────────────────────────────────────────────────────

    def get_pending_tasks(self) -> list[str]:
        """Pending checklist items (Done? = False)."""
        def _query():
            r = requests.post(
                f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query",
                headers=self._h,
                json={"filter": {"property": "Done?", "checkbox": {"equals": False}},
                      "page_size": 10},
                timeout=10
            )
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")
            items = []
            for item in r.json().get("results", []):
                try:
                    name = item["properties"]["Task"]["title"][0]["plain_text"]
                    items.append(name)
                except Exception:
                    pass
            return items or ["No pending tasks"]

        try:
            return self._retry(_query)
        except Exception as e:
            print(f"  ⚠️  Pending tasks failed: {e}")
            return ["Task fetch unavailable"]

    def get_tasks_completed_last_24h(self) -> list[str]:
        """
        NEW METHOD — The missing piece.

        The original code never knew what you finished. It only saw pending tasks,
        so completed work was invisible. This query finds tasks where:
          Done? = True  AND  last_edited_time >= 24 hours ago

        We use last_edited_time because there's no "completed_at" column,
        and the user confirmed they don't want to add one.
        """
        cutoff = (get_ist_now() - timedelta(hours=24)).isoformat()

        def _query():
            r = requests.post(
                f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query",
                headers=self._h,
                json={
                    "filter": {
                        "and": [
                            {"property": "Done?", "checkbox": {"equals": True}},
                            {"timestamp": "last_edited_time",
                             "last_edited_time": {"on_or_after": cutoff}}
                        ]
                    },
                    "page_size": 10
                },
                timeout=10
            )
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")
            items = []
            for item in r.json().get("results", []):
                try:
                    name = item["properties"]["Task"]["title"][0]["plain_text"]
                    items.append(name)
                except Exception:
                    pass
            return items

        try:
            return self._retry(_query)
        except Exception as e:
            print(f"  ⚠️  Completed tasks failed: {e}")
            return []

    # ── Read: Goals & Journal ─────────────────────────────────────────────────

    def get_strategic_goals(self) -> list[str]:
        """Active goals (In Progress) + recently completed (last 7 days)."""
        cutoff = (get_ist_now() - timedelta(days=7)).isoformat()

        def _query():
            r = requests.post(
                f"https://api.notion.com/v1/databases/{self.strategic_goals_db_id}/query",
                headers=self._h,
                json={
                    "filter": {
                        "or": [
                            {"property": "Status", "status": {"equals": "In progress"}},
                            {"and": [
                                {"property": "Status", "status": {"equals": "Done"}},
                                {"timestamp": "last_edited_time",
                                 "last_edited_time": {"on_or_after": cutoff}}
                            ]}
                        ]
                    },
                    "page_size": 10
                },
                timeout=10
            )
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")
            goals = []
            for goal in r.json().get("results", []):
                try:
                    props = goal["properties"]
                    name = props["Name"]["title"][0]["plain_text"]
                    # Progress stored as decimal (0.11 = 11%)
                    pct = int((props.get("Progress", {}).get("number") or 0) * 100)
                    status = props.get("Status", {}).get("status", {}).get("name", "Unknown")
                    tag = "✅ Done" if status == "Done" else "🔄 In Progress"
                    goals.append(f"{name} ({pct}% — {tag})")
                except Exception:
                    pass
            return goals or ["No active goals"]

        try:
            return self._retry(_query)
        except Exception as e:
            print(f"  ⚠️  Goals failed: {e}")
            return ["Goals unavailable"]

    def _read_page_blocks(self, block_id: str, max_chars: int = 800) -> str:
        """Reads plain text from a Notion page's blocks."""
        try:
            r = requests.get(
                f"https://api.notion.com/v1/blocks/{block_id}/children",
                headers=self._h, timeout=15
            )
            if r.status_code != 200:
                return ""
            prefix_map = {
                'paragraph': '', 'heading_1': '# ', 'heading_2': '## ',
                'heading_3': '### ', 'bulleted_list_item': '• ',
                'numbered_list_item': '• ', 'quote': '> ', 'callout': '💡 ',
            }
            parts = []
            for block in r.json().get("results", []):
                bt = block.get("type", "")
                if bt in prefix_map:
                    texts = block[bt].get("rich_text", [])
                    text = "".join(t.get("plain_text", "") for t in texts)
                    if text.strip():
                        parts.append(f"{prefix_map[bt]}{text}")
                elif bt == "to_do":
                    texts = block["to_do"].get("rich_text", [])
                    text = "".join(t.get("plain_text", "") for t in texts)
                    if text.strip():
                        checked = "✅" if block["to_do"].get("checked") else "☐"
                        parts.append(f"{checked} {text}")
            content = "\n".join(parts)
            return content[:max_chars] if content else ""
        except Exception:
            return ""

    def get_journal_entries(self, days_back: int = 7, limit: int = 8) -> list[dict]:
        """
        UPDATED: now returns full timestamps for temporal labeling.

        Each entry dict now contains 'date_label' (e.g., "Yesterday morning (6:30 AM)")
        instead of just 'date' (e.g., "2026-06-14"). This label is what gets passed
        to Claude, giving it proper temporal context.
        """
        cutoff = (get_ist_now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        def _query():
            r = requests.post(
                f"https://api.notion.com/v1/databases/{self.daily_journal_db_id}/query",
                headers=self._h,
                json={
                    "filter": {
                        "property": "Created time",
                        "created_time": {"on_or_after": cutoff}
                    },
                    "sorts": [{"property": "Created time", "direction": "descending"}],
                    "page_size": limit
                },
                timeout=10
            )
            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}")

            entries = []
            for entry in r.json().get("results", []):
                try:
                    props = entry["properties"]
                    title = (props.get("Name", {}).get("title") or [{}])[0].get("plain_text", "Journal Entry")

                    # Full ISO timestamp → temporal label
                    created_iso = props.get("Created time", {}).get("created_time", "")
                    date_label = label_entry_datetime(created_iso) if created_iso else "Recent"

                    life_areas = [a["name"] for a in props.get("Life Area", {}).get("multi_select", [])]
                    content = self._read_page_blocks(entry["id"])

                    entries.append({
                        "title": title,
                        "date_label": date_label,   # "Yesterday morning (6:30 AM)"
                        "created_iso": created_iso,
                        "life_areas": life_areas,
                        "content": content,
                    })
                except Exception as e:
                    print(f"  ⚠️  Journal entry parse error: {e}")
            return entries

        try:
            result = self._retry(_query)
            print(f"  ✅ {len(result)} journal entries loaded")
            return result
        except Exception as e:
            print(f"  ⚠️  Journal failed: {e}")
            return []

    # ── Read / Write: Blocks on Main Page ────────────────────────────────────

    def find_block_by_marker(self, marker: str) -> str | None:
        """
        Finds a callout block whose text STARTS WITH the marker string.
        We now write the marker at the very start of each callout so it's
        never cut off by the 1900-char truncation.
        """
        try:
            r = requests.get(
                f"https://api.notion.com/v1/blocks/{self.page_id}/children",
                headers=self._h, timeout=10
            )
            if r.status_code != 200:
                return None
            for block in r.json().get("results", []):
                if block["type"] != "callout":
                    continue
                rt = block["callout"].get("rich_text", [])
                text = "".join(t.get("plain_text", "") for t in rt)
                if text.startswith(marker):
                    return block["id"]
        except Exception as e:
            print(f"  ⚠️  Block search failed ({marker}): {e}")
        return None

    def write_callout(
        self,
        content: str,
        emoji: str,
        color: str,
        marker: str,
        existing_id: str | None = None
    ):
        """
        Creates or updates a callout block.
        Marker is written at the very top so find_block_by_marker always finds it.
        """
        timestamp = format_ist()
        full_text = self._sanitize(f"{marker}\n{timestamp}\n\n{content}")

        payload = {
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": full_text}}],
                "icon": {"emoji": emoji},
                "color": color,
            }
        }

        def _write():
            if existing_id:
                r = requests.patch(
                    f"https://api.notion.com/v1/blocks/{existing_id}",
                    headers=self._h, json=payload, timeout=15
                )
                if r.status_code != 200:
                    raise Exception(f"HTTP {r.status_code}: {r.text[:150]}")
                return "updated"
            else:
                r = requests.patch(
                    f"https://api.notion.com/v1/blocks/{self.page_id}/children",
                    headers=self._h,
                    json={"children": [{"object": "block", "type": "callout", **payload}]},
                    timeout=15
                )
                if r.status_code != 200:
                    raise Exception(f"HTTP {r.status_code}: {r.text[:150]}")
                return "created"

        try:
            action = self._retry(_write)
            print(f"  ✅ {emoji} Callout {action}")
        except Exception as e:
            print(f"  ❌ Callout write failed ({emoji}): {e}")

    def get_block_comments(self, block_id: str) -> list[str]:
        """User comments on a block — used as feedback to adjust AI output."""
        if not block_id:
            return []
        try:
            r = requests.get(
                "https://api.notion.com/v1/comments",
                headers=self._h, params={"block_id": block_id}, timeout=10
            )
            if r.status_code != 200:
                return []
            comments = []
            for c in r.json().get("results", []):
                text = "".join(t.get("plain_text", "") for t in c.get("rich_text", []))
                date = c.get("created_time", "")[:10]
                if text.strip():
                    comments.append(f"[{date}] {text.strip()}")
            return comments
        except Exception:
            return []

    # ── Calendar Queue (approval-based time blocking) ─────────────────────────

    def write_calendar_queue(
        self,
        suggestions: list[dict],
        existing_id: str | None = None
    ):
        """
        NEW: Writes the Planning Agent's calendar suggestions as to_do blocks.

        How the approval flow works:
        1. Morning run (3 AM): Planning Agent identifies free slots and suggests blocks.
           This method writes them as unchecked to_do items under a callout on your
           Notion page.
        2. You open Notion, check the ones you want.
        3. Midday run (1 PM): Reads checked items, creates Google Calendar events,
           archives the processed blocks.

        suggestions: [{"title": "...", "start": "HH:MM", "end": "HH:MM"}]
        """
        if not suggestions:
            return

        # Archive the old queue block if it exists, then rebuild it fresh.
        # This prevents stale suggestions from previous days accumulating.
        if existing_id:
            try:
                requests.patch(
                    f"https://api.notion.com/v1/blocks/{existing_id}",
                    headers=self._h, json={"archived": True}, timeout=10
                )
            except Exception:
                pass

        # Create the header callout
        header_text = (
            "📅 Calendar Queue\n"
            "Check items to approve → will be blocked at 1 PM run\n"
            "Uncheck anything you don't want."
        )
        header_block = {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": header_text}}],
                "icon": {"emoji": "📅"},
                "color": "yellow_background",
            }
        }

        try:
            # Append the callout to the page
            r = requests.patch(
                f"https://api.notion.com/v1/blocks/{self.page_id}/children",
                headers=self._h,
                json={"children": [header_block]},
                timeout=15
            )
            if r.status_code != 200:
                print(f"  ⚠️  Calendar queue header failed: HTTP {r.status_code}")
                return

            new_callout_id = r.json()["results"][0]["id"]

            # Add to_do child blocks inside the callout
            todo_blocks = [
                {
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        # Format: "Block HH:MM–HH:MM: Task Title" — must match regex in reader
                        "rich_text": [{"type": "text", "text": {
                            "content": f"Block {s['start']}–{s['end']}: {s['title']}"
                        }}],
                        "checked": False,
                    }
                }
                for s in suggestions
            ]

            r2 = requests.patch(
                f"https://api.notion.com/v1/blocks/{new_callout_id}/children",
                headers=self._h,
                json={"children": todo_blocks},
                timeout=15
            )
            if r2.status_code == 200:
                print(f"  ✅ Calendar queue: {len(suggestions)} suggestion(s) written")
            else:
                print(f"  ⚠️  Calendar queue to_do items failed: HTTP {r2.status_code}")

        except Exception as e:
            print(f"  ⚠️  Calendar queue write failed: {e}")

    def get_approved_calendar_blocks(self, queue_block_id: str) -> list[dict]:
        """
        Reads checked to_do items from the Calendar Queue callout.
        Returns parsed items: [{"title": ..., "start": "HH:MM", "end": "HH:MM", "block_id": ...}]
        """
        if not queue_block_id:
            return []
        try:
            r = requests.get(
                f"https://api.notion.com/v1/blocks/{queue_block_id}/children",
                headers=self._h, timeout=10
            )
            if r.status_code != 200:
                return []

            approved = []
            for block in r.json().get("results", []):
                if block["type"] != "to_do" or not block["to_do"].get("checked"):
                    continue
                text = "".join(
                    t.get("plain_text", "")
                    for t in block["to_do"].get("rich_text", [])
                )
                # Parse "Block HH:MM–HH:MM: Task Title"
                m = re.match(r"Block (\d{2}:\d{2})–(\d{2}:\d{2}): (.+)", text)
                if m:
                    approved.append({
                        "start":    m.group(1),
                        "end":      m.group(2),
                        "title":    m.group(3),
                        "block_id": block["id"],
                    })
            return approved
        except Exception as e:
            print(f"  ⚠️  Approved blocks read failed: {e}")
            return []

    def archive_block(self, block_id: str):
        """Hides a processed block from the page (e.g., after calendar event created)."""
        try:
            requests.patch(
                f"https://api.notion.com/v1/blocks/{block_id}",
                headers=self._h, json={"archived": True}, timeout=10
            )
        except Exception:
            pass

    # ── Memory Write ──────────────────────────────────────────────────────────

    def save_memory(
        self,
        memory_text: str,
        detail: str = "",
        memory_type: str = "Pattern",
        source: str = "Agent Auto"
    ):
        """
        FIXED: Previously the code tried 6 different property name guesses.
        The actual title property is "Memory" (confirmed from DB schema).
        Now also writes Type, Source, and Detail as the schema supports.

        memory_type: "Correction" | "Preference" | "Pattern" | "Obsevation"
        source:      "User Feedback" | "Agent Auto"
        """
        if not self.agent_memory_db_id or not memory_text.strip():
            return

        payload = {
            "parent": {"database_id": self.agent_memory_db_id},
            "properties": {
                "Memory": {
                    "title": [{"type": "text", "text": {"content": memory_text[:2000]}}]
                },
                "Type":   {"select": {"name": memory_type}},
                "Source": {"select": {"name": source}},
            }
        }
        if detail:
            payload["properties"]["Detail"] = {
                "rich_text": [{"type": "text", "text": {"content": detail[:2000]}}]
            }

        try:
            r = requests.post(
                "https://api.notion.com/v1/pages",
                headers=self._h, json=payload, timeout=15
            )
            if r.status_code in (200, 201):
                print(f"  ✅ Memory saved [{memory_type}]: {memory_text[:60]}…")
            else:
                print(f"  ⚠️  Memory save failed: HTTP {r.status_code}")
        except Exception as e:
            print(f"  ⚠️  Memory save error: {e}")

    def refactor_old_memories(self):
        """
        Weekly cleanup (called Sunday morning runs only).
        Consolidates entries older than 14 days into one summary entry.
        Logic unchanged from original — it was working correctly.
        """
        from anthropic import Anthropic
        client = Anthropic()
        headers = self._h
        now = get_ist_now()
        cutoff = (now - timedelta(days=14)).isoformat()

        r = requests.post(
            f"https://api.notion.com/v1/databases/{self.agent_memory_db_id}/query",
            headers=headers,
            json={
                "filter": {
                    "property": "Created time",
                    "created_time": {"before": cutoff}
                },
                "sorts": [{"property": "Created time", "direction": "ascending"}],
                "page_size": 100
            },
            timeout=15
        )
        if r.status_code != 200:
            return

        old_entries = r.json().get("results", [])
        regular = []
        for entry in old_entries:
            try:
                title = (entry["properties"]["Memory"]["title"] or [{}])[0].get("plain_text", "")
                if "[CONSOLIDATED]" not in title:
                    regular.append({"id": entry["id"], "title": title,
                                    "created": entry.get("created_time", "")[:10]})
            except Exception:
                pass

        if not regular:
            print("  ✅ No old memory entries to consolidate")
            return

        entries_text = " | ".join(f"{e['created']}: {e['title'][:80]}" for e in regular[:30])
        prompt = (
            f"Summarize these {len(regular)} memory entries into ONE plain-text paragraph "
            f"(max 150 words). Focus on recurring themes, goal patterns, and key context. "
            f"No headers, no bullets.\n\nEntries: {entries_text}"
        )
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6", max_tokens=250,
                messages=[{"role": "user", "content": prompt}]
            )
            summary = "".join(b.text for b in resp.content if b.type == "text").strip()
        except Exception:
            summary = f"Consolidated {len(regular)} entries from {regular[0]['created']} to {regular[-1]['created']}."

        consolidated_title = f"[CONSOLIDATED] {regular[0]['created']} to {regular[-1]['created']}"
        self.save_memory(consolidated_title, detail=summary, memory_type="Pattern")

        archived = 0
        for entry in regular:
            try:
                requests.patch(
                    f"https://api.notion.com/v1/pages/{entry['id']}",
                    headers=headers, json={"archived": True}, timeout=10
                )
                archived += 1
            except Exception:
                pass
        print(f"  ✅ Consolidated {len(regular)} entries → archived {archived}")


# ─── Google Calendar Client ───────────────────────────────────────────────────

class CalendarClient:
    """
    Google Calendar — read AND write.

    The original code used calendar.readonly scope.
    Changed to full calendar scope to support event creation (time blocking).

    HOW TO UPDATE YOUR SERVICE ACCOUNT:
    No changes needed to the service account JSON.
    Just change the scope string in this class (already done below).
    The service account must have "Make changes to events" permission on the calendar.
    """

    SCOPE_READONLY = "https://www.googleapis.com/auth/calendar.readonly"
    SCOPE_WRITE    = "https://www.googleapis.com/auth/calendar"   # ← changed from readonly

    def __init__(self):
        try:
            self.credentials = json.loads(os.environ["GOOGLE_CREDENTIALS"])
            self.calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
        except Exception as e:
            print(f"  ⚠️  Calendar init failed: {e}")
            self.credentials = None
            self.calendar_id = None

    def _get_token(self) -> str | None:
        if not self.credentials:
            return None
        try:
            now = int(time.time())
            payload = {
                "iss": self.credentials["client_email"],
                "scope": self.SCOPE_WRITE,       # ← write scope
                "aud": "https://oauth2.googleapis.com/token",
                "exp": now + 3600,
                "iat": now,
            }
            jwt_token = jwt.encode(payload, self.credentials["private_key"], algorithm="RS256")
            r = requests.post(
                "https://oauth2.googleapis.com/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                      "assertion": jwt_token},
                timeout=10
            )
            return r.json().get("access_token")
        except Exception as e:
            print(f"  ⚠️  Calendar token error: {e}")
            return None

    def get_today_events(self) -> list[dict]:
        """Fetches today's events with color-coded category labels."""
        token = self._get_token()
        if not token:
            return [{"time": "N/A", "summary": "Calendar unavailable", "category": "⚪ Other"}]

        now = get_ist_now()
        params = {
            "timeMin": now.replace(hour=0,  minute=0,  second=0,  microsecond=0).isoformat(),
            "timeMax": now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat(),
            "singleEvents": True,
            "orderBy": "startTime",
        }
        try:
            r = requests.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events",
                headers={"Authorization": f"Bearer {token}"},
                params=params, timeout=10
            )
            if r.status_code != 200:
                return [{"time": "N/A", "summary": f"Calendar error {r.status_code}", "category": "⚪ Other"}]

            events = []
            for event in r.json().get("items", []):
                start = event.get("start", {})
                end   = event.get("end", {})
                start_dt = start.get("dateTime", start.get("date", ""))
                end_dt   = end.get("dateTime", end.get("date", ""))
                time_str = start_dt.split("T")[1][:5] if "T" in start_dt else "All day"
                end_str  = end_dt.split("T")[1][:5]   if "T" in end_dt   else "All day"
                color_id = str(event.get("colorId", ""))
                emoji, label = CALENDAR_COLOR_MAP.get(color_id, ("⚪", "Other"))
                events.append({
                    "time":     time_str,
                    "end_time": end_str,
                    "summary":  event.get("summary", "No title"),
                    "category": f"{emoji} {label}",
                })
            return events or [{"time": "N/A", "summary": "No events today", "category": "⚪ Other"}]
        except Exception as e:
            return [{"time": "N/A", "summary": f"Calendar error: {e}", "category": "⚪ Other"}]

    def get_vacant_slots(self, events: list[dict], workday_start: int = 9, workday_end: int = 19) -> list[dict]:
        """
        Computes genuinely free blocks (>=60 min) during the workday using each
        event's REAL start and end time, merging overlapping events so a long
        block counts as one occupied span.
        """
        def to_min(hhmm):
            h, m = map(int, hhmm.split(":"))
            return h * 60 + m

        # Build real busy intervals [start, end) in minutes
        busy = []
        for e in events:
            if e["time"] in ("All day", "N/A"):
                continue
            try:
                s = to_min(e["time"])
            except ValueError:
                continue
            end_str = e.get("end_time", "")
            try:
                en = to_min(end_str) if end_str and end_str not in ("All day", "N/A") else s + 60
            except ValueError:
                en = s + 60
            if en <= s:                     # guard against bad/zero-length events
                en = s + 60
            busy.append((s, en))

        busy.sort()

        # Merge overlapping/adjacent busy intervals
        merged = []
        for s, en in busy:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], en))
            else:
                merged.append((s, en))

        # Walk the workday, emitting gaps of >=60 min
        vacant = []
        cursor  = workday_start * 60
        day_end = workday_end * 60

        for s, en in merged:
            if s > day_end:
                break
            free_until = min(s, day_end)
            if free_until - cursor >= 60:
                vacant.append({
                    "start":      f"{cursor // 60:02d}:{cursor % 60:02d}",
                    "end":        f"{free_until // 60:02d}:{free_until % 60:02d}",
                    "duration_h": round((free_until - cursor) / 60, 1),
                })
            cursor = max(cursor, en)

        if day_end - cursor >= 60:
            vacant.append({
                "start":      f"{cursor // 60:02d}:{cursor % 60:02d}",
                "end":        f"{workday_end:02d}:00",
                "duration_h": round((day_end - cursor) / 60, 1),
            })

        return vacant

    def create_event(self, title: str, start_hhmm: str, end_hhmm: str) -> bool:
        """
        NEW: Creates a calendar event for today at the given IST times.
        Only called by midday_run after user approval via Notion to_do check.
        """
        token = self._get_token()
        if not token:
            print("  ⚠️  Cannot create event: no calendar token")
            return False

        today = get_ist_now().strftime("%Y-%m-%d")
        event_body = {
            "summary": f"[Life OS] {title}",
            "start": {
                "dateTime": f"{today}T{start_hhmm}:00+05:30",
                "timeZone": "Asia/Kolkata",
            },
            "end": {
                "dateTime": f"{today}T{end_hhmm}:00+05:30",
                "timeZone": "Asia/Kolkata",
            },
            "colorId": "9",   # Blue = Office category
            "description": "Created by Life OS automation",
        }
        try:
            r = requests.post(
                f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=event_body, timeout=15
            )
            if r.status_code in (200, 201):
                print(f"  ✅ Calendar event created: {start_hhmm}–{end_hhmm} — {title}")
                return True
            else:
                print(f"  ⚠️  Event create failed: HTTP {r.status_code}: {r.text[:100]}")
                return False
        except Exception as e:
            print(f"  ⚠️  Event create error: {e}")
            return False


# ─── Discord Client ───────────────────────────────────────────────────────────

class DiscordClient:
    """
    Sends messages to Discord via a webhook URL.

    Setup (one-time, 2 minutes):
    1. In your Discord server → Channel Settings → Integrations → Create Webhook
    2. Copy the webhook URL
    3. In GitHub repo → Settings → Secrets → Add DISCORD_WEBHOOK_URL

    No bot needed, no server needed. Just the webhook URL.
    """

    def __init__(self):
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")

    def send(self, content: str, username: str = "Life OS") -> bool:
        """Posts a message to Discord. Returns True on success."""
        if not self.webhook_url:
            print("  ⚠️  DISCORD_WEBHOOK_URL not set — skipping Discord")
            return False
        if len(content) > 2000:
            content = content[:1997] + "…"
        try:
            r = requests.post(
                self.webhook_url,
                json={"content": content, "username": username},
                timeout=10
            )
            # Discord returns 204 No Content on success
            if r.status_code == 204:
                print("  ✅ Discord message sent")
                return True
            else:
                print(f"  ⚠️  Discord error: HTTP {r.status_code}: {r.text[:100]}")
                return False
        except Exception as e:
            print(f"  ⚠️  Discord send error: {e}")
            return False
