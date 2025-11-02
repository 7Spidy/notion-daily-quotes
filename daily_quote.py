import openai
import requests
import json
import os
from datetime import datetime
import time
import random

class MediaInspiredQuoteGenerator:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        
        # Media database IDs
        self.movies_db_id = os.getenv('MOVIES_DB_ID')
        self.books_db_id = os.getenv('BOOKS_DB_ID')
        self.games_db_id = os.getenv('GAMES_DB_ID')
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2

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
        """Internal method to query media database (wrapped with retry)"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
        query_data = {
            "filter": {
                "property": "Status",
                "status": {
                    "equals": "In progress"
                }
            },
            "page_size": 10
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
                
                # Get additional context based on media type
                context = {}
                
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

    def get_current_media_consumption(self):
        """Get all current media consumption with retry logic"""
        all_media = []
        
        # Get Movies & TV in progress
        if self.movies_db_id:
            try:
                print("🎬 Getting Movies & TV in progress...")
                movies_tv = self.notion_retry(self._query_media_database, self.movies_db_id, "Movies & TV")
                all_media.extend(movies_tv)
                print(f"   Found {len(movies_tv)} movies/shows in progress")
            except Exception as e:
                print(f"   ❌ Movies & TV error: {e}")
        
        # Get Books in progress
        if self.books_db_id:
            try:
                print("📚 Getting Books in progress...")
                books = self.notion_retry(self._query_media_database, self.books_db_id, "Books")
                all_media.extend(books)
                print(f"   Found {len(books)} books in progress")
            except Exception as e:
                print(f"   ❌ Books error: {e}")
        
        # Get Games in progress
        if self.games_db_id:
            try:
                print("🎮 Getting Games in progress...")
                games = self.notion_retry(self._query_media_database, self.games_db_id, "Games")
                all_media.extend(games)
                print(f"   Found {len(games)} games in progress")
            except Exception as e:
                print(f"   ❌ Games error: {e}")
        
        return all_media

    def generate_media_inspired_quote(self, current_media):
        """Generate a quote inspired by current media consumption"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        if not current_media:
            # Fallback prompt if no media in progress
            prompt = f"""
            Generate an inspiring quote for {current_date} for someone who loves:
            - Technology and AI development
            - Gaming and strategic thinking
            - Reading and continuous learning
            - Movies, TV shows, and storytelling
            
            The quote should be motivational, focus on personal growth, and be max 2 sentences.
            Format: "Quote text" - Author (or "Daily Reflection" if original)
            """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a thoughtful quote curator who creates meaningful daily inspiration based on current media consumption. Create quotes that bridge entertainment with personal development."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.8
            )
            
            quote = response.choices[0].message.content.strip()
            
            # Add media context to quote if available
            if current_media:
                selected = random.choice(current_media)
                quote += f"\n\n💡 *Inspired by your current {selected['type'].lower()}: {selected['name']}*"
            
            return quote
            
        except Exception as e:
            print(f"OpenAI error: {e}")
            fallback_quotes = [
                '"Every story you consume shapes the story you create. Choose wisely and let inspiration guide your journey." - Daily Reflection',
                '"Like the heroes in your favorite tales, your greatest adventures begin with a single decision to grow." - Daily Reflection',
                '"The books you read, games you play, and shows you watch are training grounds for your imagination." - Daily Reflection'
            ]
            return random.choice(fallback_quotes)

    def _update_notion_page(self, quote):
        """Internal method to update Notion page (wrapped with retry)"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        # Get current page blocks
        blocks_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
        response = requests.get(blocks_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get blocks: HTTP {response.status_code}")
            
        blocks = response.json()
        
        # Find existing quote block
        quote_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'Daily Quote' in block['callout']['rich_text'][0].get('plain_text', '')):
                quote_block_id = block['id']
                break
        
        # Prepare quote content
        quote_content = f"🌟 Daily Quote - {current_date}\n\n{quote}"
        
        new_block = {
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": quote_content
                        }
                    }
                ],
                "icon": {
                    "emoji": "✨"
                },
                "color": "blue_background"
            }
        }
        
        if quote_block_id:
            # Update existing block
            update_url = f"https://api.notion.com/v1/blocks/{quote_block_id}"
            response = requests.patch(update_url, headers=headers, json=new_block, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to update quote: HTTP {response.status_code}")
            return "updated"
        else:
            # Create new block
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            payload = {"children": [new_block]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to create quote: HTTP {response.status_code}")
            return "created"

    def update_notion_page(self, quote):
        """Update quote with retry logic"""
        try:
            print("📝 Updating Notion page with media-inspired quote...")
            action = self.notion_retry(self._update_notion_page, quote)
            print(f"   ✅ Successfully {action} quote block!")
        except Exception as e:
            print(f"❌ Failed to update Notion after retries: {str(e)}")

    def run(self):
        """Main execution function"""
        print(f"✨ Media-Inspired Daily Quote Generator")
        print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay\n")
        
        # Get current media consumption
        print("🎯 Analyzing current media consumption...")
        current_media = self.get_current_media_consumption()
        
        if current_media:
            print(f"📊 Found {len(current_media)} items currently in progress:")
            for item in current_media[:3]:  # Show first 3
                print(f"   • {item['name']} ({item['type']})")
        else:
            print("📊 No media currently in progress - using general inspiration")
        
        # Generate quote
        print("\n🤖 Generating media-inspired quote...")
        quote = self.generate_media_inspired_quote(current_media)
        print(f"   Generated quote: {quote[:100]}...")
        
        # Update Notion page
        self.update_notion_page(quote)
        print(f"\n✅ Process completed at: {datetime.now().strftime('%H:%M:%S IST')}")

if __name__ == "__main__":
    generator = MediaInspiredQuoteGenerator()
    generator.run()
