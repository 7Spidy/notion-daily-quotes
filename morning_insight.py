import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MorningInsightGenerator:
    """Generates personalized morning insights using GPT-5 mini and Google Calendar."""
    
    def __init__(self):
        """Initialize the generator with OpenAI and Google Calendar clients."""
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.calendar_service = self._setup_google_calendar()
        self.ist_tz = ZoneInfo("Asia/Kolkata")
        
        # Configuration
        self.work_threshold_hours = 2
        self.model = "gpt-5-mini"  # Correct model name
        self.max_tokens = 300
        self.temperature = 0.9
        
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
    
    def _check_for_work_day(self):
        """Check if today has 2+ hours of work-related events."""
        if not self.calendar_service:
            return False
        
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
            work_events = [e for e in events if "work" in e.get("summary", "").lower() 
                          or "meeting" in e.get("summary", "").lower()]
            
            total_duration = 0
            for event in work_events:
                start_time = event.get("start", {}).get("dateTime")
                end_time = event.get("end", {}).get("dateTime")
                if start_time and end_time:
                    start_dt = datetime.fromisoformat(start_time)
                    end_dt = datetime.fromisoformat(end_time)
                    duration = (end_dt - start_dt).total_seconds() / 3600
                    total_duration += duration
            
            return total_duration >= self.work_threshold_hours
        except Exception as e:
            print(f"⚠️ Error checking work day: {str(e)}")
            return False
    
    def _generate_wisdom(self):
        """Generate a fresh piece of wisdom using GPT-5 mini."""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a wisdom advisor who provides short, inspiring, and actionable morning insights. Keep responses to 1-2 sentences maximum."
                    },
                    {
                        "role": "user",
                        "content": "Generate a fresh and unique piece of morning wisdom for today. Make it inspiring and practical."
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ Error generating wisdom: {str(e)}")
            return "Every day is a fresh opportunity to grow and make a difference. 🌱"
    
    def _generate_work_insight(self):
        """Generate insights for a work-heavy day."""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a productivity coach. Provide brief, actionable advice for managing a busy work day."
                    },
                    {
                        "role": "user",
                        "content": "Today has back-to-back work commitments. Give me one key insight to stay productive and balanced."
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ Error generating work insight: {str(e)}")
            return "Focus on your top 3 priorities. Everything else can wait. 💼"
    
    def _generate_rest_insight(self):
        """Generate insights for a rest/leisure day."""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a wellness advisor. Provide brief advice for enjoying a relaxed day."
                    },
                    {
                        "role": "user",
                        "content": "Today is light on work commitments. Give me one insight on how to best enjoy this day."
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ Error generating rest insight: {str(e)}")
            return "Use this free time to recharge and do something you love. 🌿"
    
    def generate_morning_insight(self):
        """Main method to generate complete morning insight."""
        try:
            # Get timestamp
            date_formatted = self._get_today_date_formatted()
            time_formatted = self._get_current_time_ist()
            
            # Check if work day
            is_work_day = self._check_for_work_day()
            
            # Generate insights
            wisdom = self._generate_wisdom()
            
            if is_work_day:
                day_insight = self._generate_work_insight()
                day_type = "💼 Work Day"
            else:
                day_insight = self._generate_rest_insight()
                day_type = "🌿 Rest Day"
            
            # Format output
            output = f"""
╔════════════════════════════════════════════╗
║  AI-Generated Morning Insights             ║
║  {date_formatted} - {time_formatted}          ║
╚════════════════════════════════════════════╝

📌 Daily Wisdom
{wisdom}

📊 Today's Focus: {day_type}
{day_insight}

═══════════════════════════════════════════════
Generated using GPT-5 mini | IST Timezone
═══════════════════════════════════════════════
"""
            
            return output.strip()
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
    print(insight)
    generator.save_to_log(insight)


if __name__ == "__main__":
    main()
