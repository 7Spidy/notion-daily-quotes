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
        
        self.weekly_checklist_db_id = os.getenv('WEEKLY_CHECKLIST_DB_ID')
        self.strategic_goals_db_id = os.getenv('STRATEGIC_GOALS_DB_ID')
        self.daily_journal_db_id = os.getenv('DAILY_JOURNAL_DB_ID')
        
        self.sleep_start = "22:00"
        self.sleep_end = "06:30"
        self.max_retries = 3
        self.retry_delay = 3
        
        try:
            credentials_json = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.google_credentials = credentials_json
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        except Exception as e:
            self.google_credentials = None

    def get_current_ist_time(self):
        """Get IST time"""
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).strftime("%A, %B %d, %Y - %I:%M %p IST")

    def notion_retry(self, func, *args, **kwargs):
        """Retry wrapper"""
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    print(f"   Attempt {attempt}/{self.max_retries}...")
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)
                else:
                    raise e

    def get_google_access_token(self):
        """Get Google token"""
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
            data = {'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': token}
            return requests.post('https://oauth2.googleapis.com/token', data=data).json().get('access_token')
        except:
            return None

    def get_calendar_events_today(self):
        """Get calendar events"""
        try:
            token = self.get_google_access_token()
            if not token:
                return ["Calendar unavailable"]
            
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            start = now.replace(hour=0, minute=0, second=0).isoformat()
            end = now.replace(hour=23, minute=59, second=59).isoformat()
            
            response = requests.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{self.calendar_id}/events",
                headers={'Authorization': f'Bearer {token}'},
                params={'timeMin': start, 'timeMax': end, 'singleEvents': True, 'orderBy': 'startTime'}
            )
            
            events = []
            for event in response.json().get('items', []):
                summary = event.get('summary', 'No title')
                start_time = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', ''))
                time_str = start_time.split('T')[1][:5] if 'T' in start_time else 'All day'
                events.append(f"{time_str}: {summary}")
            
            return events if events else ["No events"]
        except:
            return ["Calendar unavailable"]

    def get_weekly_checklist_items(self):
        """Get checklist"""
        try:
            print("📋 Getting checklist...")
            response = requests.post(
                f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query",
                headers={"Authorization": f"Bearer {self.notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"},
                json={"filter": {"property": "Done?", "checkbox": {"equals": False}}, "page_size": 10},
                timeout=10
            )
            
            items = []
            for item in response.json().get('results', []):
                if 'Task' in item['properties'] and item['properties']['Task']['title']:
                    items.append(item['properties']['Task']['title'][0]['plain_text'])
            
            print(f"   Found {len(items)} items")
            return items if items else ["All completed"]
        except:
            return ["Weekly review"]

    def get_strategic_goals(self):
        """Get goals"""
        try:
            print("🎯 Getting goals...")
            response = requests.post(
                f"https://api.notion.com/v1/databases/{self.strategic_goals_db_id}/query",
                headers={"Authorization": f"Bearer {self.notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"},
                json={"filter": {"property": "Status", "status": {"equals": "In progress"}}, "page_size": 5},
                timeout=10
            )
            
            goals = []
            for goal in response.json().get('results', []):
                name = 'Untitled'
                progress = 0
                if 'Name' in goal['properties'] and goal['properties']['Name']['title']:
                    name = goal['properties']['Name']['title'][0]['plain_text']
                if 'Progress' in goal['properties'] and goal['properties']['Progress']['number']:
                    progress = int(goal['properties']['Progress']['number'])
                goals.append(f"{name} ({progress}%)")
            
            print(f"   Found {len(goals)} goals")
            return goals if goals else ["Define goals"]
        except:
            return ["Strategic planning"]

    def get_recent_journal_entries(self):
        """Get journal entries"""
        try:
            print("📝 Getting journals...")
            response = requests.post(
                f"https://api.notion.com/v1/databases/{self.daily_journal_db_id}/query",
                headers={"Authorization": f"Bearer {self.notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"},
                json={"sorts": [{"property": "Created time", "direction": "descending"}], "page_size": 2},
                timeout=10
            )
            
            entries = []
            for entry in response.json().get('results', []):
                title = 'Journal'
                if 'Name' in entry['properties'] and entry['properties']['Name']['title']:
                    title = entry['properties']['Name']['title'][0]['plain_text']
                
                # Get page content
                blocks_response = requests.get(
                    f"https://api.notion.com/v1/blocks/{entry['id']}/children",
                    headers={"Authorization": f"Bearer {self.notion_token}", "Notion-Version": "2022-06-28"},
                    timeout=15
                )
                
                content_parts = []
                for block in blocks_response.json().get('results', []):
                    if block['type'] == 'paragraph' and block['paragraph']['rich_text']:
                        text = ''.join([t.get('plain_text', '') for t in block['paragraph']['rich_text']])
                        if text.strip():
                            content_parts.append(text)
                
                content = '\n'.join(content_parts)[:300] if content_parts else "No content"
                
                date = 'Recent'
                if 'Created time' in entry['properties']:
                    date = entry['properties']['Created time']['created_time'][:10]
                
                entries.append({'title': title, 'content': content, 'date': date})
            
            print(f"   Found {len(entries)} entries")
            return entries if entries else [{'title': 'Start journaling', 'content': 'Begin reflections', 'date': 'Today'}]
        except:
            return [{'title': 'Daily reflection', 'content': 'Continue journaling', 'date': 'Today'}]

    def generate_strategic_briefing(self, checklist, goals, journals, calendar):
        """Generate briefing with GPT-5.1 Responses API"""
        journal_summaries = [f"Entry {i}: '{e['title']}' ({e['date']}) Content: {e['content'][:250]}" 
                            for i, e in enumerate(journals[:2], 1)]
        journal_text = ' | '.join(journal_summaries)
        
        prompt = f"Create exactly 5 concise numbered insights (2-3 sentences each). No intro. SLEEP: Never suggest 10PM-6:30AM activities. DATA - WEEKLY: {'; '.join(checklist[:2])}. GOALS: {'; '.join(goals[:2])}. JOURNAL: {journal_text}. CALENDAR: {'; '.join(calendar[:3])}. Format: 1.[weekly task 7AM-9PM] 2.[goal progress daytime] 3.[Journal analysis using 'you' language - never 'author'. Analyze emotions/patterns. 2-3 sentences max] 4.[calendar prep 6:30AM-9:30PM] 5.[evening reward 7PM-9:30PM]. Each point under 60 words."
        
        try:
            # Use Responses API for GPT-5.1
            response = self.openai_client.responses.create(
                model="gpt-5.1",
                input=f"You are a personal coach. CRITICAL: Use 'you/your' - NEVER 'author/writer'. For point 3: analyze journal content for themes/emotions. Keep all insights CONCISE (2-3 sentences max). No activities 10PM-6:30AM. Start with '1.'\n\n{prompt}",
                reasoning={"effort": "low"},  # Balanced reasoning for insights
                text={"verbosity": "medium"},  # Moderate detail
                max_output_tokens=350
            )
            
            insights = response.output_text.strip()
            
            # Clean author references
            insights = insights.replace("the author", "you").replace("Author", "You").replace("author", "you")
            insights = insights.replace("writer", "you").replace("the writer", "you").replace("Writer", "You")
            
            return insights
            
        except Exception as e:
            print(f"GPT-5.1 error: {e}")
            return "1. Complete priority weekly task during morning hours (8:00-11:00 AM) - consistency builds momentum.\n2. Advance strategic initiatives during afternoon sessions (2:00-5:00 PM) - progress compounds.\n3. Your recent journal entries show thoughtful self-reflection - continue this practice for growth.\n4. Approach today's activities with intentional preparation.\n5. Schedule relaxation between 8:00-9:30 PM before sleep."

    def _update_notion_block(self, briefing):
        """Update Notion"""
        import re
        briefing = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', briefing)
        briefing = briefing.encode('utf-8', errors='ignore').decode('utf-8')
        
        if len(briefing) > 1950:
            briefing = briefing[:1950] + "..."
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        response = requests.get(f"https://api.notion.com/v1/blocks/{self.page_id}/children", 
                               headers=headers, timeout=10)
        
        block_id = None
        for block in response.json().get('results', []):
            if (block['type'] == 'callout' and block.get('callout', {}).get('rich_text') and
                'AI-Generated Morning Insights' in block['callout']['rich_text'][0].get('plain_text', '')):
                block_id = block['id']
                break
        
        full_content = f"🤖 AI-Generated Morning Insights - {self.get_current_ist_time()}\n\nBased on your calendar, recent notes, and patterns, here's your personalized briefing for today.\n\n**TODAY'S FOCUS:**\n{briefing}"
        
        new_block = {
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": full_content}}],
                "icon": {"emoji": "🤖"},
                "color": "blue_background"
            }
        }
        
        if block_id:
            response = requests.patch(f"https://api.notion.com/v1/blocks/{block_id}", 
                                     headers=headers, json=new_block, timeout=15)
            return "updated" if response.status_code == 200 else None
        else:
            response = requests.patch(f"https://api.notion.com/v1/blocks/{self.page_id}/children",
                                     headers=headers, json={"children": [new_block]}, timeout=15)
            return "created" if response.status_code == 200 else None

    def run(self):
        """Main execution"""
        print(f"🎯 GPT-5.1 Powered Strategic Briefing (Responses API)")
        print(f"🕐 Started: {self.get_current_ist_time()}")
        print(f"🤖 AI Model: GPT-5.1 (Latest OpenAI Model)")
        print(f"⚡ Reasoning: low (balanced mode)")
        print(f"📊 Verbosity: medium (moderate detail)")
        print(f"😴 Sleep: {self.sleep_start} - {self.sleep_end}\n")
        
        calendar = self.get_calendar_events_today()
        checklist = self.get_weekly_checklist_items()
        goals = self.get_strategic_goals()
        journals = self.get_recent_journal_entries()
        
        print("\n🧠 Generating GPT-5.1 insights...")
        briefing = self.generate_strategic_briefing(checklist, goals, journals, calendar)
        
        print("📝 Updating Notion...")
        action = self.notion_retry(self._update_notion_block, briefing)
        print(f"   ✅ Successfully {action} briefing!")
        
        print(f"\n✅ Completed: {self.get_current_ist_time()}")

if __name__ == "__main__":
    briefing = StrategicDailyBriefing()
    briefing.run()
