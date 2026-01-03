import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
import requests
import time

# Load environment variables
load_dotenv()

class MorningInsightGenerator:
    """Generates personalized morning insights using GPT-5 mini and Google Calendar."""
    
    def __init__(self):
        """Initialize the generator with OpenAI and Google Calendar clients."""
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.calendar_service = self._setup_google_calendar()
        self.ist_tz = ZoneInfo("Asia/Kolkata")
        
        # Notion configuration
        self.notion_token = os.getenv("NOTION_API_KEY")
        self.page_id = os.getenv("NOTION_PAGE_ID")
        
        # Configuration
        self.work_threshold_hours = 2
        self.model = "gpt-5-mini"
        self.max_retries = 3
        self.retry_delay = 2
        
    def _setup_google_calendar(self):
        """Setup Google Calendar API with service account credentials."""
        try:
            creds_json = os.getenv("GOOGLE_CREDENTIALS")
            if not creds_json:
                print("⚠️ Warning: GOOGLE_CREDENTIALS not found. Calendar features disabled.")
                return None
            
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/calendar.readonly"]
            )
            
            return build("calendar", "v3", credentials=credentials)
        except Exception as e:
            print(f"⚠️ Warning: Google Calendar setup failed: {str(e)}")
            return None
    
    def _get_today_date_formatted(self):
        """Get today's date in 'Day, Month Date, Year' format in IST."""
        now = datetime.now(self.ist_tz)
        return now.strftime("%A, %B %d, %Y")
    
    def _get_current_time_ist(self):
        """Get current time in HH:MM AM/PM IST format."""
        now = datetime.now(self.ist_tz)
        return now.strftime("%I:%M %p IST")
    
    def _get_day_of_year(self):
        """Get current day number of the year."""
        now = datetime.now(self.ist_tz)
        return now.timetuple().tm_yday
    
    def _get_day_of_week(self):
        """Get day of week."""
        now = datetime.now(self.ist_tz)
        return now.strftime("%A")
    
    def _get_special_calendar_events(self):
        """Check for birthdays, anniversaries, or special events today."""
        if not self.calendar_service:
            return None
        
        try:
            now = datetime.now(self.ist_tz)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            events_result = self.calendar_service.events().list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True
            ).execute()
            
            events = events_result.get("items", [])
            
            # Look for birthday, anniversary, or festival keywords
            special_keywords = ["birthday", "anniversary", "festival", "celebration"]
            for event in events:
                summary = event.get("summary", "").lower()
                for keyword in special_keywords:
                    if keyword in summary:
                        return event.get("summary")
            
            return None
        except Exception as e:
            print(f"⚠️ Error checking special events: {str(e)}")
            return None
    
    def _generate_morning_insight(self):
        """Generate the 3-part morning insight using GPT-5 mini."""
        day_of_year = self._get_day_of_year()
        day_of_week = self._get_day_of_week()
        special_event = self._get_special_calendar_events()
        current_year = datetime.now(self.ist_tz).year
        
        # Determine day context
        if day_of_week in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]:
            day_context = "work day - focus on professional tasks and career growth"
        elif day_of_week == "Saturday":
            day_context = "Saturday - time for fun, personal projects, family, friends, and games"
        else:  # Sunday
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
            print("   🤖 Calling GPT-5 mini for morning insight...")
            
            response = self.openai_client.responses.create(
                model=self.model,
                input=prompt,
                reasoning={"effort": "low"},
                text={"verbosity": "low"}
            )
            
            insight = response.output_text.strip()
            print("   ✅ Morning insight generated with GPT-5 mini")
            return insight
            
        except Exception as e:
            print(f"   ❌ GPT-5 mini error: {str(e)}")
            # Fallback
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
        """Retry wrapper for Notion API calls."""
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    print(f"   🔄 Retry attempt {attempt}/{self.max_retries}")
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * attempt
                    print(f"   ⚠️ Attempt {attempt} failed, retrying in {wait_time}s...")
                    print(f"      Error: {str(e)}")
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ All {self.max_retries} attempts failed: {str(e)}")
                    raise e
    
    def _update_notion_page(self, insight_content):
        """Update Notion page - INSERT AT TOP."""
        current_date = self._get_today_date_formatted()
        current_time = self._get_current_time_ist()
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        response = requests.get(blocks_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get blocks: {response.status_code}")
            
        blocks = response.json()
        
        insight_block_id = None
        results = blocks.get('results', [])
        
        # Search for existing Morning Insight block
        for block in results:
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                '☀️ Daily Insight' in block['callout']['rich_text'][0].get('plain_text', '')):
                insight_block_id = block['id']
                break
        
        full_content = f"☀️ Daily Insight - {current_date} - {current_time}\n\n{insight_content}"
        
        new_block = {
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": full_content}
                    }
                ],
                "icon": {"emoji": "☀️"},
                "color": "yellow_background"
            }
        }
        
        if insight_block_id:
            # Update existing block
            update_url = f"https://api.notion.com/v1/blocks/{insight_block_id}"
            response = requests.patch(update_url, headers=headers, json=new_block, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Update failed: {response.status_code}")
            
            # Move to top by deleting and recreating
            try:
                requests.delete(update_url, headers=headers, timeout=10)
                time.sleep(0.5)
                create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
                payload = {"children": [new_block]}
                requests.patch(create_url, headers=headers, json=payload, timeout=10)
                return "updated and moved to top"
            except Exception as e:
                print(f"   ⚠️ Repositioning failed, block updated in place: {e}")
                return "updated"
        else:
            # Create new block at top
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            payload = {"children": [new_block]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=10)
            
            if response.status_code != 200:
                raise Exception(f"Create failed: {response.status_code}")
            
            return "created at top"
    
    def update_notion_page(self, insight_content):
        """Update with retry."""
        try:
            print("📝 Updating Notion page...")
            action = self.notion_retry(self._update_notion_page, insight_content)
            print(f"   ✅ Successfully {action}!")
        except Exception as e:
            print(f"❌ Notion update failed: {e}")
    
    def generate_morning_insight(self):
        """Main method to generate complete morning insight."""
        try:
            date_formatted = self._get_today_date_formatted()
            time_formatted = self._get_current_time_ist()
            
            print(f"\n{'='*60}")
            print(f"☀️ Morning Insight Generator (GPT-5 mini)")
            print(f"🕐 {date_formatted} - {time_formatted}")
            print(f"{'='*60}\n")
            
            # Generate insight
            insight = self._generate_morning_insight()
            
            print(f"\n📄 Insight:\n{insight}\n")
            
            # Update Notion
            self.update_notion_page(insight)
            
            print(f"\n{'='*60}")
            print(f"✅ Completed!")
            print(f"{'='*60}\n")
            
            return insight
        except Exception as e:
            print(f"❌ Critical error: {str(e)}")
            return f"Error generating insights: {str(e)}"
    
    def save_to_log(self, content):
        """Save insights to a timestamped log file."""
        try:
            os.makedirs("logs", exist_ok=True)
            now = datetime.now(self.ist_tz)
            filename = f"logs/morning_insight_{now.strftime('%Y%m%d_%H%M%S')}.txt"
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            
            print(f"✅ Log saved to {filename}")
            return filename
        except Exception as e:
            print(f"⚠️ Error saving log: {str(e)}")
            return None


def main():
    """Entry point for the application."""
    generator = MorningInsightGenerator()
    insight = generator.generate_morning_insight()
    generator.save_to_log(insight)


if __name__ == "__main__":
    main()
