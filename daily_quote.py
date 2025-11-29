import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import time
import random

class ContentRemixGenerator:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        
        # Media database IDs (same as original)
        self.movies_db_id = os.getenv('MOVIES_DB_ID')
        self.books_db_id = os.getenv('BOOKS_DB_ID')
        self.games_db_id = os.getenv('GAMES_DB_ID')
        
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
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ All {self.max_retries} attempts failed: {str(e)}")
                    raise e

    def _query_media_database(self, db_id, media_type):
        """Query media database - FILTER: Status = In Progress OR Done"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
        
        # NEW: Filter for "In Progress" or "Done" status
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
        
        if response.status_code != 200:
            raise Exception(f"{media_type} database query failed: {response.status_code}")
            
        data = response.json()
        results = data.get('results', [])
        
        media_items = []
        for item in results:
            try:
                name = 'Untitled'
                if 'Name' in item['properties'] and item['properties']['Name']['title']:
                    name = item['properties']['Name']['title'][0]['plain_text']
                
                # Get status
                status = 'Unknown'
                if 'Status' in item['properties'] and item['properties']['Status']['status']:
                    status = item['properties']['Status']['status']['name']
                
                # Get additional context based on media type
                context = {'status': status}
                
                if media_type == 'Movies & TV':
                    if 'Type' in item['properties'] and item['properties']['Type']['select']:
                        context['type'] = item['properties']['Type']['select']['name']
                    if 'Where?' in item['properties'] and item['properties']['Where?']['select']:
                        context['platform'] = item['properties']['Where?']['select']['name']
                
                elif media_type == 'Books':
                    if 'Author' in item['properties'] and item['properties']['Author']['multi_select']:
                        authors = [author['name'] for author in item['properties']['Author']['multi_select']]
                        context['author'] = authors[0] if authors else 'Unknown Author'
                
                elif media_type == 'Games':
                    if 'System' in item['properties'] and item['properties']['System']['select']:
                        context['system'] = item['properties']['System']['select']['name']
                    if 'Hours Played' in item['properties'] and item['properties']['Hours Played']['number']:
                        context['hours'] = item['properties']['Hours Played']['number']
                
                media_items.append({
                    'name': name,
                    'type': media_type,
                    'context': context
                })
                
            except Exception as e:
                print(f"   ⚠️ Error parsing {media_type} item: {e}")
        
        return media_items

    def get_filtered_media_consumption(self):
        """Get media with status 'In Progress' or 'Done' from all 3 databases"""
        all_media = []
        
        # Get Movies & TV (In Progress or Done)
        if self.movies_db_id:
            try:
                print("🎬 Getting Movies & TV (In Progress/Done)...")
                movies_tv = self.notion_retry(self._query_media_database, self.movies_db_id, "Movies & TV")
                all_media.extend(movies_tv)
                print(f"   Found {len(movies_tv)} movies/shows")
            except Exception as e:
                print(f"   ❌ Movies & TV error: {e}")
        
        # Get Books (In Progress or Done)
        if self.books_db_id:
            try:
                print("📚 Getting Books (In Progress/Done)...")
                books = self.notion_retry(self._query_media_database, self.books_db_id, "Books")
                all_media.extend(books)
                print(f"   Found {len(books)} books")
            except Exception as e:
                print(f"   ❌ Books error: {e}")
        
        # Get Games (In Progress or Done)
        if self.games_db_id:
            try:
                print("🎮 Getting Games (In Progress/Done)...")
                games = self.notion_retry(self._query_media_database, self.games_db_id, "Games")
                all_media.extend(games)
                print(f"   Found {len(games)} games")
            except Exception as e:
                print(f"   ❌ Games error: {e}")
        
        return all_media

    def select_random_three(self, all_media):
        """Select 3 random items from media pool"""
        if len(all_media) < 3:
            print(f"   ⚠️ Only {len(all_media)} items available, using all")
            return all_media
        
        selected = random.sample(all_media, 3)
        return selected

    def generate_content_remix_synthesis(self, three_media):
        """Generate synthesis using GPT-5 with Responses API"""
        
        if not three_media:
            return self.get_fallback_synthesis()
        
        # Build context strings for each media item
        media_descriptions = []
        for i, media in enumerate(three_media, 1):
            context_str = f"{media['type']}"
            if media['context'].get('author'):
                context_str += f" by {media['context']['author']}"
            elif media['context'].get('type'):
                context_str += f" ({media['context']['type']})"
            elif media['context'].get('system'):
                context_str += f" on {media['context']['system']}"
            
            status = media['context'].get('status', 'Unknown')
            
            media_descriptions.append(
                f"[Content {i}] {media['name']} - {context_str} [Status: {status}]"
            )
        
        # Construct prompt for GPT-5
        synthesis_prompt = f"""Based on these 3 pieces of content from my consumption:

{chr(10).join(media_descriptions)}

Generate ONE insightful synthesis (max 150 words) that:
1. Identifies a common thread, contrasting perspective, or unexpected connection across all 3
2. Offers a unique insight that ties these ideas together
3. Ends with one actionable thought or reflective question
4. Uses an engaging, personal, motivational tone

Format your response as:

🧠 Today's Synthesis:
[Your creative synthesis connecting all 3 pieces]

💡 Reflection:
[One actionable insight or thought-provoking question]"""

        try:
            print("   🤖 Calling GPT-5 for synthesis...")
            
            # GPT-5 Responses API call with medium reasoning
            response = self.openai_client.responses.create(
                model="gpt-5",
                input=synthesis_prompt,
                reasoning={"effort": "medium"},  # Medium reasoning for creative synthesis
                text={"verbosity": "medium"}      # Medium verbosity for balanced output
            )
            
            synthesis = response.output_text.strip()
            
            print("   ✅ GPT-5 synthesis generated successfully")
            return synthesis
            
        except Exception as e:
            print(f"   ❌ GPT-5 API error: {e}")
            return self.get_fallback_synthesis()

    def get_fallback_synthesis(self):
        """Fallback synthesis if API fails"""
        fallbacks = [
            """🧠 Today's Synthesis:
Every story we consume—whether on screen, in books, or through games—teaches us about resilience, creativity, and the human experience. The common thread? They all push us to think differently and challenge our perspectives.

💡 Reflection:
What's one lesson from your recent media consumption that you can apply to a real challenge you're facing today?""",
            
            """🧠 Today's Synthesis:
The narratives we engage with shape how we see the world. Movies inspire us emotionally, books expand our thinking, and games teach us strategic problem-solving. Together, they form a complete toolkit for personal growth.

💡 Reflection:
Which medium has influenced your thinking the most recently, and why?"""
        ]
        
        return random.choice(fallbacks)

    def _update_notion_page(self, synthesis, three_media):
        """Update Notion page with Content Remix Summary"""
        current_date = self.get_current_ist_time().split(' - ')[0]
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Get existing blocks
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        response = requests.get(blocks_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get blocks: HTTP {response.status_code}")
            
        blocks = response.json()
        
        # Find existing synthesis block (look for "Content Remix" callout)
        synthesis_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'Content Remix' in block['callout']['rich_text'][0].get('plain_text', '')):
                synthesis_block_id = block['id']
                break
        
        # Build sources list
        sources = []
        for media in three_media:
            sources.append(f"• {media['name']} ({media['type']})")
        sources_text = "\n".join(sources)
        
        # Build content
        synthesis_content = f"""🎨 Content Remix - {current_date}

🔗 Sources:
{sources_text}

{synthesis}"""
        
        new_block = {
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": synthesis_content
                        }
                    }
                ],
                "icon": {
                    "emoji": "🎨"
                },
                "color": "purple_background"
            }
        }
        
        # Update or create block
        if synthesis_block_id:
            update_url = f"https://api.notion.com/v1/blocks/{synthesis_block_id}"
            response = requests.patch(update_url, headers=headers, json=new_block, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to update synthesis: HTTP {response.status_code}")
            return "updated"
        else:
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            payload = {"children": [new_block]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to create synthesis: HTTP {response.status_code}")
            return "created"

    def update_notion_page(self, synthesis, three_media):
        """Update synthesis with retry logic"""
        try:
            print("📝 Updating Notion page with Content Remix...")
            action = self.notion_retry(self._update_notion_page, synthesis, three_media)
            print(f"   ✅ Successfully {action} synthesis block!")
        except Exception as e:
            print(f"❌ Failed to update Notion after retries: {str(e)}")

    def run(self):
        """Main execution function"""
        print(f"🎨 Content Remix Summary Generator (GPT-5 Powered)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🤖 Model: GPT-5 (medium reasoning, medium verbosity)")
        print(f"🎯 Filter: Status = 'In Progress' OR 'Done'\n")
        
        print("🎯 Loading filtered media consumption...")
        all_media = self.get_filtered_media_consumption()
        
        if not all_media:
            print("❌ No media found with status 'In Progress' or 'Done'")
            print("   Using fallback synthesis...")
            synthesis = self.get_fallback_synthesis()
            three_media = []
        else:
            print(f"📊 Found {len(all_media)} total items across all databases\n")
            
            print("🎲 Selecting 3 random items for synthesis...")
            three_media = self.select_random_three(all_media)
            
            for i, media in enumerate(three_media, 1):
                print(f"   {i}. {media['name']} ({media['type']}) - {media['context'].get('status', 'Unknown')}")
            
            print("\n🔍 Generating AI synthesis...")
            synthesis = self.generate_content_remix_synthesis(three_media)
        
        print(f"\n📄 Generated Synthesis Preview:")
        print(f"   {synthesis[:100]}...\n")
        
        self.update_notion_page(synthesis, three_media)
        print(f"\n✅ Content Remix generation completed at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    generator = ContentRemixGenerator()
    generator.run()
