import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import time
import random
import traceback
import sys

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
                    print(f"      Full traceback: {traceback.format_exc()}")
                    raise e

    def _query_media_database(self, db_id, media_type):
        """Query media database - FILTER: Status = In Progress OR Done"""
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
        
        print(f"      → Sending request to: {query_url}")
        
        try:
            response = requests.post(query_url, headers=headers, json=query_data, timeout=10)
            print(f"      → Response status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"      → Response body: {response.text[:500]}")
                raise Exception(f"{media_type} database query failed: {response.status_code} - {response.text[:200]}")
                
            data = response.json()
            results = data.get('results', [])
            print(f"      → Found {len(results)} results")
            
        except requests.exceptions.Timeout:
            print(f"      ❌ Request timeout after 10 seconds")
            raise
        except requests.exceptions.RequestException as e:
            print(f"      ❌ Request error: {e}")
            raise
        
        media_items = []
        for item in results:
            try:
                name = 'Untitled'
                if 'Name' in item['properties'] and item['properties']['Name']['title']:
                    name = item['properties']['Name']['title'][0]['plain_text']
                
                status = 'Unknown'
                if 'Status' in item['properties'] and item['properties']['Status']['status']:
                    status = item['properties']['Status']['status']['name']
                
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
                print(f"      Item data: {json.dumps(item, indent=2)[:500]}")
        
        return media_items

    def get_filtered_media_consumption(self):
        """Get media with status 'In Progress' or 'Done' from all 3 databases"""
        all_media = []
        
        # Get Movies & TV
        if self.movies_db_id:
            try:
                print("🎬 Getting Movies & TV (In Progress/Done)...")
                movies_tv = self.notion_retry(self._query_media_database, self.movies_db_id, "Movies & TV")
                all_media.extend(movies_tv)
                print(f"   ✅ Found {len(movies_tv)} movies/shows")
            except Exception as e:
                print(f"   ❌ Movies & TV error: {e}")
                print(f"      Traceback: {traceback.format_exc()}")
        
        # Get Books
        if self.books_db_id:
            try:
                print("📚 Getting Books (In Progress/Done)...")
                books = self.notion_retry(self._query_media_database, self.books_db_id, "Books")
                all_media.extend(books)
                print(f"   ✅ Found {len(books)} books")
            except Exception as e:
                print(f"   ❌ Books error: {e}")
                print(f"      Traceback: {traceback.format_exc()}")
        
        # Get Games
        if self.games_db_id:
            try:
                print("🎮 Getting Games (In Progress/Done)...")
                games = self.notion_retry(self._query_media_database, self.games_db_id, "Games")
                all_media.extend(games)
                print(f"   ✅ Found {len(games)} games")
            except Exception as e:
                print(f"   ❌ Games error: {e}")
                print(f"      Traceback: {traceback.format_exc()}")
        
        print(f"\n📊 Total media collected: {len(all_media)}")
        return all_media

    def select_random_two(self, all_media):
        """Select 2 random items from media pool"""
        if len(all_media) < 2:
            print(f"   ⚠️ Only {len(all_media)} items available, using all")
            return all_media
        
        selected = random.sample(all_media, 2)
        print(f"   ✅ Selected 2 random items from pool of {len(all_media)}")
        return selected

    def generate_content_remix_synthesis(self, two_media):
        """Generate synthesis using GPT-5 with Responses API"""
        
        if not two_media:
            print("   ⚠️ No media provided, using fallback")
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
            
            status = media['context'].get('status', 'Unknown')
            
            media_descriptions.append(
                f"[Content {i}] {media['name']} - {context_str} [Status: {status}]"
            )
        
        synthesis_prompt = f"""Based on these 2 pieces of content from my consumption:

{chr(10).join(media_descriptions)}

Generate ONE insightful synthesis (max 120 words) that:
1. Identifies a common thread, contrasting perspective, or unexpected connection between both
2. Offers a unique insight that ties these ideas together
3. Ends with ONE actionable thought or reflective question on a new line
4. Uses an engaging, personal, motivational tone
5. CRITICAL: Do NOT label sections. Write the synthesis naturally, then add the actionable question on a new line.

Write your response as continuous prose followed by the actionable question."""

        try:
            print("   🤖 Calling GPT-5 for synthesis...")
            print(f"      Using model: gpt-5")
            print(f"      Reasoning effort: medium")
            
            response = self.openai_client.responses.create(
                model="gpt-5",
                input=synthesis_prompt,
                reasoning={"effort": "medium"},
                text={"verbosity": "medium"}
            )
            
            synthesis = response.output_text.strip()
            
            print("   ✅ GPT-5 synthesis generated successfully")
            print(f"      Preview: {synthesis[:100]}...")
            return synthesis
            
        except Exception as e:
            print(f"   ❌ GPT-5 API error: {e}")
            print(f"      Full traceback: {traceback.format_exc()}")
            print(f"   🔄 Using fallback synthesis")
            return self.get_fallback_synthesis()

    def get_fallback_synthesis(self):
        """Fallback synthesis if API fails"""
        fallbacks = [
            """Every story we consume teaches us about resilience, creativity, and the human experience. They push us to think differently and challenge our perspectives.

What's one lesson from your recent media consumption that you can apply to a real challenge you're facing today?""",
            
            """The narratives we engage with shape how we see the world. Movies inspire us emotionally, books expand our thinking, and games teach us strategic problem-solving.

Which medium has influenced your thinking the most recently, and why?"""
        ]
        
        selected = random.choice(fallbacks)
        print(f"   ✅ Fallback synthesis selected")
        return selected

    def _update_notion_page(self, synthesis, two_media):
        """Update Notion page with Content Remix Summary"""
        current_date = self.get_current_ist_time().split(' - ')[0]
        
        print(f"      → Updating page: {self.page_id}")
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        print(f"      → Fetching blocks from: {blocks_url}")
        
        try:
            response = requests.get(blocks_url, headers=headers, timeout=10)
            print(f"      → Get blocks status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"      → Response: {response.text[:500]}")
                raise Exception(f"Failed to get blocks: HTTP {response.status_code} - {response.text[:200]}")
                
            blocks = response.json()
            print(f"      → Found {len(blocks.get('results', []))} existing blocks")
            
        except Exception as e:
            print(f"      ❌ Error fetching blocks: {e}")
            raise
        
        # Find existing synthesis block
        synthesis_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'Content Remix' in block['callout']['rich_text'][0].get('plain_text', '')):
                synthesis_block_id = block['id']
                print(f"      → Found existing Content Remix block: {synthesis_block_id}")
                break
        
        if not synthesis_block_id:
            print(f"      → No existing Content Remix block found, will create new")
        
        # Build sources list
        sources = []
        for media in two_media:
            sources.append(f"• {media['name']} ({media['type']})")
        sources_text = "\n".join(sources)
        
        synthesis_content = f"""🎨 Content Remix - {current_date}

{sources_text}

{synthesis}"""
        
        print(f"      → Content preview: {synthesis_content[:100]}...")
        
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
            print(f"      → Updating existing block: {update_url}")
            response = requests.patch(update_url, headers=headers, json=new_block, timeout=10)
            print(f"      → Update status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"      → Response: {response.text[:500]}")
                raise Exception(f"Failed to update synthesis: HTTP {response.status_code} - {response.text[:200]}")
            return "updated"
        else:
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            print(f"      → Creating new block: {create_url}")
            payload = {"children": [new_block]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=10)
            print(f"      → Create status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"      → Response: {response.text[:500]}")
                raise Exception(f"Failed to create synthesis: HTTP {response.status_code} - {response.text[:200]}")
            return "created"

    def update_notion_page(self, synthesis, two_media):
        """Update synthesis with retry logic"""
        try:
            print("📝 Updating Notion page with Content Remix...")
            action = self.notion_retry(self._update_notion_page, synthesis, two_media)
            print(f"   ✅ Successfully {action} synthesis block!")
        except Exception as e:
            print(f"❌ Failed to update Notion after retries: {str(e)}")
            print(f"   Full traceback: {traceback.format_exc()}")

    def run(self):
        """Main execution function"""
        try:
            print(f"\n{'='*60}")
            print(f"🎨 Content Remix Summary Generator (GPT-5 Powered)")
            print(f"🕐 Started at: {self.get_current_ist_time()}")
            print(f"🤖 Model: GPT-5 (medium reasoning, medium verbosity)")
            print(f"🎯 Filter: Status = 'In Progress' OR 'Done'")
            print(f"{'='*60}\n")
            
            print("🎯 Loading filtered media consumption...")
            all_media = self.get_filtered_media_consumption()
            
            if not all_media:
                print("❌ No media found with status 'In Progress' or 'Done'")
                print("   Using fallback synthesis...")
                synthesis = self.get_fallback_synthesis()
                two_media = []
            else:
                print(f"\n🎲 Selecting 2 random items for synthesis...")
                two_media = self.select_random_two(all_media)
                
                for i, media in enumerate(two_media, 1):
                    print(f"   {i}. {media['name']} ({media['type']}) - {media['context'].get('status', 'Unknown')}")
                
                print("\n🔍 Generating AI synthesis...")
                synthesis = self.generate_content_remix_synthesis(two_media)
            
            print(f"\n📄 Generated Synthesis:")
            print(f"{synthesis}\n")
            
            self.update_notion_page(synthesis, two_media)
            
            print(f"\n{'='*60}")
            print(f"✅ Content Remix generation completed at: {self.get_current_ist_time()}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ FATAL ERROR in run(): {e}")
            print(f"{'='*60}")
            print(f"Full traceback:")
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    try:
        print("\n🚀 Starting Content Remix Generator...\n")
        generator = ContentRemixGenerator()
        generator.run()
        print("\n🎉 Script completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        sys.exit(1)
