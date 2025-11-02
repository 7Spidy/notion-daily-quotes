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
        """Internal method to query media database - ALL MEDIA (no status filter)"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
        query_data = {
            "page_size": 50
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
                
                # Get status for logging
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

    def get_all_media_consumption(self):
        """Get ALL media from databases with retry logic"""
        all_media = []
        
        # Get ALL Movies & TV
        if self.movies_db_id:
            try:
                print("🎬 Getting ALL Movies & TV...")
                movies_tv = self.notion_retry(self._query_media_database, self.movies_db_id, "Movies & TV")
                all_media.extend(movies_tv)
                print(f"   Found {len(movies_tv)} total movies/shows")
            except Exception as e:
                print(f"   ❌ Movies & TV error: {e}")
        
        # Get ALL Books
        if self.books_db_id:
            try:
                print("📚 Getting ALL Books...")
                books = self.notion_retry(self._query_media_database, self.books_db_id, "Books")
                all_media.extend(books)
                print(f"   Found {len(books)} total books")
            except Exception as e:
                print(f"   ❌ Books error: {e}")
        
        # Get ALL Games
        if self.games_db_id:
            try:
                print("🎮 Getting ALL Games...")
                games = self.notion_retry(self._query_media_database, self.games_db_id, "Games")
                all_media.extend(games)
                print(f"   Found {len(games)} total games")
            except Exception as e:
                print(f"   ❌ Games error: {e}")
        
        return all_media

    def clean_quote_formatting(self, quote):
        """Clean up quote formatting to remove unwanted asterisks and italics"""
        import re
        
        # Remove *MediaTitle* patterns and replace with MediaTitle
        quote = re.sub(r'\*([^*]+)\*', r'\1', quote)
        
        # Clean up any double spaces
        quote = re.sub(r'\s+', ' ', quote)
        
        return quote.strip()

    def try_get_quote_from_media(self, media_item):
        """Try to get a real quote from a specific media item"""
        media_context = ""
        if media_item['type'] == 'Books' and media_item.get('context', {}).get('author'):
            media_context = f" by {media_item['context']['author']}"
        elif media_item['type'] == 'Movies & TV' and media_item.get('context', {}).get('type'):
            media_context = f" ({media_item['context']['type']})"
            
        prompt = f"Find a real, authentic, memorable quote from '{media_item['name']}'{media_context}. The quote must be an EXACT quote that actually appears in {media_item['name']}. Look for quotes about growth, determination, learning, overcoming challenges, wisdom, or achieving goals. Provide the exact quote as spoken/written in the original source. Format: Quote - Character/Speaker Name, {media_item['name']}. If you don't know any real quotes from this specific {media_item['type'].lower()}, respond with exactly: NO_QUOTE_FOUND"
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a quote researcher who finds ONLY real, authentic quotes from actual books, movies, TV shows, and video games. You never create, modify, or paraphrase quotes. If you don't know an exact quote from the requested source, respond with exactly 'NO_QUOTE_FOUND'."},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=150,
                temperature=0.1
            )
            
            quote = response.choices[0].message.content.strip()
            
            # Check if AI couldn't find a quote
            if "NO_QUOTE_FOUND" in quote or "sorry" in quote.lower() or "don't have access" in quote.lower():
                return None
                
            # Clean formatting
            quote = self.clean_quote_formatting(quote)
            return quote
            
        except Exception as e:
            print(f"   ⚠️ Quote attempt failed: {e}")
            return None

    def generate_media_inspired_quote(self, all_media):
        """Generate a quote with smart fallback logic"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        if not all_media:
            print("   No media found, using general inspirational quotes")
            fallback_quotes = [
                '"The way to get started is to quit talking and begin doing." - Walt Disney',
                '"Innovation distinguishes between a leader and a follower." - Steve Jobs',
                '"Success is not final, failure is not fatal: it is the courage to continue that counts." - Winston Churchill'
            ]
            return random.choice(fallback_quotes)
        
        # Shuffle media list for randomness
        shuffled_media = all_media.copy()
        random.shuffle(shuffled_media)
        
        # Try up to 5 different media items to find a real quote
        for attempt in range(min(5, len(shuffled_media))):
            selected_media = shuffled_media[attempt]
            print(f"   Attempt {attempt + 1}: Trying {selected_media['name']} ({selected_media['type']})")
            
            quote = self.try_get_quote_from_media(selected_media)
            
            if quote:
                print(f"   ✅ Found authentic quote from {selected_media['name']}")
                return quote
            else:
                print(f"   ❌ No quote found for {selected_media['name']}, trying next...")
        
        # If no quotes found from any media, use well-known media quotes
        print("   Using backup famous media quotes")
        famous_media_quotes = [
            '"May the Force be with you." - Obi-Wan Kenobi, Star Wars',
            '"I am inevitable." - Thanos, Avengers',
            '"With great power comes great responsibility." - Uncle Ben, Spider-Man',
            '"The needs of the many outweigh the needs of the few." - Spock, Star Trek',
            '"I\'ll be back." - Terminator, The Terminator',
            '"Life is like a box of chocolates." - Forrest Gump, Forrest Gump'
        ]
        
        return random.choice(famous_media_quotes)

    def _update_notion_page(self, quote):
        """Internal method to update Notion page (wrapped with retry)"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
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
        
        quote_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'Daily Quote' in block['callout']['rich_text'][0].get('plain_text', '')):
                quote_block_id = block['id']
                break
        
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
            update_url = f"https://api.notion.com/v1/blocks/{quote_block_id}"
            response = requests.patch(update_url, headers=headers, json=new_block, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to update quote: HTTP {response.status_code}")
            return "updated"
        else:
            create_url = f"https://api.notion.com/v1/blocks/{self.page_id}/children"
            payload = {"children": [new_block]}
            response = requests.patch(create_url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                raise Exception(f"Failed to create quote: HTTP {response.status_code}")
            return "created"

    def update_notion_page(self, quote):
        """Update quote with retry logic"""
        try:
            print("📝 Updating Notion page with authentic media quote...")
            action = self.notion_retry(self._update_notion_page, quote)
            print(f"   ✅ Successfully {action} quote block!")
        except Exception as e:
            print(f"❌ Failed to update Notion after retries: {str(e)}")

    def run(self):
        """Main execution function"""
        print(f"✨ Authentic Media Quote Generator (All Media)")
        print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay\n")
        
        print("🎯 Analyzing ALL media consumption...")
        all_media = self.get_all_media_consumption()
        
        if all_media:
            print(f"📊 Found {len(all_media)} total media items:")
            for item in all_media[:5]:
                status = item.get('context', {}).get('status', 'Unknown')
                print(f"   • {item['name']} ({item['type']}) - {status}")
        else:
            print("📊 No media found - using general authentic quotes")
        
        print("\n🤖 Finding authentic quote from media library...")
        quote = self.generate_media_inspired_quote(all_media)
        print(f"   Selected quote: {quote[:100]}...")
        
        self.update_notion_page(quote)
        print(f"\n✅ Process completed at: {datetime.now().strftime('%H:%M:%S IST')}")

if __name__ == "__main__":
    generator = MediaInspiredQuoteGenerator()
    generator.run()
