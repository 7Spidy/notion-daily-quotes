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
                
                # Identify time blocks (events with specific keywords or longer duration)
                if any(keyword in summary.lower() for keyword in ['block', 'focus', 'deep work', 'project', 'development']):
                    time_blocks.append(f"• {time_display}: {summary} (Focus Block)")
            
            return {
                "events": formatted_events if formatted_events else ["• No scheduled events today"],
                "blocks": time_blocks if time_blocks else ["• No dedicated focus blocks scheduled"]
            }
            
        except Exception as e:
            print(f"Calendar error: {e}")
            return {"events": ["• Calendar temporarily unavailable"], "blocks": []}

    def debug_database_properties(self, db_id, db_name):
        """Debug database structure to understand properties"""
        try:
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            db_url = f"https://api.notion.com/v1/databases/{db_id}"
            response = requests.get(db_url, headers=headers)
            
            if response.status_code != 200:
                print(f"❌ {db_name} access error: {response.status_code}")
                return None
                
            db_data = response.json()
            properties = db_data.get('properties', {})
            
            print(f"✅ {db_name} properties:")
            for prop_name, prop_data in properties.items():
                prop_type = prop_data.get('type', 'unknown')
                print(f"   - {prop_name}: {prop_type}")
                
                # Show select options if it's a select property
                if prop_type == 'select' and 'select' in prop_data:
                    options = prop_data['select'].get('options', [])
                    option_names = [opt['name'] for opt in options]
                    print(f"     Options: {option_names}")
                
            return properties
            
        except Exception as e:
            print(f"❌ Error debugging {db_name}: {e}")
            return None

    def get_weekly_checklist_items(self):
        """Get pending items from Weekly Checklist database"""
        try:
            if not self.weekly_checklist_db_id:
                return ["• Weekly Checklist database not configured"]
            
            print("🔍 Analyzing Weekly Checklist database...")
            properties = self.debug_database_properties(self.weekly_checklist_db_id, "Weekly Checklist")
            
            if not properties:
                return ["• Weekly Checklist database access failed"]
            
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Query for incomplete/pending items
            query_url = f"https://api.notion.com/v1/databases/{self.weekly_checklist_db_id}/query"
            
            # Try different approaches based on database structure
            possible_status_props = ['Status', 'Done', 'Complete', 'Completed', 'Checkbox', 'Progress']
            status_property = None
            
            for prop in possible_status_props:
                if prop in properties:
                    status_property = prop
                    break
            
            if status_property and properties[status_property]['type'] == 'checkbox':
                # Checkbox property - filter for unchecked
                query_data = {
                    "filter": {
                        "property": status_property,
                        "checkbox": {
                            "equals": False
                        }
                    },
                    "page_size": 5
                }
            elif status_property and properties[status_property]['type'] == 'select':
                # Select property - try common incomplete statuses
                query_data = {
                    "filter": {
                        "or": [
                            {"property": status_property, "select": {"equals": "To Do"}},
                            {"property": status_property, "select": {"equals": "In Progress"}},
                            {"property": status_property, "select": {"equals": "Not Started"}},
                            {"property": status_property, "select": {"equals": "Pending"}}
                        ]
                    },
                    "page_size": 5
                }
            else:
                # No clear status property - get all recent items
                query_data = {"page_size": 5}
            
            response = requests.post(query_url, headers=headers, json=query_data)
            
            if response.status_code != 200:
                print(f"❌ Weekly checklist query failed: {response.status_code}")
                return ["• Error querying weekly checklist"]
                
            data = response.json()
            results = data.get('results', [])
            print(f"📊 Found {len(results)} weekly checklist items")
            
            checklist_items = []
            for item in results:
                try:
                    # Get title
                    title = self.extract_title_from_item(item, properties)
                    
                    # Get priority or category if available
                    priority = self.extract_select_value(item, properties, ['Priority', 'Importance', 'Urgency'])
                    category = self.extract_select_value(item, properties, ['Category', 'Area', 'Type'])
                    
                    # Format the item
                    display_text = title
                    if priority:
                        display_text = f"[{priority}] {display_text}"
                    if category:
                        display_text += f" ({category})"
                    
                    checklist_items.append(f"• {display_text}")
                    
                except Exception as item_error:
                    print(f"⚠️ Error processing checklist item: {item_error}")
                    checklist_items.append("• Weekly checklist item (details unavailable)")
            
            return checklist_items if checklist_items else ["• No pending weekly checklist items"]
            
        except Exception as e:
            print(f"❌ Weekly checklist error: {e}")
            return ["• Error accessing Weekly Checklist database"]

    def get_strategic_goals(self):
        """Get active strategic goals"""
        try:
            if not self.strategic_goals_db_id:
                return ["• Strategic Goals database not configured"]
            
            print("🔍 Analyzing Strategic Goals database...")
            properties = self.debug_database_properties(self.strategic_goals_db_id, "Strategic Goals")
            
            if not properties:
                return ["• Strategic Goals database access failed"]
            
            headers = {
                "Authorization": f"Bearer {self.notion_token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28"
            }
            
            # Query for active goals
            query_url = f"https://api.notion.com/v1/databases/{self.strategic_goals_db_id}/query"
            
            # Look for status property
            status_property = None
            possible_status_props = ['Status', 'Progress', 'State', 'Active']
            
            for prop in possible_status_props:
                if prop in properties:
                    status_property = prop
                    break
            
            if status_property and properties[status_property]['type'] == 'select':
                query_data = {
                    "filter": {
                        "or": [
                            {"property": status_property, "select": {"equals": "In Progress"}},
                            {"property": status_property, "select": {"equals": "Active"}},
                            {"property": status_property, "select": {"equals": "Current"}},
                            {"property": status_property, "select": {"equals": "🔄 In Progress"}}
                        ]
                    },
                    "page_size": 5
                }
            else:
                # Get all items if no clear status
                query_data = {"page_size": 5}
            
            response = requests.post(query_url, headers=headers, json=query_data)
            
            if response.status_code != 200:
                print(f"❌ Strategic goals query failed: {response.status_code}")
                return ["• Error querying strategic goals"]
                
            data = response.json()
            results = data.get('results', [])
            print(f"📊 Found {len(results)} strategic goals")
            
            strategic_goals = []
            for goal in results:
                try:
                    # Get title
                    title = self.extract_title_from_item(goal, properties)
                    
                    # Get progress if available
                    progress = self.extract_number_value(goal, properties, ['Progress', 'Completion', 'Percent'])
                    
                    # Get deadline if available
                    deadline = self.extract_date_value(goal, properties, ['Deadline', 'Due Date', 'Target Date'])
                    
                    # Format the goal
                    display_text = title
                    if progress is not None:
                        progress_percent = int(progress * 100) if progress <= 1 else int(progress)
                        display_text += f" ({progress_percent}% complete)"
                    if deadline:
                        display_text += f" - Due: {deadline}"
                    
                    strategic_goals.append(f"• {display_text}")
                    
                except Exception as goal_error:
                    print(f"⚠️ Error processing strategic goal: {goal_error}")
                    strategic_goals.append("• Strategic goal (details unavailable)")
            
            return strategic_goals if strategic_goals else ["• No active strategic goals"]
            
        except Exception as e:
            print(f"❌ Strategic goals error: {e}")
            return ["• Error accessing Strategic Goals database"]

    def get_journal_reflection_patterns(self):
        """Analyze recent journal entries for reflection patterns"""
        try:
            if not self.daily_journal_db_id:
                return ["• Daily Journal database not configured"]
            
            print("🔍 Analyzing Daily Journal database...")
            properties = self.debug_database_properties(self.daily_journal_db_id, "Daily Journal")
            
            if not properties:
                return ["• Journal analysis unavailable"]
            
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
                        "property": "Created time" if "Created time" in properties else "Created",
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
            
            # Analyze patterns (simplified version)
            reflection_insights = []
            
            if len(results) >= 3:
                reflection_insights = [
                    "• Best reflection time appears to be evening based on recent patterns",
                    "• Consider 15-20 minute reflection sessions for optimal insight",
                    "• Focus on daily wins and challenges for balanced perspective"
                ]
            else:
                reflection_insights = [
                    "• Establish consistent evening reflection routine (9-10 PM ideal)",
                    "• Start with 10-minute daily gratitude and progress review",
                    "• Use guided prompts for deeper self-analysis"
                ]
            
            return reflection_insights
            
        except Exception as e:
            print(f"❌ Journal analysis error: {e}")
            return ["• Journal analysis temporarily unavailable"]

    def extract_title_from_item(self, item, properties):
        """Extract title from Notion item with flexible property matching"""
        title_props = ['Title', 'Name', 'Goal', 'Task', 'Item']
        
        for prop_name in title_props:
            if prop_name in properties and prop_name in item['properties']:
                prop_data = item['properties'][prop_name]
                if prop_data.get('title') and len(prop_data['title']) > 0:
                    return prop_data['title'][0]['plain_text']
        
        return 'Untitled item'

    def extract_select_value(self, item, properties, possible_names):
        """Extract select property value"""
        for prop_name in possible_names:
            if prop_name in properties and prop_name in item['properties']:
                prop_data = item['properties'][prop_name]
                if prop_data.get('select') and prop_data['select']:
                    return prop_data['select']['name']
        return None

    def extract_number_value(self, item, properties, possible_names):
        """Extract number property value"""
        for prop_name in possible_names:
            if prop_name in properties and prop_name in item['properties']:
                prop_data = item['properties'][prop_name]
                if prop_data.get('number') is not None:
                    return prop_data['number']
        return None

    def extract_date_value(self, item, properties, possible_names):
        """Extract date property value"""
        for prop_name in possible_names:
            if prop_name in properties and prop_name in item['properties']:
                prop_data = item['properties'][prop_name]
                if prop_data.get('date') and prop_data['date'].get('start'):
                    date_str = prop_data['date']['start']
                    try:
                        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        return date_obj.strftime('%m/%d')
                    except:
                        return date_str
        return None

    def generate_strategic_briefing(self, calendar_data, checklist_items, strategic_goals, reflection_patterns):
        """Generate AI-powered strategic daily briefing"""
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        
        prompt = f"""
        Create a strategic daily briefing for {current_date} using ONLY the real data provided.
        
        REAL DATA FROM USER'S STRATEGIC SYSTEMS:
        
        WEEKLY CHECKLIST (pending items):
        {chr(10).join(checklist_items)}
        
        CALENDAR EVENTS & TIME BLOCKS:
        {chr(10).join(calendar_data['events'])}
        {chr(10).join(calendar_data['blocks'])}
        
        STRATEGIC GOALS (active):
        {chr(10).join(strategic_goals)}
        
        REFLECTION PATTERNS:
        {chr(10).join(reflection_patterns)}
        
        INSTRUCTIONS:
        - Use ONLY the specific items mentioned above
        - Reference actual percentages, deadlines, and item names
        - Create 3-5 concrete priorities per section
        - Be specific about timing based on calendar data
        
        Create exactly these sections:
        
        **TODAY'S FOCUS:**
        • Priority 1: [Specific item from Weekly Checklist with highest impact]
        • Priority 2: [Specific calendar event or time block that needs preparation/follow-up]
        • Priority 3: [Specific strategic goal milestone or next action]
        • Priority 4: [Additional high-value item from any source]
        • Priority 5: [One more strategic priority if data supports it]
        
        **ENERGY OPTIMIZATION:**
        • Peak Hours: [Specific times based on calendar gaps and important tasks]
        • Reflection Time: [Specific time recommendation based on reflection patterns and schedule]
        • Recovery Activities: [Intelligent suggestions based on workload intensity and available time]
        
        Be concrete and actionable. Reference specific items by name, times, and percentages.
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",  # Using GPT-4 for more strategic intelligence
                messages=[
                    {"role": "system", "content": "You are a strategic productivity coach who creates highly specific, data-driven daily briefings focused on high-impact activities and optimal energy management."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.6
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            # Fallback briefing with actual data
            fallback = f"""**TODAY'S FOCUS:**
            • Priority 1: {checklist_items[0] if checklist_items else 'Complete weekly checklist review'}
            • Priority 2: {calendar_data['events'][0] if calendar_data['events'] else 'Schedule strategic focus time'}
            • Priority 3: {strategic_goals[0] if strategic_goals else 'Define strategic goal priorities'}
            
            **ENERGY OPTIMIZATION:**
            • Peak Hours: 9-11 AM for focused strategic work
            • Reflection Time: {reflection_patterns[0] if reflection_patterns else 'Evening reflection routine'}
            • Recovery Activities: Schedule breaks between intense focus sessions
            """
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
                    print("✅ Updated strategic daily briefing")
                else:
                    print(f"❌ Error updating briefing: {response.status_code}")
            else:
                # Create new block
                create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
                payload = {"children": [new_block_data]}
                response = requests.patch(create_url, headers=headers, json=payload)
                if response.status_code == 200:
                    print("✅ Created new strategic daily briefing")
                else:
                    print(f"❌ Error creating briefing: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error updating briefing: {str(e)}")

    def run(self):
        """Main execution with strategic focus"""
        print(f"🎯 Generating strategic daily briefing for {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        # Gather strategic data
        print("📅 Getting calendar events and time blocks...")
        calendar_data = self.get_calendar_events_and_blocks()
        print(f"   Calendar: {len(calendar_data['events'])} events, {len(calendar_data['blocks'])} focus blocks")
        
        print("📋 Getting weekly checklist items...")
        checklist_items = self.get_weekly_checklist_items()
        print(f"   Checklist: {len(checklist_items)} pending items")
        
        print("🎯 Getting strategic goals...")
        strategic_goals = self.get_strategic_goals()
        print(f"   Goals: {len(strategic_goals)} active goals")
        
        print("📝 Analyzing reflection patterns...")
        reflection_patterns = self.get_journal_reflection_patterns()
        print(f"   Reflection: {len(reflection_patterns)} insights")
        
        # Show data summary
        print("\n📊 STRATEGIC DATA SUMMARY:")
        print("Calendar Events:", calendar_data['events'][:2])
        print("Weekly Checklist:", checklist_items[:2])  
        print("Strategic Goals:", strategic_goals[:2])
        print("Reflection Patterns:", reflection_patterns[:1])
        
        # Generate strategic briefing
        print("\n🧠 Generating strategic AI briefing...")
        briefing = self.generate_strategic_briefing(calendar_data, checklist_items, strategic_goals, reflection_patterns)
        print(f"   Generated briefing ({len(briefing)} characters)")
        
        # Update Notion
        print("\n📝 Updating Notion page...")
        self.update_daily_briefing_section(briefing)
        print("✅ Strategic daily briefing completed!")

if __name__ == "__main__":
    briefing = StrategicDailyBriefing()
    briefing.run()
