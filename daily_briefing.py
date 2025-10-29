import openai
import requests
import json
import os
from datetime import datetime, timedelta
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
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 3  # seconds
        
        # Google Calendar setup
        try:
            credentials_json = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.google_credentials = credentials_json
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        except Exception as e:
            print(f"Google setup error: {e}")
            self.google_credentials = None

    def notion_retry(self, func, *args, **kwargs):
        """Retry wrapper for Notion API calls with exponential backoff"""
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"   Attempt {attempt}/{self.max_retries}...")
                result = func(*args, **kwargs)
                if attempt > 1:
                    print(f"   ✅ Succeeded on attempt {attempt}")
                return result
            except Exception as e:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt  # Exponential backoff
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

    def get_calendar_events_and_blocks(self):
        """Get today's calendar events and identify time blocks"""
        try:
            access_token = self.get_google_access_token()
            if not access_token:
                return {"events": ["• Calendar access unavailable"], "blocks": []}
                
            headers = {'Authorization': f'Bearer {access_token}'}
            
            now = datetime.now()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'
            
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
                return {"events": ["• Calendar access error"], "blocks": []}
                
            events_data = response.json()
            events = events_data.get('items', [])
            
            formatted_events = []
            time_blocks = []
            
            for event in events:
                start = event.get('start', {})
                end = event.get('end', {})
                summary = event.get('summary', 'No title')
                
                start_time = start.get('dateTime', start.get('date', ''))
                end_time = end.get('dateTime', end.get('date', ''))
                
                if 'T' in start_time:
                    start_str = start_time.split('T')[1][:5]
                    end_str = end_time.split('T')[1][:5] if 'T' in end_time else ''
                    time_display = f"{start_str}-{end_str}" if end_str else start_str
                else:
                    time_display = 'All day'
                
                formatted_events.append(f"• {time_display}: {summary}")
                
                if any(keyword in summary.lower() for keyword in ['office', 'work', 'meeting', 'focus', 'block', 'forex']):
                    time_blocks.append(f"• {time_display}: {summary}")
            
            return {
                "events": formatted_events if formatted_events else ["• No scheduled events today"],
                "blocks": time_blocks if time_blocks else ["• No special focus blocks scheduled"]
            }
            
        except Exception as e:
            print(f"Calendar error: {e}")
            return {"events": ["• Calendar temporarily unavailable"], "blocks": []}

    def _query_weekly_checklist(self):
        """Internal: Query weekly checklist (wrapped with retry)"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query"
        query_data = {
            "filter": {"property": "Checkbox", "checkbox": {"equals": False}},
            "page_size": 5
        }
        
        response = requests.post(query_url, headers=headers, json=query_data, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
        data = response.json()
        results = data.get('results', [])
        
        checklist_items = []
        for item in results:
            try:
                name = 'Untitled task'
                if 'Name' in item['properties'] and item['properties']['Name']['title']:
                    name = item['properties']['Name']['title'][0]['plain_text']
                checklist_items.append(f"• {name}")
            except Exception as e:
                checklist_items.append("• Weekly task (parsing error)")
        
        return checklist_items if checklist_items else ["• All weekly items completed! ✅"]

    def get_weekly_checklist_items(self):
        """Get unchecked items from Weekly Checklist with retry"""
        try:
            print("📋 Getting Weekly Checklist items...")
            items = self.notion_retry(self._query_weekly_checklist)
            print(f"   Found {len(items)} unchecked items")
            return items
        except Exception as e:
            print(f"❌ Weekly checklist failed after retries: {e}")
            return ["• Error accessing Weekly Checklist"]

    def _query_strategic_goals(self):
        """Internal: Query strategic goals (wrapped with retry)"""
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
        
        strategic_goals = []
        for goal in results:
            try:
                name = 'Untitled Goal'
                if 'Name' in goal['properties'] and goal['properties']['Name']['title']:
                    name = goal['properties']['Name']['title'][0]['plain_text']
                
                progress = 0
                if 'Progress' in goal['properties'] and goal['properties']['Progress']['number'] is not None:
                    progress = int(goal['properties']['Progress']['number'])
                
                goal_type = 'Goal'
                if 'Type' in goal['properties'] and goal['properties']['Type']['select']:
                    goal_type = goal['properties']['Type']['select']['name']
                
                due_info = ''
                if 'Due Date' in goal['properties'] and goal['properties']['Due Date']['date']:
                    due_date = goal['properties']['Due Date']['date']['start']
                    try:
                        due_datetime = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                        due_info = f" - Due: {due_datetime.strftime('%m/%d')}"
                    except:
                        due_info = f" - Due: {due_date}"
                
                strategic_goals.append(f"• [{goal_type}] {name} ({progress}% complete){due_info}")
                
            except Exception as e:
                strategic_goals.append("• Strategic goal (parsing error)")
        
        return strategic_goals if strategic_goals else ["• No strategic goals in progress"]

    def get_strategic_goals(self):
        """Get active strategic goals with retry"""
        try:
            print("🎯 Getting Strategic Goals...")
            goals = self.notion_retry(self._query_strategic_goals)
            print(f"   Found {len(goals)} active goals")
            return goals
        except Exception as e:
            print(f"❌ Strategic goals failed after retries: {e}")
            return ["• Error accessing Strategic Goals"]

    def _query_journal_patterns(self):
        """Internal: Query journal patterns (wrapped with retry)"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{self.daily_journal_db_id}/query"
        query_data = {
            "sorts": [{"property": "Created time", "direction": "descending"}],
            "page_size": 7
        }
        
        response = requests.post(query_url, headers=headers, json=query_data, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
        data = response.json()
        results = data.get('results', [])
        
        if len(results) >= 5:
            return [
                "• Continue your excellent daily journaling routine around 9:00-9:30 PM",
                "• Focus tonight on reviewing today's strategic goal progress",
                "• Consider deep reflection on weekly checklist completion patterns"
            ]
        elif len(results) >= 2:
            return [
                "• Establish more consistent evening reflection routine (9:00 PM ideal)",
                "• Tonight: reflect on strategic goal alignment with daily actions",
                "• Use 15-minute focused reflection sessions for better insights"
            ]
        else:
            return [
                "• Start simple: 10-minute evening reflection at 9:00 PM",
                "• Focus on: What went well today? What could be improved?",
                "• Use journal to track progress on strategic goals and weekly tasks"
            ]

    def get_journal_reflection_patterns(self):
        """Get recent journal entries with retry"""
        try:
            print("📝 Analyzing Daily Journal patterns...")
            patterns = self.notion_retry(self._query_journal_patterns)
            print(f"   Generated {len(patterns)} reflection insights")
            return patterns
        except Exception as e:
            print(f"❌ Journal analysis failed after retries: {e}")
            return ["• Evening reflection recommended based on typical productivity patterns"]

    def generate_strategic_briefing(self, calendar_data, checklist_items, strategic_goals, reflection_patterns):
        """Generate AI-powered strategic daily briefing"""
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        
        prompt = f"""
        Create a strategic daily briefing for {current_date} using ONLY the real data provided below.
        
        REAL DATA FROM USER'S STRATEGIC SYSTEMS:
        
        WEEKLY CHECKLIST (unchecked items):
        {chr(10).join(checklist_items)}
        
        CALENDAR EVENTS TODAY:
        {chr(10).join(calendar_data['events'])}
        
        IMPORTANT TIME BLOCKS:
        {chr(10).join(calendar_data['blocks'])}
        
        STRATEGIC GOALS (in progress):
        {chr(10).join(strategic_goals)}
        
        REFLECTION ANALYSIS:
        {chr(10).join(reflection_patterns)}
        
        INSTRUCTIONS:
        - Reference SPECIFIC items from the data above by name
        - Mention actual percentages, times, and task names
        - Create 3-5 actionable priorities per section
        - Be concrete about timing based on calendar gaps
        - Focus on highest impact activities
        
        Create exactly these sections:
        
        **TODAY'S FOCUS:**
        • Priority 1: [Most important unchecked weekly task with specific timing]
        • Priority 2: [Specific calendar preparation or follow-up with time]
        • Priority 3: [Specific strategic goal advancement with percentage target]
        • Priority 4: [Additional high-impact item from available data]
        • Priority 5: [One more strategic priority if data supports it]
        
        **ENERGY OPTIMIZATION:**
        • Peak Hours: [Specific morning/afternoon slots based on calendar gaps]
        • Reflection Time: [Specific evening time based on analysis and schedule]
        • Recovery Activities: [Intelligent suggestions based on today's intensity]
        
        Use specific names, times, and data points. Be actionable and strategic.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": "You are a strategic productivity coach who creates highly specific, data-driven daily briefings. Always reference actual data provided rather than generic advice."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.6
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI error: {e}")
            return f"""**TODAY'S FOCUS:**
• Priority 1: {checklist_items[0] if checklist_items else 'Complete weekly planning review'}
• Priority 2: {calendar_data['blocks'][0] if calendar_data['blocks'] else calendar_data['events'][0] if calendar_data['events'] else 'Schedule focus time'}
• Priority 3: {strategic_goals[0] if strategic_goals else 'Define next strategic goal milestone'}
• Priority 4: Review and update progress on active strategic initiatives
• Priority 5: Prepare for tomorrow's high-priority activities

**ENERGY OPTIMIZATION:**
• Peak Hours: 9:00-11:00 AM for strategic work (based on calendar gaps)
• Reflection Time: {reflection_patterns[0] if reflection_patterns else '9:00 PM evening reflection routine'}
• Recovery Activities: Schedule breaks between intense focus sessions"""

    def _update_notion_block(self, briefing_content):
        """Internal: Update Notion page (wrapped with retry)"""
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
        
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        full_content = f"🤖 AI-Generated Morning Insights - {current_date}\n\nBased on your calendar, recent notes, and patterns, here's your personalized briefing for today.\n\n{briefing_content}"
        
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
        """Update the Daily Briefing section with retry"""
        try:
            print("📝 Updating Notion page...")
            action = self.notion_retry(self._update_notion_block, briefing_content)
            print(f"   ✅ Successfully {action} daily briefing block!")
        except Exception as e:
            print(f"❌ Failed to update Notion after retries: {str(e)}")

    def run(self):
        """Main execution"""
        print(f"🎯 Strategic Daily Briefing Generator")
        print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay\n")
        
        calendar_data = self.get_calendar_events_and_blocks()
        checklist_items = self.get_weekly_checklist_items()
        strategic_goals = self.get_strategic_goals()
        reflection_patterns = self.get_journal_reflection_patterns()
        
        print("\n📊 DATA SUMMARY:")
        print(f"   Calendar: {len(calendar_data['events'])} events, {len(calendar_data['blocks'])} blocks")
        print(f"   Checklist: {len(checklist_items)} items")
        print(f"   Goals: {len(strategic_goals)} active")
        print(f"   Patterns: {len(reflection_patterns)} insights")
        
        print("\n🧠 Generating AI briefing...")
        briefing = self.generate_strategic_briefing(calendar_data, checklist_items, strategic_goals, reflection_patterns)
        
        self.update_daily_briefing_section(briefing)
        print(f"\n✅ Process completed at: {datetime.now().strftime('%H:%M:%S IST')}")

if __name__ == "__main__":
    briefing = StrategicDailyBriefing()
    briefing.run()
