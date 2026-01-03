#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print("=" * 60)
print("☀️ MORNING INSIGHT - SCRIPT STARTED")
print("=" * 60)

import sys
print("✅ sys imported")

import os
print("✅ os imported")

import json
print("✅ json imported")

from datetime import datetime, timezone, timedelta
print("✅ datetime imported")

import time
print("✅ time imported")

try:
    import requests
    print("✅ requests imported")
except ImportError as e:
    print(f"❌ FATAL: requests not installed: {e}")
    sys.exit(1)

try:
    import openai
    print("✅ openai imported")
except ImportError as e:
    print(f"❌ FATAL: openai not installed: {e}")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    print("✅ dotenv imported")
    # Try to load .env file (for local development)
    load_dotenv()
    print("✅ .env file loaded (if exists)")
except ImportError:
    print("⚠️ dotenv not available, using system environment variables")
except Exception as e:
    print(f"⚠️ Could not load .env: {e}")

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    print("✅ google API imports successful")
except ImportError as e:
    print(f"⚠️ Warning: google API not installed: {e}")
    Credentials = None
    build = None

print("\n" + "=" * 60)
print("✅ ALL IMPORTS SUCCESSFUL")
print("=" * 60 + "\n")

class MorningInsightGenerator:
    """Generates personalized morning insights using GPT-5 mini and Google Calendar."""
    
    def __init__(self):
        """Initialize the generator with OpenAI and Google Calendar clients."""
        print("🔧 Initializing MorningInsightGenerator...")
        
        # Try multiple variable name variants (GitHub Actions vs local .env)
        print("   🔍 Checking environment variables...")
        
        # OpenAI API Key
        self.openai_api_key = (
            os.getenv('OPENAI_API_KEY') or 
            os.getenv('OPENAI_KEY') or
            None
        )
        
        # Notion API Key - try multiple names
        self.notion_token = (
            os.getenv('NOTION_API_KEY') or 
            os.getenv('NOTION_TOKEN') or
            os.getenv('NOTION_KEY') or
            None
        )
        
        # Notion Page ID - try multiple names
        self.page_id = (
            os.getenv('NOTION_PAGE_ID') or 
            os.getenv('PAGE_ID') or
            os.getenv('DAILY_PAGE_ID') or
            None
        )
        
        # Debug: Show ALL environment variables that contain 'NOTION' or 'PAGE'
        print("\n   📋 Available environment variables:")
        all_env_vars = {k: v for k, v in os.environ.items()}
        notion_vars = {k: f"{'*' * 10}{v[-4:]}" if len(v) > 4 else "****" 
                      for k, v in all_env_vars.items() 
                      if 'NOTION' in k.upper() or 'PAGE' in k.upper()}
        
        if notion_vars:
            for key, masked_value in notion_vars.items():
                print(f"      {key}: {masked_value}")
        else:
            print("      ⚠️ No NOTION or PAGE variables found in environment")
        
        print("\n   🔍 Variable detection results:")
        print(f"      OPENAI_API_KEY: {'✅ Found' if self.openai_api_key else '❌ NOT FOUND'}")
        print(f"      NOTION_TOKEN: {'✅ Found' if self.notion_token else '❌ NOT FOUND'}")
        print(f"      NOTION_PAGE_ID: {'✅ Found' if self.page_id else '❌ NOT FOUND'}")
        
        # Validate all required env vars
        missing_vars = []
        if not self.openai_api_key:
            missing_vars.append('OPENAI_API_KEY')
        if not self.notion_token:
            missing_vars.append('NOTION_API_KEY or NOTION_TOKEN')
        if not self.page_id:
            missing_vars.append('NOTION_PAGE_ID or PAGE_ID')
        
        if missing_vars:
            print("\n" + "=" * 60)
            print("❌ CONFIGURATION ERROR")
            print("=" * 60)
            print(f"Missing: {', '.join(missing_vars)}")
            print("\n🛠️ FOR GITHUB ACTIONS:")
            print("   Go to: Repository Settings → Secrets → Actions")
            print("   Add these secrets:")
            print("      - OPENAI_API_KEY")
            print("      - NOTION_API_KEY (or NOTION_TOKEN)")
            print("      - NOTION_PAGE_ID (or PAGE_ID)")
            print("\n🛠️ FOR LOCAL DEVELOPMENT:")
            print("   Create .env file with:")
            print("      OPENAI_API_KEY=your_key")
            print("      NOTION_API_KEY=your_token")
            print("      NOTION_PAGE_ID=your_page_id")
            print("=" * 60)
            raise ValueError(f"❌ Missing: {', '.join(missing_vars)}")
        
        print(f"\n   ✅ OPENAI_API_KEY: {'*' * 10}{self.openai_api_key[-4:]}")
        print(f"   ✅ NOTION_TOKEN: {'*' * 10}{self.notion_token[-4:]}")
        print(f"   ✅ NOTION_PAGE_ID: {self.page_id}")
        
        # Initialize OpenAI client
        try:
            self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
            print("   ✅ OpenAI client initialized")
        except Exception as e:
            print(f"   ❌ Failed to initialize OpenAI: {e}")
            raise
        
        # Setup Google Calendar
        self.calendar_service = self._setup_google_calendar()
        
        # Configuration
        self.model = "gpt-5-mini"
        self.max_retries = 3
        self.retry_delay = 2
        
        print("   ✅ MorningInsightGenerator initialized successfully\n")
        
    def _setup_google_calendar(self):
        """Setup Google Calendar API with service account credentials."""
        if not Credentials or not build:
            print("   ℹ️ Google API libraries not available")
            return None
            
        try:
            creds_json = os.getenv("GOOGLE_CREDENTIALS")
            if not creds_json:
                print("   ℹ️ GOOGLE_CREDENTIALS not set (calendar features disabled)")
                return None
            
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/calendar.readonly"]
            )
            
            service = build("calendar", "v3", credentials=credentials)
            print("   ✅ Google Calendar initialized")
            return service
        except Exception as e:
            print(f"   ℹ️ Calendar disabled: {str(e)[:100]}")
            return None
    
    def get_current_ist_time(self):
        """Get current IST time correctly"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        return now_ist.strftime("%A, %B %d, %Y - %I:%M %p IST")
    
    def _get_day_of_year(self):
        """Get current day number of the year."""
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        return now.timetuple().tm_yday
    
    def _get_day_of_week(self):
        """Get day of week."""
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        return now.strftime("%A")
    
    def _get_special_calendar_events(self):
        """Check for birthdays, anniversaries, or special events today."""
        if not self.calendar_service:
            return None
        
        try:
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            events_result = self.calendar_service.events().list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True
            ).execute()
            
            events = events_result.get("items", [])
            
            special_keywords = ["birthday", "anniversary", "festival", "celebration"]
            for event in events:
                summary = event.get("summary", "").lower()
                for keyword in special_keywords:
                    if keyword in summary:
                        print(f"   🎉 Special event: {event.get('summary')}")
                        return event.get("summary")
            
            print("   ℹ️ No special events on calendar")
            return None
        except Exception as e:
            print(f"   ℹ️ Calendar check skipped: {str(e)[:50]}")
            return None
    
    def _generate_morning_insight(self):
        """Generate the 3-part morning insight using GPT-5 mini."""
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        
        day_of_year = self._get_day_of_year()
        day_of_week = self._get_day_of_week()
        special_event = self._get_special_calendar_events()
        current_year = now.year
        
        if day_of_week in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            day_context = "work day - focus on professional tasks and career growth"
        elif day_of_week == "Saturday":
            day_context = "Saturday - time for fun, personal projects, family, friends, and games"
        else:
            day_context = "Sunday - reflection on the week, preparation for next week/month, and working on Notion goals and tasks"
        
        special_event_text = f"Special event today: {special_event}" if special_event else "No special events today. Check for Hindu festivals or astronomical events like new/full moon, eclipse."
        
        prompt = f"""Generate a brief 3-part morning insight for Day {day_of_year} of {current_year}. Today is {day_of_week}.

PART 1: One line stoic reminder about the passage of time. Format: "Day {day_of_year} of {current_year}. [Add a brief stoic thought about time, mortality, or present moment - max 15 words]"

PART 2: {special_event_text}
If special event exists, acknowledge it warmly (1 short sentence).
If no special event, check if today has significance (Hindu festival, new/full moon, eclipse, solstice, etc.) and mention it briefly. If nothing, skip this part entirely.

PART 3: One thought-provoking line for journaling based on this context: {day_context}
Make it personally inspiring, locally or globally relevant, and suitable for journaling reflection. Max 20 words.

CRITICAL: Keep total response under 100 words. Be concise, meaningful, and thought-provoking. This is the first thing I read before writing my journal.

Format exactly like this (skip Part 2 if no special event):
Day {day_of_year} of {current_year}. [stoic thought]

[Part 2 if applicable]

[One thought-provoking question or statement for journaling]"""

        try:
            print("   🤖 Calling GPT-5 mini...")
            
            response = self.openai_client.responses.create(
                model=self.model,
                input=prompt,
                reasoning={"effort": "low"},
                text={"verbosity": "low"}
            )
            
            insight = response.output_text.strip()
            print("   ✅ Morning insight generated")
            return insight
            
        except Exception as e:
            print(f"   ⚠️ GPT error, using fallback: {str(e)[:50]}")
            fallback = f"Day {day_of_year} of {current_year}. Each day is a gift - use it wisely.\n\n"
            if special_event:
                fallback += f"Today: {special_event}\n\n"
            if day_of_week == "Sunday":
                fallback += "What did this week teach you about your goals and priorities?"
            elif day_of_week == "Saturday":
                fallback += "What brings you joy today that you've been postponing?"
            else:
                fallback += "What's one small action today that aligns with your bigger vision?"
            return fallback
    
    def notion_retry(self, func, *args, **kwargs):
        """Retry wrapper for Notion API calls"""
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    print(f"   🔄 Retry {attempt}/{self.max_retries}")
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    print(f"   ⚠️ Attempt {attempt} failed, retrying in {wait_time}s...")
                    print(f"      Error: {str(e)[:100]}")
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ All {self.max_retries} attempts failed")
                    raise e
    
    def _update_notion_page(self, insight_content):
        """Update Notion page - INSERT AT TOP"""
        current_time = self.get_current_ist_time()
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        
        print(f"   📡 GET {blocks_url[:60]}...")
        response = requests.get(blocks_url, headers=headers, timeout=10)
        
        print(f"   📊 Response: {response.status_code}")
        
        if response.status_code != 200:
            error_detail = response.text[:300]
            print(f"   ❌ Error: {error_detail}")
            raise Exception(f"HTTP {response.status_code}: {error_detail}")
            
        blocks = response.json()
        
        # Find existing Daily Insight block
        insight_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                '☀️ Daily Insight' in block['callout']['rich_text'][0].get('plain_text', '')):
                insight_block_id = block['id']
                print(f"   ✅ Found existing block")
                break
        
        full_content = f"☀️ Daily Insight - {current_time}\n\n{insight_content}"
        
        if len(full_content) > 1900:
            full_content = full_content[:1900] + "..."
            print(f"   ⚠️ Truncated to {len(full_content)} chars")
        
        new_block_data = {
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": full_content}}],
                "icon": {"emoji": "☀️"},
                "color": "yellow_background"
            }
        }
        
        if insight_block_id:
            update_url = f"https://api.notion.com/v1/blocks/{insight_block_id}"
            response = requests.patch(update_url, headers=headers, json=new_block_data, timeout=15)
            
            if response.status_code != 200:
                print(f"   ❌ Update failed: {response.status_code}")
                raise Exception(f"Update failed: {response.status_code}")
            
            return "updated"
        else:
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            payload = {"children": [new_block_data]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=15)
            
            if response.status_code != 200:
                print(f"   ❌ Create failed: {response.status_code}")
                raise Exception(f"Create failed: {response.status_code}")
            
            return "created"
    
    def update_notion_page(self, insight_content):
        """Update with retry"""
        try:
            print("📝 Updating Notion page...")
            action = self.notion_retry(self._update_notion_page, insight_content)
            print(f"   ✅ Successfully {action} Daily Insight!")
        except Exception as e:
            print(f"❌ Notion update failed: {e}")
    
    def run(self):
        """Main execution"""
        print(f"☀️ Morning Insight Generator (GPT-5 mini)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🔄 Retry: {self.max_retries} attempts, {self.retry_delay}s delay\n")
        
        print("🧠 Generating morning insight...")
        insight = self._generate_morning_insight()
        print(f"   📊 Generated: {len(insight)} characters\n")
        
        print(f"📄 Insight Preview:\n{insight}\n")
        
        self.update_notion_page(insight)
        
        print(f"\n✅ Completed at: {self.get_current_ist_time()}")


def main():
    """Entry point"""
    try:
        generator = MorningInsightGenerator()
        generator.run()
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
