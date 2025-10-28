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
        
        # Strategic databases (now with correct IDs)
        self.weekly_checklist_db_id = os.getenv('WEEKLY_CHECKLIST_DB_ID')
        self.strategic_goals_db_id = os.getenv('STRATEGIC_GOALS_DB_ID')
        self.daily_journal_db_id = os.getenv('DAILY_JOURNAL_DB_ID')
        
        # Google Calendar setup
        try:
            credentials_json = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.google_credentials = credentials_json
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        except Exception as e:
            print(f"Google setup error: {e}")
            self.google_credentials = None

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
                
                # Identify important time blocks
                if any(keyword in summary.lower() for keyword in ['office', 'work', 'meeting', 'focus', 'block', 'forex']):
                    time_blocks.append(f"• {time_display}: {summary}")
            
            return {
                "events": formatted_events if formatted_events else ["• No scheduled events today"],
                "blocks": time_blocks if time_blocks else ["• No special focus blocks scheduled"]
            }
            
        except Exception as e:
            print(f"Calendar error: {e}")
            return {"events": ["• Calendar temporarily unavailable"], "blocks": []}

    def get_weekly_checklist_items(self):
        """Get unchecked items from Weekly Checklist database"""
        try:
            print("✅ Getting Weekly Checklist items...")
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Query for unchecked items (Checkbox = false)
            query_url = f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query"
            query_data = {
                "filter": {
                    "property": "Checkbox",
                    "checkbox": {
                        "equals": False
                    }
                },
                "page_size": 5
            }
            
            response = requests.post(query_url, headers=headers, json=query_data)
            
            if response.status_code != 200:
                print(f"❌ Weekly checklist query failed: {response.status_code} - {response.text}")
                return ["• Error querying weekly checklist"]
                
            data = response.json()
            results = data.get('results', [])
            print(f"📊 Found {len(results)} unchecked weekly checklist items")
            
            checklist_items = []
            for item in results:
                try:
                    # Get name/title
                    name = 'Untitled task'
                    if 'Name' in item['properties'] and item['properties']['Name']['title']:
                        name = item['properties']['Name']['title'][0]['plain_text']
                    
                    checklist_items.append(f"• {name}")
                    
                except Exception as item_error:
                    print(f"⚠️ Error processing checklist item: {item_error}")
                    checklist_items.append("• Weekly task (details unavailable)")
            
            return checklist_items if checklist_items else ["• All weekly checklist items completed! ✅"]
            
        except Exception as e:
            print(f"❌ Weekly checklist error: {e}")
            return [f"• Error accessing Weekly Checklist: {str(e)}"]

    def get_strategic_goals(self):
        """Get active strategic goals (In progress status)"""
        try:
            print("🎯 Getting Strategic Goals...")
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Query for goals with "In progress" status
            query_url = f"https://api.notion.com/v1/databases/{self.strategic_goals_db_id}/query"
            query_data = {
                "filter": {
                    "property": "Status",
                    "status": {
                        "equals": "In progress"
                    }
                },
                "page_size": 5
            }
            
            response = requests.post(query_url, headers=headers, json=query_data)
            
            if response.status_code != 200:
                print(f"❌ Strategic goals query failed: {response.status_code} - {response.text}")
                return ["• Error querying strategic goals"]
                
            data = response.json()
            results = data.get('results', [])
            print(f"📊 Found {len(results)} strategic goals in progress")
            
            strategic_goals = []
            for goal in results:
                try:
                    # Get name
                    name = 'Untitled Goal'
                    if 'Name' in goal['properties'] and goal['properties']['Name']['title']:
                        name = goal['properties']['Name']['title'][0]['plain_text']
                    
                    # Get progress
                    progress = 0
                    if 'Progress' in goal['properties'] and goal['properties']['Progress']['number'] is not None:
                        progress = goal['properties']['Progress']['number']
                    
                    # Get type  
                    goal_type = 'Goal'
                    if 'Type' in goal['properties'] and goal['properties']['Type']['select']:
                        goal_type = goal['properties']['Type']['select']['name']
                    
                    # Get due date
                    due_info = ''
                    if 'Due Date' in goal['properties'] and goal['properties']['Due Date']['date']:
                        due_date = goal['properties']['Due Date']['date']['start']
                        try:
                            due_datetime = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                            due_info = f" - Due: {due_datetime.strftime('%m/%d')}"
                        except:
                            due_info = f" - Due: {due_date}"
                    
                    progress_percent = int(progress) if progress else 0
                    strategic_goals.append(f"• [{goal_type}] {name} ({progress_percent}% complete){due_info}")
                    
                except Exception as goal_error:
                    print(f"⚠️ Error processing strategic goal: {goal_error}")
                    strategic_goals.append("• Strategic goal (details unavailable)")
            
            return strategic_goals if strategic_goals else ["• No strategic goals currently in progress"]
            
        except Exception as e:
            print(f"❌ Strategic goals error: {e}")
            return [f"• Error accessing Strategic Goals: {str(e)}"]

    def get_journal_reflection_patterns(self):
        """Get recent journal entries and suggest reflection patterns"""
        try:
            print("📝 Analyzing Daily Journal patterns...")
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Get recent journal entries (last 7 days)
            query_url = f"https://api.notion.com/v1/databases/{self.daily_journal_db_id}/query"
            query_data = {
                "sorts": [
                    {
                        "property": "Created time",
                        "direction": "descending"
                    }
                ],
                "page_size": 7
            }
            
            response = requests.post(query_url, headers=headers, json=query_data)
            
            if response.status_code != 200:
                print(f"❌ Journal query failed: {response.status_code}")
                return ["• Journal analysis temporarily unavailable"]
                
            data = response.json()
            results = data.get('results', [])
            print(f"📊 Found {len(results)} recent journal entries")
            
            # Analyze patterns
            reflection_insights = []
            
            if len(results) >= 5:
                # Regular journaler
                reflection_insights = [
                    "• Continue your excellent daily journaling routine around 9:00-9:30 PM",
                    "• Focus tonight on reviewing today's strategic goal progress",
                    "• Consider deep reflection on weekly checklist completion patterns"
                ]
            elif len(results) >= 2:
                # Occasional journaler
                reflection_insights = [
                    "• Establish more consistent evening reflection routine (9:00 PM ideal)",
                    "• Tonight: reflect on strategic goal alignment with daily actions",
                    "• Use 15-minute focused reflection sessions for better insights"
                ]
            else:
                # Infrequent journaler
                reflection_insights = [
                    "• Start simple: 10-minute evening reflection at 9:00 PM",
                    "• Focus on: What went well today? What could be improved?",
                    "• Use journal to track progress on strategic goals and weekly tasks"
                ]
            
            return reflection_insights
            
        except Exception as e:
            print(f"❌ Journal analysis error: {e}")
            return ["• Evening reflection recommended based on typical productivity patterns"]

    def generate_strategic_briefing(self, calendar_data, checklist_items, strategic_goals, reflection_patterns):
        """Generate AI-powered strategic daily briefing with real data"""
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
                model="gpt-5-nano",
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
            # Smart fallback with actual data
            fallback = f"""**TODAY'S FOCUS:**
• Priority 1: {checklist_items[0] if checklist_items else 'Complete weekly planning review'}
• Priority 2: {calendar_data['blocks'][0] if calendar_data['blocks'] else calendar_data['events'][0] if calendar_data['events'] else 'Schedule focus time'}
• Priority 3: {strategic_goals[0] if strategic_goals else 'Define next strategic goal milestone'}
• Priority 4: Review and update progress on active strategic initiatives
• Priority 5: Prepare for tomorrow's high-priority activities

**ENERGY OPTIMIZATION:**
• Peak Hours: 9:00-11:00 AM for strategic work (based on calendar gaps)
• Reflection Time: {reflection_patterns[0] if reflection_patterns else '9:00 PM evening reflection routine'}
• Recovery Activities: Schedule breaks between intense focus sessions"""
            return fallback

    def update_daily_briefing_section(self, briefing_content):
        """Update the Daily Briefing section in Notion"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        try:
            blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            response = requests.get(blocks_url, headers=headers)
            
            if response.status_code != 200:
                print(f"❌ Error getting blocks: {response.status_code}")
                return
                
            blocks = response.json()
            
            # Find the Daily Briefing callout block
            briefing_block_id = None
            for block in blocks.get('results', []):
                if (block['type'] == 'callout' and 
                    block.get('callout', {}).get('rich_text') and
                    len(block['callout']['rich_text']) > 0 and
                    'AI-Generated Morning Insights' in block['callout']['rich_text'][0].get('plain_text', '')):
                    briefing_block_id = block['id']
                    break
            
            # Prepare the content
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
                    print("✅ Updated strategic daily briefing successfully!")
                else:
                    print(f"❌ Error updating briefing: {response.status_code}")
            else:
                # Create new block
                create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
                payload = {"children": [new_block_data]}
                response = requests.patch(create_url, headers=headers, json=payload)
                if response.status_code == 200:
                    print("✅ Created new strategic daily briefing successfully!")
                else:
                    print(f"❌ Error creating briefing: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error updating briefing: {str(e)}")

    def run(self):
        """Main execution with strategic focus and detailed logging"""
        print(f"🎯 Generating strategic daily briefing for {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"📍 Database IDs configured:")
        print(f"   Weekly Checklist: {self.weekly_checklist_db_id}")
        print(f"   Strategic Goals: {self.strategic_goals_db_id}")
        print(f"   Daily Journal: {self.daily_journal_db_id}")
        
        # Gather strategic data with detailed logging
        print("\n📅 Getting calendar events and time blocks...")
        calendar_data = self.get_calendar_events_and_blocks()
        print(f"   Events: {len(calendar_data['events'])}, Focus Blocks: {len(calendar_data['blocks'])}")
        
        print("\n📋 Getting weekly checklist items...")
        checklist_items = self.get_weekly_checklist_items()
        print(f"   Unchecked items: {len(checklist_items)}")
        
        print("\n🎯 Getting strategic goals...")
        strategic_goals = self.get_strategic_goals()
        print(f"   Active goals: {len(strategic_goals)}")
        
        print("\n📝 Analyzing reflection patterns...")
        reflection_patterns = self.get_journal_reflection_patterns()
        print(f"   Reflection insights: {len(reflection_patterns)}")
        
        # Show data summary for verification
        print("\n📊 STRATEGIC DATA SUMMARY:")
        print("Calendar Events:", calendar_data['events'][:2])
        print("Focus Blocks:", calendar_data['blocks'])
        print("Weekly Checklist:", checklist_items[:2])  
        print("Strategic Goals:", strategic_goals[:2])
        print("Reflection Insights:", reflection_patterns[:1])
        
        # Generate strategic briefing
        print("\n🧠 Generating strategic AI briefing...")
        briefing = self.generate_strategic_briefing(calendar_data, checklist_items, strategic_goals, reflection_patterns)
        print(f"   Generated briefing ({len(briefing)} characters)")
        
        # Update Notion
        print("\n📝 Updating Notion page...")
        self.update_daily_briefing_section(briefing)
        print("✅ Strategic daily briefing process completed!")

if __name__ == "__main__":
    briefing = StrategicDailyBriefing()
    briefing.run()
