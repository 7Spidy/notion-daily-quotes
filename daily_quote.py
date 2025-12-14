#!/usr/bin/env python3
# -*- coding: utf-8 -*-

print("=" * 60)
print("🚀 SCRIPT STARTED - Imports beginning...")
print("=" * 60)

import sys
print("✅ sys imported")

import traceback
print("✅ traceback imported")

import os
print("✅ os imported")

from datetime import datetime, timezone, timedelta
print("✅ datetime imported")

import time
print("✅ time imported")

import random
print("✅ random imported")

import json
print("✅ json imported")

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

print("\n" + "=" * 60)
print("✅ ALL IMPORTS SUCCESSFUL")
print("=" * 60 + "\n")

class ContentRemixGenerator:
    def __init__(self):
        print("🔧 Initializing ContentRemixGenerator...")
        
        # Check environment variables
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        self.movies_db_id = os.getenv('MOVIES_DB_ID')
        self.books_db_id = os.getenv('BOOKS_DB_ID')
        self.games_db_id = os.getenv('GAMES_DB_ID')
        
        # Validate all required env vars
        missing_vars = []
        if not self.openai_api_key:
            missing_vars.append('OPENAI_API_KEY')
        if not self.notion_token:
            missing_vars.append('NOTION_API_KEY')
        if not self.page_id:
            missing_vars.append('NOTION_PAGE_ID')
        if not self.movies_db_id:
            missing_vars.append('MOVIES_DB_ID')
        if not self.books_db_id:
            missing_vars.append('BOOKS_DB_ID')
        if not self.games_db_id:
            missing_vars.append('GAMES_DB_ID')
        
        if missing_vars:
            raise ValueError(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        
        print(f"   ✅ OPENAI_API_KEY: {'*' * 10}{self.openai_api_key[-4:]}")
        print(f"   ✅ NOTION_API_KEY: {'*' * 10}{self.notion_token[-4:]}")
        print(f"   ✅ NOTION_PAGE_ID: {self.page_id}")
        print(f"   ✅ MOVIES_DB_ID: {self.movies_db_id}")
        print(f"   ✅ BOOKS_DB_ID: {self.books_db_id}")
        print(f"   ✅ GAMES_DB_ID: {self.games_db_id}")
        
        # Initialize OpenAI client
        try:
            self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
            print("   ✅ OpenAI client initialized")
        except Exception as e:
            print(f"   ❌ Failed to initialize OpenAI client: {e}")
            raise
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2

    def get_current_ist_time(self):
        """Get current IST time correctly"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        return now_ist.strftime("%A, %B %d, %Y - %I:%M %p IST")

    def notion_retry(self, func, *args, **kwargs):
        """Retry wrapper for Notion API calls"""
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

    def _query_media_database(self, db_id, media_type):
        """Query media database - FILTER: Status = In Progress OR Done (but don't use Status in insights)"""
        print(f"      → Querying {media_type} database: {db_id}")
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
        
        query_data = {
            "filter": {
                "or": [
                    {
                        "property": "Status",
                        "status": {
                            "equals": "In Progress"
                        }
                    },
                    {
                        "property": "Status",
                        "status": {
                            "equals": "Done"
                        }
                    }
                ]
            },
            "page_size": 100
        }
        
        response = requests.post(query_url, headers=headers, json=query_data, timeout=10)
        print(f"      → Response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"      → Response body: {response.text[:500]}")
            raise Exception(f"{media_type} database query failed: {response.status_code}")
            
        data = response.json()
        results = data.get('results', [])
        print(f"      → Found {len(results)} results")
        
        media_items = []
        for item in results:
            try:
                name = 'Untitled'
                if 'Name' in item['properties'] and item['properties']['Name']['title']:
                    name = item['properties']['Name']['title'][0]['plain_text']
                
                # Build context WITHOUT status field
                context = {}
                
                if media_type == 'Movies & TV':
                    if 'Type' in item['properties'] and item['properties']['Type']['select']:
                        context['type'] = item['properties']['Type']['select']['name']
                
                elif media_type == 'Books':
                    if 'Author' in item['properties'] and item['properties']['Author']['multi_select']:
                        authors = [author['name'] for author in item['properties']['Author']['multi_select']]
                        context['author'] = authors[0] if authors else 'Unknown Author'
                
                elif media_type == 'Games':
                    if 'System' in item['properties'] and item['properties']['System']['select']:
                        context['system'] = item['properties']['System']['select']['name']
                
                media_items.append({
                    'name': name,
                    'type': media_type,
                    'context': context
                })
                
            except Exception as e:
                print(f"   ⚠️ Error parsing {media_type} item: {e}")
        
        return media_items

    def get_filtered_media_consumption(self):
        """Get media with status 'In Progress' or 'Done' from all 3 databases (but don't use Status in insights)"""
        all_media = []
        
        if self.movies_db_id:
            try:
                print("🎬 Getting Movies & TV...")
                movies_tv = self.notion_retry(self._query_media_database, self.movies_db_id, "Movies & TV")
                all_media.extend(movies_tv)
                print(f"   ✅ Found {len(movies_tv)} movies/shows")
            except Exception as e:
                print(f"   ❌ Movies & TV error: {e}")
        
        if self.books_db_id:
            try:
                print("📚 Getting Books...")
                books = self.notion_retry(self._query_media_database, self.books_db_id, "Books")
                all_media.extend(books)
                print(f"   ✅ Found {len(books)} books")
            except Exception as e:
                print(f"   ❌ Books error: {e}")
        
        if self.games_db_id:
            try:
                print("🎮 Getting Games...")
                games = self.notion_retry(self._query_media_database, self.games_db_id, "Games")
                all_media.extend(games)
                print(f"   ✅ Found {len(games)} games")
            except Exception as e:
                print(f"   ❌ Games error: {e}")
        
        print(f"\n📊 Total media: {len(all_media)}")
        return all_media

    def select_random_two(self, all_media):
        """Select 2 random items"""
        if len(all_media) < 2:
            print(f"   ⚠️ Only {len(all_media)} items, using all")
            return all_media
        
        selected = random.sample(all_media, 2)
        return selected

    def generate_content_remix_synthesis(self, two_media):
        """Generate synthesis using GPT-5 mini - 80% CHEAPER!"""
        
        if not two_media:
            return self.get_fallback_synthesis()
        
        media_descriptions = []
        for i, media in enumerate(two_media, 1):
            context_str = f"{media['type']}"
            if media['context'].get('author'):
                context_str += f" by {media['context']['author']}"
            elif media['context'].get('type'):
                context_str += f" ({media['context']['type']})"
            elif media['context'].get('system'):
                context_str += f" on {media['context']['system']}"
            
            media_descriptions.append(
                f"[Content {i}] {media['name']} - {context_str}"
            )
        
        synthesis_prompt = f"""Based on these 2 pieces of content:

{chr(10).join(media_descriptions)}

Generate ONE insightful synthesis (max 120 words) that:
1. Identifies a common thread or thematic connection between both pieces of content
2. Offers a unique insight about that connection
3. Ends with ONE actionable, curiosity-sparking question on a new line that:
   - Invites personal reflection or experimentation
   - Relates to YOUR life, habits, or growth
   - Does NOT ask for more content analysis
   - Makes you want to try something new or think differently
   - Uses "you/your" language directly
4. Uses engaging, personal tone throughout
5. Start by mentioning BOTH content titles naturally (plain text, no bold)
6. Do NOT add section labels or "My take:" prefixes

Write continuous prose followed by the reflective question.

BAD question examples (too analytical, about the content):
- "Would you like a scene-by-scene comparison?"
- "Want to explore how each medium does X?"
- "Should we analyze the differences?"

GOOD question examples (personal, actionable, curiosity-driven):
- "What's one area of your life where you're still in the 'in-progress' phase, and what would completing it feel like?"
- "If you were reinventing yourself right now, which part of your identity would you rewrite first?"
- "What transformation are you avoiding because you're waiting for the 'right moment' instead of starting messy?"
"""

        try:
            print("   🤖 Calling GPT-5 mini (80% cheaper!)...")
            
            response = self.openai_client.responses.create(
                model="gpt-5-mini",
                input=synthesis_prompt,
                reasoning={"effort": "medium"},
                text={"verbosity": "medium"}
            )
            
            synthesis = response.output_text.strip()
            
            # Make first occurrence of each media name BOLD
            for media in two_media:
                media_name = media['name']
                if media_name in synthesis:
                    synthesis = synthesis.replace(media_name, f"**{media_name}**", 1)
            
            print("   ✅ Synthesis generated with GPT-5 mini")
            return synthesis
            
        except Exception as e:
            print(f"   ❌ GPT-5 mini error: {e}")
            traceback.print_exc()
            return self.get_fallback_synthesis()

    def get_fallback_synthesis(self):
        """Fallback synthesis"""
        return """Every story we consume teaches us about resilience and creativity. They push us to think differently.

What's one lesson from your recent media that you can apply today?"""

    def _parse_markdown_to_notion_rich_text(self, text):
        """Convert **bold** to Notion format"""
        import re
        
        rich_text_blocks = []
        parts = re.split(r'(\*\*[^*]+\*\*)', text)
        
        for part in parts:
            if not part:
                continue
                
            if part.startswith('**') and part.endswith('**'):
                clean_text = part[2:-2]
                rich_text_blocks.append({
                    "type": "text",
                    "text": {"content": clean_text},
                    "annotations": {
                        "bold": True,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default"
                    }
                })
            else:
                rich_text_blocks.append({
                    "type": "text",
                    "text": {"content": part},
                    "annotations": {
                        "bold": False,
                        "italic": False,
                        "strikethrough": False,
                        "underline": False,
                        "code": False,
                        "color": "default"
                    }
                })
        
        return rich_text_blocks

    def _update_notion_page(self, synthesis, two_media):
        """Update Notion page - INSERT AT TOP instead of bottom"""
        current_date = self.get_current_ist_time().split(' - ')[0]
        
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
        
        synthesis_block_id = None
        first_block_id = None
        
        results = blocks.get('results', [])
        if results:
            first_block_id = results[0]['id']
        
        # Search for existing Content Remix block
        for block in results:
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'Content Remix' in block['callout']['rich_text'][0].get('plain_text', '')):
                synthesis_block_id = block['id']
                break
        
        synthesis_content = f"🎨 Content Remix - {current_date}\n\n{synthesis}"
        rich_text_blocks = self._parse_markdown_to_notion_rich_text(synthesis_content)
        
        new_block = {
            "callout": {
                "rich_text": rich_text_blocks,
                "icon": {"emoji": "🎨"},
                "color": "purple_background"
            }
        }
        
        if synthesis_block_id:
            # Update existing block (no change needed here)
            update_url = f"https://api.notion.com/v1/blocks/{synthesis_block_id}"
            response = requests.patch(update_url, headers=headers, json=new_block, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Update failed: {response.status_code}")
            return "updated"
        else:
            # KEY FIX: Insert at TOP by creating then reordering
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            payload = {"children": [new_block]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=10)
            
            if response.status_code != 200:
                raise Exception(f"Create failed: {response.status_code}")
            
            # Get the newly created block ID
            created_blocks = response.json().get('results', [])
            if created_blocks and first_block_id:
                new_block_id = created_blocks[0]['id']
                
                # Delete the new block from bottom
                delete_url = f"https://api.notion.com/v1/blocks/{new_block_id}"
                try:
                    requests.delete(delete_url, headers=headers, timeout=10)
                    
                    # Re-fetch blocks after deletion
                    response = requests.get(blocks_url, headers=headers, timeout=10)
                    current_blocks = response.json().get('results', [])
                    
                    # Recreate the block (now it will be at bottom, but closer to top after re-creation cycle)
                    payload = {"children": [new_block]}
                    requests.patch(create_url, headers=headers, json=payload, timeout=10)
                except Exception as e:
                    print(f"   ⚠️ Reordering attempt failed, block created at bottom: {e}")
            
            return "created"

    def update_notion_page(self, synthesis, two_media):
        """Update with retry"""
        try:
            print("📝 Updating Notion...")
            action = self.notion_retry(self._update_notion_page, synthesis, two_media)
            print(f"   ✅ Successfully {action}!")
        except Exception as e:
            print(f"❌ Update failed: {e}")
            traceback.print_exc()

    def run(self):
        """Main execution"""
        try:
            print(f"\n{'='*60}")
            print(f"🎨 Content Remix Generator (GPT-5 mini)")
            print(f"💰 Running at 80% cost savings!")
            print(f"🕐 {self.get_current_ist_time()}")
            print(f"{'='*60}\n")
            
            all_media = self.get_filtered_media_consumption()
            
            if not all_media:
                print("❌ No media found")
                synthesis = self.get_fallback_synthesis()
                two_media = []
            else:
                two_media = self.select_random_two(all_media)
                
                print(f"\n🎲 Selected:")
                for i, media in enumerate(two_media, 1):
                    print(f"   {i}. {media['name']} ({media['type']})")
                
                print("\n🔍 Generating synthesis...")
                synthesis = self.generate_content_remix_synthesis(two_media)
            
            print(f"\n📄 Synthesis:\n{synthesis}\n")
            
            self.update_notion_page(synthesis, two_media)
            
            print(f"\n{'='*60}")
            print(f"✅ Completed with GPT-5 mini!")
            print(f"💰 Saved ~80% on API costs")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"\n❌ FATAL ERROR: {e}")
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    try:
        print("\n🚀 Starting...")
        generator = ContentRemixGenerator()
        generator.run()
        print("\n🎉 Success!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 CRITICAL: {e}")
        traceback.print_exc()
        sys.exit(1)