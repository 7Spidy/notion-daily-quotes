import openai
import requests
import json
import os
from datetime import datetime, timedelta
import base64

class DailyBriefingGenerator:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        self.capture_db_id = os.getenv('CAPTURE_DATABASE_ID')
        self.goals_db_id = os.getenv('GOALS_DATABASE_ID')
        
        # Setup Google Calendar with simpler approach
        try:
            credentials_json = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.google_credentials = credentials_json
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        except Exception as e:
            print(f"Google Calendar setup error: {e}")
            self.google_credentials = None

    def get_google_calendar_token(self):
        """Get access token for Google Calendar API"""
        try:
            import jwt
            import time
            
            # Create JWT
            now = int(time.time())
            payload = {
                'iss': self.google_credentials['client_email'],
                'scope': 'https://www.googleapis.com/auth/calendar.readonly',
                'aud': 'https://oauth2.googleapis.com/token',
                'exp': now + 3600,
                'iat': now
            }
            
            # Sign with private key
            private_key = self.google_credentials['private_key']
            token = jwt.encode(payload, private_key, algorithm='RS256')
            
            # Exchange for access token
            data = {
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'assertion': token
            }
            
            response = requests.post('https://oauth2.googleapis.com/token', data=data)
            return response.json().get('access_token')
            
        except Exception as e:
            print(f"Token generation error: {e}")
            return None

    def get_today_calendar_events(self):
        """Get today's calendar events using direct API calls"""
        try:
            access_token = self.get_google_calendar_token()
            if not access_token:
                return ["• Calendar access unavailable"]
                
            headers = {'Authorization': f'Bearer {access_token}'}
            
            # Get today's events
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
            events_data = response.json()
            
            formatted_events = []
            for event in events_data.get('items', []):
                start = event.get('start', {})
                start_time = start.get('dateTime', start.get('date', ''))
                summary = event.get('summary', 'No title')
                
                if 'T' in start_time:
                    time_str = start_time.split('T')[1][:5]
                else:
                    time_str = 'All day'
                    
                formatted_events.append(f"• {time_str}: {summary}")
            
            return formatted_events if formatted_events else ["• No scheduled events today"]
            
        except Exception as e:
            print(f"Calendar error: {e}")
            return ["• Calendar events will be shown here"]

    def get_unprocessed_captures(self):
        """Get unprocessed items from Quick Capture database"""
        try:
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            query_url = f"https://api.notion.com/v1/databases/{self.capture_db_id}/query"
            query_data = {
                "filter": {
                    "property": "Processing_Status",
                    "select": {
                        "equals": "📥 Captured"
                    }
                },
                "page_size": 5
            }
            
            response = requests.post(query_url, headers=headers, json=query_data)
            
            if response.status_code != 200:
                print(f"Capture query error: {response.status_code} - {response.text}")
                return ["• Error accessing captures"]
                
            data = response.json()
            
            captures = []
            for item in data.get('results', [])[:5]:  # Limit to 5 items
                try:
                    title_prop = item['properties'].get('Title', {})
                    title = 'Untitled'
                    if title_prop.get('title') and len(title_prop['title']) > 0:
                        title = title_prop['title'][0]['plain_text']
                    
                    type_prop = item['properties'].get('Type', {})
                    item_type = 'Unknown'
                    if type_prop.get('select'):
                        item_type = type_prop['select']['name']
                    
                    captures.append(f"• {item_type}: {title}")
                except Exception as item_error:
                    print(f"Error processing capture item: {item_error}")
                    continue
            
            return captures if captures else ["• No unprocessed captures"]
            
        except Exception as e:
            print(f"Captures error: {e}")
            return ["• Error accessing captures"]

    def get_active_goals(self):
        """Get active goals and their progress"""
        try:
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            query_url = f"https://api.notion.com/v1/databases/{self.goals_db_id}/query"
            query_data = {
                "filter": {
                    "property": "Status",
                    "select": {
                        "equals": "🔄 In Progress"
                    }
                },
                "page_size": 3
            }
            
            response = requests.post(query_url, headers=headers, json=query_data)
            
            if response.status_code != 200:
                print(f"Goals query error: {response.status_code} - {response.text}")
                return ["• Error accessing goals"]
                
            data = response.json()
            
            goals = []
            for goal in data.get('results', [])[:3]:  # Limit to 3 goals
                try:
                    title_prop = goal['properties'].get('Goal', {})
                    title = 'Untitled Goal'
                    if title_prop.get('title') and len(title_prop['title']) > 0:
                        title = title_prop['title'][0]['plain_text']
                    
                    progress_prop = goal['properties'].get('Progress', {})
                    progress = 0
                    if progress_prop.get('number') is not None:
                        progress = progress_prop['number']
                    
                    level_prop = goal['properties'].get('Level', {})
                    level = 'Goal'
                    if level_prop.get('select'):
                        level = level_prop['select']['name']
                    
                    progress_percent = int(progress * 100) if progress else 0
                    goals.append(f"• {level}: {title} ({progress_percent}% complete)")
                    
                except Exception as goal_error:
                    print(f"Error processing goal: {goal_error}")
                    continue
            
            return goals if goals else ["• No active goals found"]
            
        except Exception as e:
            print(f"Goals error: {e}")
            return ["• Error accessing goals"]

    def generate_daily_briefing(self, calendar_events, captures, goals):
        """Generate AI-powered daily briefing"""
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        
        prompt = f"""
        Generate a personalized daily briefing for {current_date}. 
        
        CALENDAR EVENTS TODAY:
        {chr(10).join(calendar_events)}
        
        UNPROCESSED CAPTURES:
        {chr(10).join(captures)}
        
        ACTIVE GOALS:
        {chr(10).join(goals)}
        
        Based on this data, create a briefing with exactly these sections:
        
        TODAY'S FOCUS:
        • Priority 1: [Most urgent from calendar/deadlines]
        • Priority 2: [Important goal-aligned task]  
        • Priority 3: [Learning opportunity from captures]
        
        KNOWLEDGE OPPORTUNITIES:
        • To Process: [Mention 1-2 specific captures to review]
        • To Connect: [Suggest connecting captures to goals]
        • To Distill: [Recommend insight extraction from specific items]
        
        ENERGY OPTIMIZATION:
        • Peak Hours: [Best work times based on calendar gaps]
        • Reflection Time: [When to journal based on schedule]
        • Recovery Activities: [Break times and activities]
        
        Keep each bullet point to one line. Be specific and actionable.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",  # Using cheaper model for daily automation
                messages=[
                    {"role": "system", "content": "You are a personal productivity coach who creates concise, actionable daily briefings."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            return f"Daily briefing generation temporarily unavailable. Focus on your calendar events and process your captures today!"

    def update_daily_briefing_section(self, briefing_content):
        """Update the Daily Briefing section in Notion"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        try:
            # Get page blocks
            blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            response = requests.get(blocks_url, headers=headers)
            
            if response.status_code != 200:
                print(f"Error getting blocks: {response.status_code}")
                return
                
            blocks = response.json()
            
            # Find Daily Briefing section (look for callout with AI-Generated Morning Insights)
            briefing_block_id = None
            for block in blocks.get('results', []):
                if (block['type'] == 'callout' and 
                    block.get('callout', {}).get('rich_text') and
                    len(block['callout']['rich_text']) > 0 and
                    'AI-Generated Morning Insights' in block['callout']['rich_text'][0].get('plain_text', '')):
                    briefing_block_id = block['id']
                    break
            
            # Prepare content
            current_date = datetime.now().strftime("%A, %B %d, %Y")
            full_content = f"🤖 AI-Generated Morning Insights - {current_date}\n\nBased on your calendar, recent notes, and patterns, here's your personalized briefing for today.\n\n{briefing_content}"
            
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
                        "emoji": "🤖"
                    },
                    "color": "blue_background"
                }
            }
            
            if briefing_block_id:
                # Update existing block
                update_url = f"https://api.notion.com/v1/blocks/{briefing_block_id}"
                response = requests.patch(update_url, headers=headers, json=new_block_data)
                if response.status_code == 200:
                    print("✅ Updated existing daily briefing block")
                else:
                    print(f"❌ Error updating block: {response.status_code}")
            else:
                print("🔍 No existing briefing block found, creating new one...")
                # Create new block at the beginning
                create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
                payload = {"children": [new_block_data]}
                response = requests.patch(create_url, headers=headers, json=payload)
                if response.status_code == 200:
                    print("✅ Created new daily briefing block")
                else:
                    print(f"❌ Error creating block: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error updating daily briefing: {str(e)}")

    def run(self):
        """Main execution function"""
        print(f"🌅 Generating daily briefing for {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Gather data
        print("📅 Getting calendar events...")
        calendar_events = self.get_today_calendar_events()
        print(f"   Found {len(calendar_events)} calendar events")
        
        print("📥 Getting unprocessed captures...")
        captures = self.get_unprocessed_captures()
        print(f"   Found {len(captures)} unprocessed captures")
        
        print("🎯 Getting active goals...")
        goals = self.get_active_goals()
        print(f"   Found {len(goals)} active goals")
        
        # Generate briefing
        print("🤖 Generating AI briefing...")
        briefing = self.generate_daily_briefing(calendar_events, captures, goals)
        print(f"   Generated briefing ({len(briefing)} characters)")
        
        # Update Notion
        print("📝 Updating Notion page...")
        self.update_daily_briefing_section(briefing)
        print("✅ Daily briefing process completed!")

if __name__ == "__main__":
    generator = DailyBriefingGenerator()
    generator.run()
