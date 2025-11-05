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
                    print(f"   Attempt {attempt}/{self.max_retries}...")
                result = func(*args, **kwargs)
                if attempt > 1:
                    print(f"   ✅ Succeeded on attempt {attempt}")
                return result
            except Exception as e:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    print(f"   ⚠️ Attempt {attempt} failed: {str(e)[:100]}")
                    print(f"   ⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ All {self.max_retries} attempts failed")
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
                return ["Calendar access unavailable"]
                
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
                return ["Calendar access error"]
                
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
                
                formatted_events.append(f"{time_str}: {summary}")
            
            return formatted_events if formatted_events else ["No events scheduled today"]
            
        except Exception as e:
            print(f"Calendar error: {e}")
            return ["Calendar temporarily unavailable"]

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
                print(f"   ⚠️ Error parsing task: {e}")
                items.append("Weekly task")
        
        return items if items else ["All weekly items completed"]

    def get_weekly_checklist_items(self):
        """Get unchecked weekly checklist with retry"""
        try:
            print("📋 Getting Weekly Checklist items...")
            items = self.notion_retry(self._query_weekly_checklist)
            print(f"   Found {len(items)} unchecked items")
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
                print(f"   ⚠️ Error parsing goal: {e}")
                goals.append("Strategic goal")
        
        return goals if goals else ["Define new strategic goals"]

    def get_strategic_goals(self):
        """Get strategic goals with retry"""
        try:
            print("🎯 Getting Strategic Goals...")
            goals = self.notion_retry(self._query_strategic_goals)
            print(f"   Found {len(goals)} active goals")
            return goals
        except Exception as e:
            print(f"❌ Strategic goals failed: {e}")
            return ["Strategic milestone planning"]

    def _query_recent_journal_entries_with_content(self):
        """Get recent journal entries WITH full content"""
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
                
                # Get journal content from AI Prompt field
                content = 'No content'
                if 'AI Prompt' in entry['properties'] and entry['properties']['AI Prompt']['rich_text']:
                    content_parts = []
                    for text_part in entry['properties']['AI Prompt']['rich_text']:
                        if 'plain_text' in text_part:
                            content_parts.append(text_part['plain_text'])
                    content = ''.join(content_parts) if content_parts else 'No content'
                
                # Get life areas
                life_areas = []
                if 'Life Area' in entry['properties'] and entry['properties']['Life Area']['multi_select']:
                    life_areas = [area['name'] for area in entry['properties']['Life Area']['multi_select']]
                
                # Get created date
                created_date = 'Unknown date'
                if 'Created time' in entry['properties'] and entry['properties']['Created time']['created_time']:
                    created_date = entry['properties']['Created time']['created_time'][:10]  # Just the date part
                
                journal_entries.append({
                    'title': title,
                    'content': content[:500],  # First 500 characters
                    'life_areas': life_areas,
                    'date': created_date
                })
                
            except Exception as e:
                print(f"   ⚠️ Error parsing journal entry: {e}")
                journal_entries.append({
                    'title': 'Recent reflection',
                    'content': 'Journal entry content unavailable',
                    'life_areas': [],
                    'date': 'Unknown'
                })
        
        return journal_entries if journal_entries else [{
            'title': 'Start journaling',
            'content': 'Begin your daily reflection practice',
            'life_areas': ['Personal Growth'],
            'date': 'Today'
        }]

    def get_recent_journal_entries_with_content(self):
        """Get recent journal entries with full content and retry logic"""
        try:
            print("📝 Getting recent journal entries with content...")
            entries = self.notion_retry(self._query_recent_journal_entries_with_content)
            print(f"   Found {len(entries)} detailed entries")
            
            # Log journal preview for debugging
            for i, entry in enumerate(entries[:2], 1):
                print(f"   Journal {i}: {entry['title']} ({entry['date']}) - Areas: {', '.join(entry['life_areas'])}")
                print(f"      Content preview: {entry['content'][:100]}...")
            
            return entries
        except Exception as e:
            print(f"❌ Journal entries failed: {e}")
            return [{
                'title': 'Daily reflection practice',
                'content': 'Continue building consistent journaling habits',
                'life_areas': ['Personal Growth'],
                'date': 'Today'
            }]

    def generate_strategic_briefing(self, checklist_items, strategic_goals, journal_entries, calendar_events):
        """Generate AI-powered strategic daily briefing with deep journal analysis"""
        current_datetime = self.get_current_ist_time()
        
        # Prepare detailed journal content for analysis
        journal_analysis_data = []
        for entry in journal_entries:
            areas_text = ', '.join(entry['life_areas']) if entry['life_areas'] else 'General'
            journal_analysis_data.append(f"ENTRY: '{entry['title']}' (Date: {entry['date']}, Life Areas: {areas_text}) CONTENT: {entry['content']}")
        
        journal_text = ' | '.join(journal_analysis_data)
        
        prompt = f"Create exactly 5 numbered motivational insights using this REAL data. Do NOT include any intro text - start directly with numbered list. IMPORTANT: Never suggest activities between 10:00 PM and 6:30 AM (sleep time). WEEKLY TASKS (unchecked): {'; '.join(checklist_items[:3])}. STRATEGIC GOALS (active): {'; '.join(strategic_goals[:3])}. DETAILED JOURNAL ENTRIES: {journal_text}. TODAY'S CALENDAR: {'; '.join(calendar_events[:5])}. Format requirements: 1. [insight about specific weekly task with optimal 7AM-9PM timing] 2. [insight about specific strategic goal with daytime timing reference] 3. [DEEP ANALYSIS: Read the actual journal content and provide insightful commentary, motivation, or reflection based on what was actually written - reference specific thoughts, patterns, emotions, or themes from the journal entries] 4. [insight about specific calendar event with prep timing 6:30AM-9:30PM] 5. [evening reward/unwind tip 7PM-9:30PM based on journal mood and free time]. Be specific, reference actual data including journal content, respect sleep schedule."
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a motivational life coach and journal analyst who reads actual journal content to provide deep, personalized insights. Create exactly 5 numbered insights with no intro text. Start directly with '1.' For point 3, analyze the actual journal content deeply - comment on themes, emotions, patterns, and provide thoughtful motivation based on what was actually written. Never suggest activities between 10:00 PM and 6:30 AM. Reference specific data provided."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=500,  # Increased for deeper journal analysis
                temperature=0.7  # Slightly higher for more insightful commentary
            )
            
            insights = response.choices[0].message.content.strip()
            return insights
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            fallback = "1. Focus on completing your most important weekly task during peak morning hours (8:00-11:00 AM) - every small step builds momentum.\n2. Make measurable progress on your strategic initiatives during focused afternoon sessions (2:00-5:00 PM) - consistency creates results.\n3. Your recent journal reflections show growth in self-awareness - continue this valuable practice of daily reflection as it builds emotional intelligence and clarity.\n4. Approach today's scheduled activities with intentional focus during your productive daytime hours.\n5. Schedule relaxation time between 8:00-9:30 PM before your sleep routine - balance drives sustainable performance."
            return fallback

    def _update_notion_block(self, briefing_content):
        """Update Notion page with new briefing format"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        response = requests.get(blocks_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get blocks: HTTP {response.status_code}")
            
        blocks = response.json()
        
        briefing_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'AI-Generated Morning Insights' in block['callout']['rich_text'][0].get('plain_text', '')):
                briefing_block_id = block['id']
                break
        
        current_datetime = self.get_current_ist_time()
        full_content = f"🤖 AI-Generated Morning Insights - {current_datetime}\n\nBased on your calendar, recent notes, and patterns, here's your personalized briefing for today.\n\n**TODAY'S FOCUS:**\n{briefing_content}"
        
        new_block_data = {
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": full_content}}],
                "icon": {"emoji": "🤖"},
                "color": "blue_background"
            }
        }
        
        if briefing_block_id:
            update_url = f"https://api.notion.com/v1/blocks/{briefing_block_id}"
            response = requests.patch(update_url, headers=headers, json=new_block_data, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to update block: HTTP {response.status_code}")
            return "updated"
        else:
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            payload = {"children": [new_block_data]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to create block: HTTP {response.status_code}")
            return "created"

    def update_daily_briefing_section(self, briefing_content):
        """Update briefing with retry"""
        try:
            print("📝 Updating Notion page...")
            action = self.notion_retry(self._update_notion_block, briefing_content)
            print(f"   ✅ Successfully {action} daily briefing!")
        except Exception as e:
            print(f"❌ Failed to update Notion: {str(e)}")

    def run(self):
        """Main execution"""
        print(f"🎯 Strategic Daily Briefing Generator (Journal Content Analysis)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay")
        print(f"😴 Sleep schedule: {self.sleep_start} - {self.sleep_end} (protected)\n")
        
        print("📅 Getting calendar events...")
        calendar_events = self.get_calendar_events_today()
        print(f"   Found {len(calendar_events)} events")
        
        print("📋 Getting weekly checklist...")
        checklist_items = self.get_weekly_checklist_items()
        print(f"   Found {len(checklist_items)} items")
        
        print("🎯 Getting strategic goals...")
        strategic_goals = self.get_strategic_goals()
        print(f"   Found {len(strategic_goals)} goals")
        
        print("📝 Getting detailed journal entries...")
        journal_entries = self.get_recent_journal_entries_with_content()
        print(f"   Found {len(journal_entries)} detailed entries")
        
        print("\n🧠 Generating deep journal-aware insights...")
        briefing = self.generate_strategic_briefing(checklist_items, strategic_goals, journal_entries, calendar_events)
        
        self.update_daily_briefing_section(briefing)
        print(f"\n✅ Completed at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    briefing = StrategicDailyBriefing()
    briefing.run()
