#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import time

class MorningInsightGenerator:
    """Generates brief 2-part morning insights: Stoic reminder + Personal journal prompt"""
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        
        # Retry settings
        self.max_retries = 3
        self.retry_delay = 3

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

    def generate_morning_insight(self):
        """Generate 2-part morning insight with personal journal prompt"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now = datetime.now(ist)
        
        day_of_year = now.timetuple().tm_yday
        day_of_week = now.strftime("%A")
        current_year = now.year
        
        # Determine day context
        if day_of_week in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            day_context = 'work day - focusing on professional excellence and meaningful contribution'
        elif day_of_week == 'Saturday':
            day_context = 'Saturday - time for fun, personal projects, family, friends, and games'
        else:  # Sunday
            day_context = 'Sunday - reflection on the week, preparation for next week/month, and working on Notion goals'
        
        prompt = f"""Generate a brief 2-part morning insight. Be concise and profound. MAX 80 words total.

Today is {day_of_week}, Day {day_of_year} of {current_year}.

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

Format: TWO parts ONLY separated by a blank line. No section labels except for "📝 Journal Prompt:". Just the content."""

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
        
        print("🧠 Generating 2-part morning insight with personal journal prompt...")
        insight = self.generate_morning_insight()
        print(f"  📊 Generated: {len(insight)} characters\n")
        
        self.update_morning_insight(insight)
        print(f"\n✅ Process completed at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    generator = MorningInsightGenerator()
    generator.run()
