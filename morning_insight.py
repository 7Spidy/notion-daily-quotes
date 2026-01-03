#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import time

print("=" * 60)
print("☀️ MORNING INSIGHT - SCRIPT STARTED")
print("=" * 60)

class MorningInsightGenerator:
    """Generates personalized morning insights using GPT-5 mini and Google Calendar."""
    
    def __init__(self):
        """Initialize - EXACTLY like daily_briefing.py"""
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

    def _get_day_of_year(self):
        """Get day of year"""
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).timetuple().tm_yday
    
    def _get_day_of_week(self):
        """Get day of week"""
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).strftime("%A")
    
    def _get_special_calendar_events(self):
        """Check for special events"""
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
            
            special_keywords = ['birthday', 'anniversary', 'festival', 'celebration']
            
            for event in events:
                summary = event.get('summary', '').lower()
                for keyword in special_keywords:
                    if keyword in summary:
                        print(f"   🎉 Special event found: {event.get('summary')}")
                        return event.get('summary')
            
            return None
        except Exception as e:
            print(f"   ⚠️ Calendar error: {e}")
            return None
    
    def _generate_morning_insight(self):
        """Generate morning insight"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        
        day_of_year = self._get_day_of_year()
        day_of_week = self._get_day_of_week()
        special_event = self._get_special_calendar_events()
        current_year = now.year
        
        if day_of_week in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            day_context = 'work day - focus on professional tasks and career growth'
        elif day_of_week == 'Saturday':
            day_context = 'Saturday - time for fun, personal projects, family, friends, and games'
        else:
            day_context = 'Sunday - reflection on the week, preparation for next week/month, and working on Notion goals and tasks'
        
        special_text = f'Special event today: {special_event}' if special_event else 'No special events today. Check for Hindu festivals or astronomical events like new/full moon, eclipse.'
        
        prompt = f"""Generate a brief 3-part morning insight for Day {day_of_year} of {current_year}. Today is {day_of_week}.

PART 1: One line stoic reminder. Format: "Day {day_of_year} of {current_year}. [brief stoic thought - max 15 words]"

PART 2: {special_text}
If special event, acknowledge warmly (1 sentence). If no special event but today has significance (Hindu festival, new/full moon, eclipse), mention briefly. Otherwise skip.

PART 3: One thought-provoking line for journaling based on: {day_context}
Make it inspiring and suitable for reflection. Max 20 words.

Keep total under 100 words. This is read before morning journal."""

        try:
            print("   🤖 Calling GPT-5 mini...")
            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=prompt,
                reasoning={'effort': 'low'},
                text={'verbosity': 'low'}
            )
            insight = response.output_text.strip()
            print("   ✅ Insight generated")
            return insight
        except Exception as e:
            print(f"   ❌ GPT error: {e}")
            fallback = f"Day {day_of_year} of {current_year}. Each day is a gift - use it wisely.\n\n"
            if special_event:
                fallback += f"Today: {special_event}\n\n"
            if day_of_week == 'Sunday':
                fallback += "What did this week teach you about your goals?"
            elif day_of_week == 'Saturday':
                fallback += "What brings you joy that you've been postponing?"
            else:
                fallback += "What's one action today that aligns with your vision?"
            return fallback
    
    def sanitize_content_for_notion(self, content):
        """Sanitize content to prevent Notion API errors"""
        if not content:
            return "Daily insight content unavailable"
        
        import re
        
        # Remove control characters
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)
        
        # Replace problematic unicode
        content = content.encode('utf-8', errors='ignore').decode('utf-8')
        
        # Size limit
        max_content_length = 1950
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
            print(f"   ⚠️ Content truncated to {max_content_length} characters")
        
        # Ensure not empty
        if not content.strip():
            content = "Daily insight generated successfully"
        
        return content

    def _update_notion_block_safe(self, insight_content):
        """Update Notion - EXACTLY like daily_briefing.py pattern"""
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
        
        # Find existing block
        insight_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                '☀️ Daily Insight' in block['callout']['rich_text'][0].get('plain_text', '')):
                insight_block_id = block['id']
                break
        
        current_datetime = self.get_current_ist_time()
        full_content = f"☀️ Daily Insight - {current_datetime}\n\n{insight_content}"
        
        # Sanitize
        full_content = self.sanitize_content_for_notion(full_content)
        
        print(f"   📊 Final content size: {len(full_content)} characters")
        
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
                "color": "yellow_background"
            }
        }
        
        try:
            if insight_block_id:
                # Update existing block
                update_url = f"https://api.notion.com/v1/blocks/{insight_block_id}"
                response = requests.patch(update_url, headers=headers, json=new_block_data, timeout=15)
                
                if response.status_code != 200:
                    print(f"   ❌ Update failed: {response.status_code} - {response.text[:300]}")
                    raise Exception(f"Failed to update block: HTTP {response.status_code}")
                    
                return "updated"
            else:
                # Create new block
                create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
                payload = {"children": [new_block_data]}
                response = requests.patch(create_url, headers=headers, json=payload, timeout=15)
                
                if response.status_code != 200:
                    print(f"   ❌ Create failed: {response.status_code} - {response.text[:300]}")
                    raise Exception(f"Failed to create block: HTTP {response.status_code}")
                    
                return "created"
                
        except Exception as e:
            print(f"   💡 Detailed error: {str(e)}")
            print(f"   📊 Content length: {len(full_content)} characters")
            raise e

    def update_daily_insight(self, insight_content):
        """Update Notion with retry"""
        try:
            print("📝 Updating Notion page...")
            action = self.notion_retry(self._update_notion_block_safe, insight_content)
            print(f"   ✅ Successfully {action} Daily Insight!")
        except Exception as e:
            print(f"❌ Failed to update Notion: {str(e)}")

    def run(self):
        """Main execution - EXACTLY like daily_briefing.py"""
        print(f"☀️ Morning Insight Generator (GPT-5 mini)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay\n")
        
        print("🧠 Generating morning insight...")
        insight = self._generate_morning_insight()
        print(f"   📊 Generated: {len(insight)} chars\n")
        
        self.update_daily_insight(insight)
        print(f"\n✅ Process completed at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    briefing = MorningInsightGenerator()
    briefing.run()
