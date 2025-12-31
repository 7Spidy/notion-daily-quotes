#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import jwt
import time

class MorningInsight:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        
        # Google Calendar setup
        try:
            credentials_json = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
            self.google_credentials = credentials_json
            self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        except Exception as e:
            print(f"Google setup error: {e}")
            self.google_credentials = None
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 3

    def get_current_ist_time(self):
        """Get current IST time"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        return now_ist.strftime("%A, %B %d, %Y - %I:%M %p IST")

    def get_today_ist(self):
        """Get today's date in IST"""
        ist = timezone(timedelta(hours=5, minutes=30))
        return datetime.now(ist).date()

    def get_day_of_year(self):
        """Get current day of year and year"""
        ist = timezone(timedelta(hours=5, minutes=30))
        today = datetime.now(ist).date()
        day_of_year = today.timetuple().tm_yday
        year = today.year
        return day_of_year, year

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

    def check_is_workday(self):
        """Check if today is a work day by looking for 💼Work or Work block"""
        try:
            access_token = self.get_google_access_token()
            if not access_token:
                print("   ⚠️ Calendar access unavailable - assuming workday")
                return True
            
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
                print(f"   ⚠️ Calendar API error: {response.status_code} - assuming workday")
                return True
            
            events_data = response.json()
            events = events_data.get('items', [])
            
            # Look for Work or 💼Work events with multiple hour duration
            for event in events:
                summary = event.get('summary', '').lower()
                
                if 'work' in summary or '💼' in event.get('summary', ''):
                    start = event.get('start', {})
                    end = event.get('end', {})
                    
                    start_time_str = start.get('dateTime', start.get('date', ''))
                    end_time_str = end.get('dateTime', end.get('date', ''))
                    
                    # Calculate duration
                    try:
                        if 'T' in start_time_str and 'T' in end_time_str:
                            start_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                            end_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                            duration_hours = (end_dt - start_dt).total_seconds() / 3600
                            
                            if duration_hours >= 2:  # At least 2 hours = workday
                                print(f"   💼 Work block detected: {duration_hours:.1f} hours - WORKDAY")
                                return True
                    except Exception as parse_error:
                        print(f"   ⚠️ Error parsing event time: {parse_error}")
            
            print("   🏖️ No significant Work block found - NON-WORKDAY (weekend/holiday)")
            return False
            
        except Exception as e:
            print(f"   ⚠️ Calendar check error: {e} - assuming workday")
            return True

    def get_special_calendar_events_today(self):
        """Get birthdays/anniversaries from today's calendar"""
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
            
            # Look for Birthday/Anniversary in event name
            for event in events:
                summary = event.get('summary', '')
                
                if 'birthday' in summary.lower() or 'anniversary' in summary.lower():
                    print(f"   🎂 Special event found: {summary}")
                    return summary
            
            return None
            
        except Exception as e:
            print(f"   ⚠️ Calendar error: {e}")
            return None

    def generate_stoic_wisdom(self, day_of_year, year):
        """Generate fresh stoic wisdom about passage of time using GPT"""
        prompt = f"""Generate ONE short, powerful stoic wisdom about the passage of time and taking action.

Context: Today is Day {day_of_year} of {year}.

Requirements:
- Exactly ONE line, maximum 12 words
- Start with: "Day {day_of_year} of {year}."
- End with a verb/action (not a period, but implied)
- Examples style:
  - "Day 365 of 2025. What will you build with today?"
  - "Day 100 of 2025. Time compounds. Act now."
  - "Day 215 of 2025. Every moment shapes your legacy."
  - "Day 42 of 2025. Small actions today, large results tomorrow."

Be unique, fresh, and thought-provoking. This will be the first thing someone reads at 6:30 AM.

Respond with ONLY the single line, no punctuation at end, no quotes."""

        try:
            print("   🤖 Generating stoic wisdom...")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=30
            )
            
            wisdom = response.choices[0].message.content.strip()
            # Remove quotes if GPT added them
            wisdom = wisdom.strip('"\'\'').strip()
            print(f"   ✅ Wisdom: {wisdom}")
            return wisdom
            
        except Exception as e:
            print(f"   ❌ Stoic wisdom error: {e}")
            return f"Day {day_of_year} of {year}. Every moment matters"

    def generate_day_aware_insight(self, is_workday):
        """Generate day-aware inspiring insight based on workday status"""
        
        if is_workday:
            day_context = """This is a WORKDAY. Generate an inspiring insight for a professional who's stepping into their work day.
            
Requirements:
- 2-3 sentences maximum
- 50-70 words total
- Include ONE action-oriented question at the end (your journal prompt)
- Focus: breakthrough project, focus, growth, power
- Tone: energizing but grounded
- Start with an observation about their week/day
- End with a question that's personal and actionable
- Example:
  "You're stepping into your power this week. Focus on one breakthrough project that challenges you—that's where real growth lives. What's the smallest first step you can take today?"

Respond with 2-3 sentences ending with a reflective question. No labels or headers."""
        else:
            day_context = """This is a NON-WORKDAY (weekend or holiday). Generate an inspiring insight for someone with freedom today.
            
Requirements:
- 2-3 sentences maximum
- 50-70 words total
- Include ONE reflective/curiosity-sparking question at the end (your journal prompt)
- Focus: connection, creation, presence, joy, rest
- Tone: warm, introspective, celebratory
- For Saturday: energy, creativity, relationships. For Sunday: reflection, preparation, integration
- End with a question that's personal and invites experimentation
- Example:
  "Today is for connection and creation. Whether you're building something new or strengthening bonds, let joy guide your choices. Who or what needs your presence today?"

Respond with 2-3 sentences ending with a reflective question. No labels or headers."""
        
        prompt = f"{day_context}\n\nGenerate the insight now."
        
        try:
            print(f"   🤖 Generating {'work' if is_workday else 'non-work'} day insight...")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
                max_tokens=100
            )
            
            insight = response.choices[0].message.content.strip()
            print(f"   ✅ Insight generated: {len(insight)} characters")
            return insight
            
        except Exception as e:
            print(f"   ❌ Insight generation error: {e}")
            if is_workday:
                return "Focus on one meaningful project today. What's the smallest step forward you can take right now?"
            else:
                return "Today is yours to create with. What will bring you joy and connection today?"

    def generate_birthday_reminder(self, event_name):
        """Format birthday/anniversary as a friendly reminder"""
        # Extract person name and type
        event_lower = event_name.lower()
        
        if 'anniversary' in event_lower:
            event_type = "Anniversary"
            emoji = "💍"
        else:
            event_type = "Birthday"
            emoji = "🎂"
        
        # Clean up name
        name = event_name.replace("Birthday", "").replace("Anniversary", "").replace("birthday", "").replace("anniversary", "").strip()
        
        return f"{emoji} {name}'s {event_type} - Reach out and celebrate"

    def _get_page_blocks(self):
        """Get all blocks from the Notion page"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        response = requests.get(blocks_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get page blocks: HTTP {response.status_code}")
        
        return response.json().get('results', [])

    def _find_insight_block(self, blocks):
        """Find existing Morning Insight block"""
        for block in blocks:
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0):
                text = block['callout']['rich_text'][0].get('plain_text', '')
                if '✨ Morning Insight' in text or 'Day ' in text and 'of 2025' in text:
                    return block['id']
        return None

    def _update_notion_block_safe(self, stoic_wisdom, special_event, day_aware_insight):
        """Update Notion page with Morning Insight"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Get current blocks
        blocks = self.notion_retry(self._get_page_blocks)
        insight_block_id = self._find_insight_block(blocks)
        
        # Build content
        current_datetime = self.get_current_ist_time()
        
        # Part 1: Stoic wisdom
        content_lines = [stoic_wisdom]
        
        # Part 2: Special event (if exists)
        if special_event:
            content_lines.append("")  # blank line
            content_lines.append(special_event)
        
        # Part 3: Day-aware insight
        content_lines.append("")  # blank line
        content_lines.append(day_aware_insight)
        
        full_content = "\n".join(content_lines)
        
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
                    "emoji": "✨"
                },
                "color": "orange_background"
            }
        }
        
        try:
            if insight_block_id:
                # Update existing block
                print(f"   📝 Updating existing Morning Insight block...")
                update_url = f"https://api.notion.com/v1/blocks/{insight_block_id}"
                response = requests.patch(update_url, headers=headers, json=new_block_data, timeout=15)
                
                if response.status_code != 200:
                    print(f"   ❌ Update failed: {response.status_code}")
                    raise Exception(f"Failed to update block: HTTP {response.status_code}")
                
                print(f"   ✅ Block updated successfully")
                return "updated"
            else:
                # Create new block
                print(f"   ✨ Creating new Morning Insight block...")
                create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
                payload = {"children": [new_block_data]}
                response = requests.patch(create_url, headers=headers, json=payload, timeout=15)
                
                if response.status_code != 200:
                    print(f"   ❌ Create failed: {response.status_code}")
                    raise Exception(f"Failed to create block: HTTP {response.status_code}")
                
                print(f"   ✅ Block created successfully")
                return "created"
        
        except Exception as e:
            print(f"   💡 Error details: {str(e)}")
            raise e

    def update_notion_page(self, stoic_wisdom, special_event, day_aware_insight):
        """Update Notion page with retry logic"""
        try:
            print("📝 Updating Notion page with Morning Insight...")
            action = self.notion_retry(self._update_notion_block_safe, stoic_wisdom, special_event, day_aware_insight)
            print(f"   ✅ Successfully {action} Morning Insight block!")
        except Exception as e:
            print(f"❌ Failed to update Notion: {str(e)}")

    def run(self):
        """Main execution"""
        print(f"\n{'='*70}")
        print(f"✨ Morning Insight Generator")
        print(f"🕐 {self.get_current_ist_time()}")
        print(f"{'='*70}\n")
        
        try:
            # Part 1: Get day of year for stoic wisdom
            print("📅 Calculating day of year...")
            day_of_year, year = self.get_day_of_year()
            print(f"   Day {day_of_year} of {year}")
            
            # Part 2: Check if it's a workday
            print("\n📊 Checking if today is a workday...")
            is_workday = self.check_is_workday()
            
            # Part 3: Get special events (birthdays/anniversaries)
            print("\n🎂 Checking for birthdays/anniversaries...")
            special_event_raw = self.get_special_calendar_events_today()
            special_event_formatted = None
            if special_event_raw:
                special_event_formatted = self.generate_birthday_reminder(special_event_raw)
                print(f"   ✅ Found: {special_event_formatted}")
            else:
                print(f"   ℹ️ No special events today")
            
            # Part 1: Generate stoic wisdom
            print("\n📖 Part 1: Stoic Wisdom")
            stoic_wisdom = self.generate_stoic_wisdom(day_of_year, year)
            
            # Part 3: Generate day-aware insight
            print("\n💡 Part 3: Day-Aware Insight")
            day_aware_insight = self.generate_day_aware_insight(is_workday)
            
            # Update Notion
            print("\n🔄 Updating Notion...")
            self.update_notion_page(stoic_wisdom, special_event_formatted, day_aware_insight)
            
            print(f"\n{'='*70}")
            print(f"✅ Morning Insight generated successfully!")
            print(f"{'='*70}\n")
            
        except Exception as e:
            print(f"\n❌ FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    insight = MorningInsight()
    insight.run()
