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
                print(f"   ⚠️ Error parsing block {block_type}: {e}")
        
        full_content = '\n'.join(content_parts)
        return full_content[:800] if full_content else "No content found"  # Reduced for better management

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
            "page_size": 2
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
                
                print(f"   📖 Reading: {title} ({created_date})")
                
                # Fetch the actual page content
                page_content = self._get_page_content(page_id)
                
                journal_entries.append({
                    'title': title,
                    'content': page_content,
                    'life_areas': life_areas,
                    'date': created_date,
                    'page_id': page_id
                })
                
                print(f"      ✅ Content loaded: {len(page_content)} characters")
                
            except Exception as e:
                print(f"   ⚠️ Error processing journal entry: {e}")
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
            print(f"   ✅ Successfully loaded {len(entries)} journal entries with content")
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
        if
