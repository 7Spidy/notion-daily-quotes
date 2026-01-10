#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import time

class MorningInsightGenerator:
    """Generates brief 3-part morning insights: Stoic reminder + Special events + Personal journal prompt"""
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 3
        
        # Google Calendar setup
        try:
            credentials_json = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.google_credentials = credentials_json
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        except Exception as e:
            print(f"Google setup error: {e}")
            self.google_credentials = None
            self.calendar_id = None

    def get_current_ist_time(self):
        """Get current IST time"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        return now_ist.strftime("%A, %B %d, %Y - %I:%M %p IST")

    def notion_retry(self, func, *args, **kwargs):
        """Retry wrapper for Notion API calls"""
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
        if not self.google_credentials:
            return None
        
        try:
            import jwt
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

    def get_lunar_phase_and_hindu_festivals(self):
        """Check for moon phases and Hindu festivals using astronomy API"""
        try:
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            
            # Use astronomy API to get moon phase
            # Format: YYYY-MM-DD
            date_str = now.strftime("%Y-%m-%d")
            
            # Using a free astronomy API
            url = f"https://api.astronomyapi.com/api/v2/bodies/positions/moon"
            
            # Fallback: Simple lunar calculation
            # This is an approximation based on known lunar cycle
            from math import floor
            
            # Known new moon: January 29, 2026
            known_new_moon = datetime(2026, 1, 29, tzinfo=ist)
            lunar_month = 29.53059  # days
            
            days_since = (now - known_new_moon).days
            phase = (days_since % lunar_month) / lunar_month
            
            lunar_event = None
            if 0 <= phase < 0.03 or phase > 0.97:
                lunar_event = "New Moon"
            elif 0.47 <= phase < 0.53:
                lunar_event = "Full Moon"
            
            # Hindu festivals for 2026 (major ones)
            hindu_festivals = {
                "2026-01-14": "Makar Sankranti",
                "2026-01-26": "Vasant Panchami",
                "2026-02-26": "Maha Shivaratri",
                "2026-03-14": "Holi",
                "2026-03-30": "Ugadi / Gudi Padwa",
                "2026-04-02": "Rama Navami",
                "2026-04-06": "Hanuman Jayanti",
                "2026-08-15": "Independence Day",
                "2026-08-16": "Janmashtami",
                "2026-09-05": "Ganesh Chaturthi",
                "2026-10-05": "Dussehra",
                "2026-10-17": "Karva Chauth",
                "2026-10-20": "Dhanteras",
                "2026-10-22": "Diwali",
                "2026-10-23": "Govardhan Puja",
                "2026-10-24": "Bhai Dooj",
                "2026-11-05": "Chhath Puja"
            }
            
            today_key = now.strftime("%Y-%m-%d")
            hindu_festival = hindu_festivals.get(today_key)
            
            if hindu_festival:
                print(f"  🪔 Hindu festival found: {hindu_festival}")
                return hindu_festival
            elif lunar_event:
                print(f"  🌙 Lunar event found: {lunar_event}")
                return lunar_event
            
            return None
            
        except Exception as e:
            print(f"  ⚠️ Lunar/Festival check error: {e}")
            return None

    def get_special_calendar_events(self):
        """Check for birthdays, anniversaries, and special events from calendar"""
        if not self.google_credentials or not self.calendar_id:
            return None
        
        try:
            access_token = self.get_google_access_token()
            if not access_token:
                return None
            
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
                return None
            
            events_data = response.json()
            events = events_data.get('items', [])
            
            # Look for special keywords
            special_keywords = ['birthday', 'anniversary', 'festival', 'celebration']
            
            for event in events:
                summary = event.get('summary', '').lower()
                for keyword in special_keywords:
                    if keyword in summary:
                        print(f"  🎉 Special event found: {event.get('summary')}")
                        return event.get('summary')
            
            return None
        except Exception as e:
            print(f"  ⚠️ Calendar error: {e}")
            return None

    def get_all_special_events(self):
        """Get all special events: calendar events + Hindu festivals + lunar phases"""
        events = []
        
        # Check calendar events
        calendar_event = self.get_special_calendar_events()
        if calendar_event:
            events.append(calendar_event)
        
        # Check Hindu festivals and lunar phases
        hindu_lunar_event = self.get_lunar_phase_and_hindu_festivals()
        if hindu_lunar_event:
            events.append(hindu_lunar_event)
        
        if events:
            return " | ".join(events)
        return None

    def generate_morning_insight(self):
        """Generate 3-part morning insight with personal journal prompt"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        
        day_of_year = now.timetuple().tm_yday
        day_of_week = now.strftime("%A")
        current_year = now.year
        special_events = self.get_all_special_events()
        
        # Determine day context
        if day_of_week in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            day_context = 'work day - focusing on professional excellence and meaningful contribution'
        elif day_of_week == 'Saturday':
            day_context = 'Saturday - time for fun, personal projects, family, friends, and games'
        else:  # Sunday
            day_context = 'Sunday - reflection on the week, preparation for next week/month, and working on Notion goals'
        
        # Build the prompt based on whether special events exist
        if special_events:
            prompt = f"""Generate a brief 3-part morning insight. Be concise and profound. MAX 100 words total.

Today is {day_of_week}, Day {day_of_year} of {current_year}.
Today's special event(s): {special_events}

**PART 1 - Stoic Time Reminder (1 sentence):**
Start with "Day {day_of_year} of {current_year}." Then add a profound stoic thought about time passing, mortality, or living intentionally. Keep it under 20 words.

**PART 2 - Special Event Acknowledgment (1 sentence):**
Today is special: {special_events}. Write 1 warm, culturally appropriate sentence acknowledging this event.

**PART 3 - Personal Journal Prompt:**
Create a deeply personal, introspective journaling prompt inspired by 2026 journal prompts. The prompt should:
- Be about personal growth, self-reflection, emotions, relationships, or life meaning
- NOT be work-related at all
- Encourage vulnerability and authentic self-exploration
- Relate naturally to the day's energy ({day_of_week})
- Be specific enough to guide deep reflection
- Start with "📝 Journal Prompt:"
- Keep it under 30 words

Format: Three distinct parts separated by blank lines. No section labels except for "📝 Journal Prompt:". Just the content."""
        else:
            prompt = f"""Generate a brief 2-part morning insight. Be concise and profound. MAX 80 words total.

Today is {day_of_week}, Day {day_of_year} of {current_year}.
There are NO special events today.

**PART 1 - Stoic Time Reminder (1 sentence):**
Start with "Day {day_of_year} of {current_year}." Then add a profound stoic thought about time passing, mortality, or living intentionally. Keep it under 20 words.

**PART 2 - Personal Journal Prompt:**
Create a deeply personal, introspective journaling prompt inspired by 2026 journal prompts. The prompt should:
- Be about personal growth, self-reflection, emotions, relationships, or life meaning
- NOT be work-related at all
- Encourage vulnerability and authentic self-exploration
- Relate naturally to the day's energy ({day_of_week})
- Be specific enough to guide deep reflection
- Start with "📝 Journal Prompt:"
- Keep it under 30 words

Format: TWO parts ONLY separated by a blank line. No section labels except for "📝 Journal Prompt:". Just the content.
CRITICAL: Do NOT include any birthday wishes, festival greetings, or event acknowledgments. There is NO special event today."""

        try:
            print("  🤖 Generating insight with GPT-5 mini...")
            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=prompt,
                reasoning={'effort': 'low'},
                text={'verbosity': 'low'}
            )
            
            insight = response.output_text.strip()
            print("  ✅ Insight generated")
            return insight
        
        except Exception as e:
            print(f"  ❌ GPT error: {e}")
            
            # Fallback based on day
            fallback = f"Day {day_of_year} of {current_year}. Each morning is a gift; unwrap it with intention.\n\n"
            
            if special_events:
                fallback += f"Today: {special_events} 🎉\n\n"
            
            if day_of_week == 'Sunday':
                fallback += "📝 Journal Prompt: What emotion have you been avoiding this week, and what is it trying to tell you about your needs?"
            elif day_of_week == 'Saturday':
                fallback += "📝 Journal Prompt: When did you last feel completely yourself, and what would it take to feel that way more often?"
            else:
                fallback += "📝 Journal Prompt: What relationship in your life needs more attention, and what small gesture could you offer today?"
            
            return fallback

    def sanitize_content_for_notion(self, content):
        """Sanitize content to prevent Notion API errors"""
        if not content:
            return "Morning insight content unavailable"
        
        import re
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)
        content = content.encode('utf-8', errors='ignore').decode('utf-8')
        
        max_content_length = 1950
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
            print(f"  ⚠️ Content truncated to {max_content_length} characters")
        
        if not content.strip():
            content = "Morning insight generated successfully"
        
        return content

    def _update_notion_block_safe(self, insight_content):
        """Update Notion with morning insight"""
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
        
        # Find existing morning insight block
        insight_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                '☀️ Morning Insight' in block['callout']['rich_text'][0].get('plain_text', '')):
                insight_block_id = block['id']
                break
        
        current_datetime = self.get_current_ist_time()
        full_content = f"☀️ Morning Insight - {current_datetime}\n\n{insight_content}"
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
                    "emoji": "☀️"
                },
                "color": "orange_background"
            }
        }
        
        try:
            if insight_block_id:
                # Update existing block
                update_url = f"https://api.notion.com/v1/blocks/{insight_block_id}"
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

    def update_morning_insight(self, insight_content):
        """Update Notion with retry"""
        try:
            print("📝 Updating Notion page with morning insight...")
            action = self.notion_retry(self._update_notion_block_safe, insight_content)
            print(f"  ✅ Successfully {action} Morning Insight!")
        except Exception as e:
            print(f"❌ Failed to update Notion: {str(e)}")

    def run(self):
        """Main execution"""
        print(f"☀️ Morning Insight Generator (GPT-5 mini)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay\n")
        
        print("🧠 Generating 3-part morning insight with personal journal prompt...")
        insight = self.generate_morning_insight()
        print(f"  📊 Generated: {len(insight)} characters\n")
        
        self.update_morning_insight(insight)
        print(f"\n✅ Process completed at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    generator = MorningInsightGenerator()
    generator.run()
