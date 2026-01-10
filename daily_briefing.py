import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import jwt
import time

class StrategicDailyBriefing:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        
        # Strategic databases
        self.weekly_checklist_db_id = os.getenv('WEEKLY_CHECKLIST_DB_ID')
        self.strategic_goals_db_id = os.getenv('STRATEGIC_GOALS_DB_ID')
        self.daily_journal_db_id = os.getenv('DAILY_JOURNAL_DB_ID')
        
        # Sleep schedule
        self.sleep_start = "22:00"
        self.sleep_end = "06:30"
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 3
        
        # Google Calendar setup
        try:
            credentials_json = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.google_credentials = credentials_json
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        except Exception as e:
            print(f"Google setup error: {e}")
            self.google_credentials = None

    def get_current_ist_time(self):
        """Get current IST time correctly"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        return now_ist.strftime("%A, %B %d, %Y - %I:%M %p IST")

    def notion_retry(self, func, *args, **kwargs):
        """Retry wrapper for Notion API calls with exponential backoff"""
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

    def get_google_access_token(self):
        """Get access token for Google Calendar API"""
        try:
            now = int(time.time())
            payload = {
                'iss': self.google_credentials['client_email'],
                'scope': 'https://www.googleapis.com/auth/calendar.readonly',
                'aud': 'https://oauth2.googleapis.com/token',
                'exp': now + 3600,
                'iat': now
            }
            
            private_key = self.google_credentials['private_key']
            token = jwt.encode(payload, private_key, algorithm='RS256')
            
            data = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'assertion': token
            }
            
            response = requests.post('https://oauth2.googleapis.com/token', data=data)
            return response.json().get('access_token')
            
        except Exception as e:
            print(f"Token generation error: {e}")
            return None

    def get_calendar_events_today(self):
        """Get today's calendar events"""
        try:
            access_token = self.get_google_access_token()
            if not access_token:
                return [{"time": "N/A", "summary": "Calendar access unavailable"}]
            
            headers = {'Authorization': f'Bearer {access_token}'}
            
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
            
            url = f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events"
            params = {
                'timeMin': start_time,
                'timeMax': end_time,
                'singleEvents': True,
                'orderBy': 'startTime'
            }
            
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code != 200:
                print(f"Calendar API error: {response.status_code}")
                return [{"time": "N/A", "summary": "Calendar access error"}]
            
            events_data = response.json()
            events = events_data.get('items', [])
            
            formatted_events = []
            for event in events:
                start = event.get('start', {})
                summary = event.get('summary', 'No title')
                
                start_time = start.get('dateTime', start.get('date', ''))
                if 'T' in start_time:
                    time_str = start_time.split('T')[1][:5]
                else:
                    time_str = 'All day'
                
                formatted_events.append({"time": time_str, "summary": summary})
            
            return formatted_events if formatted_events else [{"time": "N/A", "summary": "No events scheduled today"}]
            
        except Exception as e:
            print(f"Calendar error: {e}")
            return [{"time": "N/A", "summary": "Calendar temporarily unavailable"}]

    def _query_weekly_checklist(self):
        """Get unchecked weekly checklist items"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query"
        query_data = {
            "filter": {
                "property": "Done?",
                "checkbox": {
                    "equals": False
                }
            },
            "page_size": 10
        }
        
        response = requests.post(query_url, headers=headers, json=query_data, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        
        data = response.json()
        results = data.get('results', [])
        
        items = []
        for item in results:
            try:
                name = 'Untitled task'
                if 'Task' in item['properties'] and item['properties']['Task']['title']:
                    name = item['properties']['Task']['title'][0]['plain_text']
                items.append(name)
            except Exception as e:
                print(f"  ⚠️ Error parsing task: {e}")
                items.append("Weekly task")
        
        return items if items else ["All weekly items completed"]

    def get_weekly_checklist_items(self):
        """Get unchecked weekly checklist with retry"""
        try:
            print("📋 Getting Weekly Checklist items...")
            items = self.notion_retry(self._query_weekly_checklist)
            print(f"  Found {len(items)} unchecked items")
            return items
        except Exception as e:
            print(f"❌ Weekly checklist failed: {e}")
            return ["Weekly planning review"]

    def _query_strategic_goals(self):
        """Get active strategic goals"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{self.strategic_goals_db_id}/query"
        query_data = {
            "filter": {"property": "Status", "status": {"equals": "In progress"}},
            "page_size": 5
        }
        
        response = requests.post(query_url, headers=headers, json=query_data, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        
        data = response.json()
        results = data.get('results', [])
        
        goals = []
        for goal in results:
            try:
                name = 'Untitled Goal'
                if 'Name' in goal['properties'] and goal['properties']['Name']['title']:
                    name = goal['properties']['Name']['title'][0]['plain_text']
                
                progress = 0
                if 'Progress' in goal['properties'] and goal['properties']['Progress']['number'] is not None:
                    progress = int(goal['properties']['Progress']['number'])
                
                goals.append(f"{name} ({progress}% complete)")
            except Exception as e:
                print(f"  ⚠️ Error parsing goal: {e}")
                goals.append("Strategic goal")
        
        return goals if goals else ["Define new strategic goals"]

    def get_strategic_goals(self):
        """Get strategic goals with retry"""
        try:
            print("🎯 Getting Strategic Goals...")
            goals = self.notion_retry(self._query_strategic_goals)
            print(f"  Found {len(goals)} active goals")
            return goals
        except Exception as e:
            print(f"❌ Strategic goals failed: {e}")
            return ["Strategic milestone planning"]

    def _get_page_content(self, page_id):
        """Get the full content of a Notion page"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        response = requests.get(blocks_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get page content: HTTP {response.status_code}")
        
        blocks_data = response.json()
        blocks = blocks_data.get('results', [])
        
        content_parts = []
        
        def extract_text_from_rich_text(rich_text_array):
            """Extract plain text from rich text array"""
            if not rich_text_array:
                return ""
            text_parts = []
            for text_obj in rich_text_array:
                if text_obj.get('plain_text'):
                    text_parts.append(text_obj['plain_text'])
            return ''.join(text_parts)
        
        for block in blocks:
            try:
                block_type = block.get('type', '')
                
                if block_type == 'paragraph':
                    text = extract_text_from_rich_text(block['paragraph']['rich_text'])
                    if text.strip():
                        content_parts.append(text)
                
                elif block_type == 'heading_1':
                    text = extract_text_from_rich_text(block['heading_1']['rich_text'])
                    if text.strip():
                        content_parts.append(f"# {text}")
                
                elif block_type == 'heading_2':
                    text = extract_text_from_rich_text(block['heading_2']['rich_text'])
                    if text.strip():
                        content_parts.append(f"## {text}")
                
                elif block_type == 'heading_3':
                    text = extract_text_from_rich_text(block['heading_3']['rich_text'])
                    if text.strip():
                        content_parts.append(f"### {text}")
                
                elif block_type == 'bulleted_list_item':
                    text = extract_text_from_rich_text(block['bulleted_list_item']['rich_text'])
                    if text.strip():
                        content_parts.append(f"• {text}")
                
                elif block_type == 'numbered_list_item':
                    text = extract_text_from_rich_text(block['numbered_list_item']['rich_text'])
                    if text.strip():
                        content_parts.append(f"• {text}")
                
                elif block_type == 'to_do':
                    text = extract_text_from_rich_text(block['to_do']['rich_text'])
                    checked = block['to_do']['checked']
                    if text.strip():
                        status = "✅" if checked else "☐"
                        content_parts.append(f"{status} {text}")
                
                elif block_type == 'quote':
                    text = extract_text_from_rich_text(block['quote']['rich_text'])
                    if text.strip():
                        content_parts.append(f"> {text}")
                
                elif block_type == 'callout':
                    text = extract_text_from_rich_text(block['callout']['rich_text'])
                    if text.strip():
                        content_parts.append(f"💡 {text}")
                
            except Exception as e:
                print(f"  ⚠️ Error parsing block {block_type}: {e}")
        
        full_content = '\n'.join(content_parts)
        return full_content[:800] if full_content else "No content found"

    def _query_recent_journal_entries_with_page_content(self):
        """Get recent journal entries WITH full page content"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{self.daily_journal_db_id}/query"
        query_data = {
            "sorts": [{"property": "Created time", "direction": "descending"}],
            "page_size": 3
        }
        
        response = requests.post(query_url, headers=headers, json=query_data, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        
        data = response.json()
        results = data.get('results', [])
        
        journal_entries = []
        
        for entry in results:
            try:
                # Get journal title
                title = 'Journal Entry'
                if 'Name' in entry['properties'] and entry['properties']['Name']['title']:
                    title = entry['properties']['Name']['title'][0]['plain_text']
                
                # Get life areas
                life_areas = []
                if 'Life Area' in entry['properties'] and entry['properties']['Life Area']['multi_select']:
                    life_areas = [area['name'] for area in entry['properties']['Life Area']['multi_select']]
                
                # Get created date
                created_date = 'Unknown date'
                if 'Created time' in entry['properties'] and entry['properties']['Created time']['created_time']:
                    created_date = entry['properties']['Created time']['created_time'][:10]
                
                # Get page ID to fetch content
                page_id = entry['id']
                
                print(f"  📖 Reading: {title} ({created_date})")
                
                # Fetch the actual page content
                page_content = self._get_page_content(page_id)
                
                journal_entries.append({
                    'title': title,
                    'content': page_content,
                    'life_areas': life_areas,
                    'date': created_date,
                    'page_id': page_id
                })
                
                print(f"  ✅ Content loaded: {len(page_content)} characters")
                
            except Exception as e:
                print(f"  ⚠️ Error processing journal entry: {e}")
                journal_entries.append({
                    'title': 'Recent journal entry',
                    'content': 'Journal content temporarily unavailable',
                    'life_areas': [],
                    'date': 'Recent',
                    'page_id': ''
                })
        
        return journal_entries if journal_entries else [{
            'title': 'Start journaling',
            'content': 'Begin writing daily reflections to track your thoughts and growth',
            'life_areas': ['Personal Growth'],
            'date': 'Today',
            'page_id': ''
        }]

    def get_recent_journal_entries_with_page_content(self):
        """Get recent journal entries with full page content and retry logic"""
        try:
            print("📝 Getting detailed journal entries with page content...")
            entries = self.notion_retry(self._query_recent_journal_entries_with_page_content)
            print(f"  ✅ Successfully loaded {len(entries)} journal entries with content")
            return entries
        except Exception as e:
            print(f"❌ Journal content reading failed: {e}")
            return [{
                'title': 'Daily reflection practice',
                'content': 'Continue building consistent journaling habits for self-awareness and growth',
                'life_areas': ['Personal Growth'],
                'date': 'Today',
                'page_id': ''
            }]

    def sanitize_content_for_notion(self, content):
        """Sanitize content to prevent Notion API errors and truncation"""
        if not content:
            return "Daily briefing content unavailable"
        
        import re
        
        # Remove control characters and non-printable characters
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)
        
        # Replace problematic unicode characters
        content = content.encode('utf-8', errors='ignore').decode('utf-8')
        
        # Increased limits to prevent truncation
        max_content_length = 1950
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
            print(f"  ⚠️ Content truncated from {len(content)} to {max_content_length} characters")
        
        # Ensure content is not empty
        if not content.strip():
            content = "Daily briefing generated successfully"
        
        return content

    def has_vacant_time_slots(self, calendar_events):
        """Check if there are vacant time slots in the calendar"""
        # If no events or only placeholder events, we have vacant time
        if not calendar_events or calendar_events[0]['time'] == 'N/A':
            return True
        
        # Count actual scheduled events (excluding all-day events)
        scheduled_events = [e for e in calendar_events if e['time'] != 'All day' and e['time'] != 'N/A']
        
        # If less than 6 events, there are likely vacant slots
        return len(scheduled_events) < 6

    def generate_strategic_briefing(self, checklist_items, strategic_goals, journal_entries, calendar_events):
        """Generate 5-part daily insight using GPT"""
        current_datetime = self.get_current_ist_time()
        
        # Prepare journal content
        journal_summaries = []
        for i, entry in enumerate(journal_entries[:3], 1):
            areas_text = ', '.join(entry['life_areas']) if entry['life_areas'] else 'General'
            content_summary = entry['content'][:400] if entry['content'] else 'No content'
            journal_summaries.append(f"{entry['title']} ({entry['date']}) - {areas_text}: {content_summary}")
        
        journal_text = ' | '.join(journal_summaries)
        
        # Prepare calendar events
        calendar_text = []
        for event in calendar_events:
            calendar_text.append(f"{event['time']}: {event['summary']}")
        
        # Check for vacant time slots
        has_vacant_slots = self.has_vacant_time_slots(calendar_events)
        
        prompt = f"""You are an AI briefing assistant. Today is {current_datetime}. 

DATA:
- WEEKLY TASKS: {'; '.join(checklist_items[:5])}
- STRATEGIC GOALS: {'; '.join(strategic_goals[:3])}
- RECENT JOURNAL ENTRIES: {journal_text}
- TODAY'S CALENDAR: {'; '.join(calendar_text)}
- VACANT TIME SLOTS AVAILABLE: {"Yes" if has_vacant_slots else "No"}

Create EXACTLY 5 brief, numbered insights for the user's morning briefing. Write naturally - avoid starting every sentence with "You". Use varied sentence structures like "The schedule shows...", "Today's priority is...", "Consider...", "Worth noting...", etc. Only use "You" when directly addressing the user about specific actions they took or should take.

Format your response EXACTLY as follows (number each point, NO headings in brackets):

1. Review the recent journal entries and calendar events. Find something unique or meaningful they accomplished or experienced. Give a thoughtful, grateful insight that acknowledges this (2-3 sentences max). Use natural language - describe what happened, not "You did X".

2. From the Weekly Tasks list, recommend ONE specific task to tackle today. Explain why briefly (1-2 sentences). Use varied language like "Today's priority could be...", "Worth tackling...", "Consider completing..."

3. From the Strategic Goals, suggest ONE specific action to take today. Be actionable and brief (1-2 sentences). Vary the language structure.

4. {"Identify 2-3 vacant time blocks in the calendar suitable for working on tasks. Format naturally as 'The [time] slot works well for [task type]' or 'Consider using [time] for [task]' (2-3 suggestions max)." if has_vacant_slots else "Since the calendar is packed today, suggest 2-3 task types that fit into short breaks or flexible moments. Do NOT mention specific times. Use natural phrasing like 'Quick breaks work well for...', 'Short moments can be used to...'"}

5. {"Suggest ONE fun, relaxing activity for a vacant time slot in the second half of the day. Include the specific time if there's a clear opening. Use natural language like 'The [time] slot is perfect for [activity]' or simply suggest '[activity]' if no clear slot." if has_vacant_slots else "Suggest ONE fun, relaxing activity that fits flexibly into the second half of the day between commitments. Do NOT mention specific times. Use natural phrasing like 'Between commitments, [activity] offers a good break' or 'Consider [activity] when there's a flexible moment'"}

Keep TOTAL response under 800 characters. Write naturally as an AI briefing assistant - be warm, direct, and actionable."""

        try:
            print("  🤖 Calling GPT...")
            
            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=prompt,
                reasoning={"effort": "medium"},
                text={"verbosity": "low"}
            )
            
            insights = response.output_text.strip()
            
            print("  ✅ Daily insight generated")
            return insights
            
        except Exception as e:
            print(f"  ❌ GPT error: {e}")
            # Fallback response
            fallback = f"""1. The Shantidham lunch plan and those evening Lego/game sessions with Pam show consistent follow-through on building meaningful rituals together.

2. The Physio Infographic is scheduled for today and ties directly to physiotherapy progress - completing it maintains momentum.

3. Worth confirming or booking the skin specialist appointment, bringing photos and notes about dry hands for an efficient visit.

4. {"Short breaks throughout the day work well for checking Robu device status, quick-editing Insights, or doing 10-minute physio stretches." if has_vacant_slots else "Quick task reviews during breaks can maintain progress despite a busy schedule."}

5. {"Building the Lego set with Pam or a short NFSMW session offers a relaxing creative break between commitments." if has_vacant_slots else "Between commitments, building Lego or gaming provides quick creative breaks."}"""
            
            return fallback

    def _update_notion_block_safe(self, briefing_content):
        """Update Notion page with enhanced error handling"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Get current blocks
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        response = requests.get(blocks_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get blocks: HTTP {response.status_code}")
        
        blocks = response.json()
        
        # Find existing briefing block
        briefing_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'Daily Insight' in block['callout']['rich_text'][0].get('plain_text', '')):
                briefing_block_id = block['id']
                break
        
        current_datetime = self.get_current_ist_time()
        
        # Create header and content
        header_content = f"🌅 Daily Insight - {current_datetime}\n\n"
        
        # Combine header and briefing content
        full_content = header_content + briefing_content
        
        # Ensure content is within limits
        full_content = self.sanitize_content_for_notion(full_content)
        
        print(f"  📊 Final content size: {len(full_content)} characters")
        
        new_block_data = {
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": full_content
                        }
                    }
                ],
                "icon": {
                    "emoji": "🌅"
                },
                "color": "blue_background"
            }
        }
        
        try:
            if briefing_block_id:
                # Update existing block
                update_url = f"https://api.notion.com/v1/blocks/{briefing_block_id}"
                response = requests.patch(update_url, headers=headers, json=new_block_data, timeout=15)
                
                if response.status_code != 200:
                    print(f"  ❌ Update failed: {response.status_code} - {response.text[:300]}")
                    raise Exception(f"Failed to update block: HTTP {response.status_code}")
                
                return "updated"
            else:
                # Create new block
                create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
                payload = {"children": [new_block_data]}
                response = requests.patch(create_url, headers=headers, json=payload, timeout=15)
                
                if response.status_code != 200:
                    print(f"  ❌ Create failed: {response.status_code} - {response.text[:300]}")
                    raise Exception(f"Failed to create block: HTTP {response.status_code}")
                
                return "created"
            
        except Exception as e:
            print(f"  💡 Detailed error: {str(e)}")
            print(f"  📊 Content length: {len(full_content)} characters")
            raise e

    def update_daily_briefing_section(self, briefing_content):
        """Update briefing with enhanced retry and error handling"""
        try:
            print("📝 Updating Notion page with daily insight...")
            action = self.notion_retry(self._update_notion_block_safe, briefing_content)
            print(f"  ✅ Successfully {action} daily insight!")
        except Exception as e:
            print(f"❌ Failed to update Notion after all attempts: {str(e)}")

    def run(self):
        """Main execution"""
        print(f"🌅 Daily Insight Generator (5-Part Format)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay\n")
        
        print("📅 Getting calendar events...")
        calendar_events = self.get_calendar_events_today()
        print(f"  Found {len(calendar_events)} events")
        
        print("📋 Getting weekly checklist...")
        checklist_items = self.get_weekly_checklist_items()
        print(f"  Found {len(checklist_items)} items")
        
        print("🎯 Getting strategic goals...")
        strategic_goals = self.get_strategic_goals()
        print(f"  Found {len(strategic_goals)} goals")
        
        print("📝 Reading journal entries...")
        journal_entries = self.get_recent_journal_entries_with_page_content()
        print(f"  ✅ Analyzed {len(journal_entries)} journal entries")
        
        print("\n🧠 Generating 5-part daily insight...")
        briefing = self.generate_strategic_briefing(checklist_items, strategic_goals, journal_entries, calendar_events)
        print(f"  📊 Generated insight: {len(briefing)} characters")
        
        self.update_daily_briefing_section(briefing)
        print(f"\n✅ Process completed at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    briefing = StrategicDailyBriefing()
    briefing.run()
