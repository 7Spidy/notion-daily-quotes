import openai
import requests
import json
import os
from datetime import datetime, timezone, timedelta
import time
import random

class MediaInspiredQuoteGenerator:
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.notion_token = os.getenv('NOTION_API_KEY')
        self.page_id = os.getenv('NOTION_PAGE_ID')
        
        self.movies_db_id = os.getenv('MOVIES_DB_ID')
        self.books_db_id = os.getenv('BOOKS_DB_ID')
        self.games_db_id = os.getenv('GAMES_DB_ID')
        
        self.max_retries = 3
        self.retry_delay = 2

    def get_current_ist_time(self):
        """Get current IST time"""
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        return now_ist.strftime("%A, %B %d, %Y - %I:%M %p IST")

    def notion_retry(self, func, *args, **kwargs):
        """Retry wrapper"""
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
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ All attempts failed: {str(e)}")
                    raise e

    def _query_media_database(self, db_id, media_type):
        """Query media database"""
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        response = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", 
                                headers=headers, json={"page_size": 50}, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"{media_type} query failed: {response.status_code}")
            
        media_items = []
        for item in response.json().get('results', []):
            try:
                name = 'Untitled'
                if 'Name' in item['properties'] and item['properties']['Name']['title']:
                    name = item['properties']['Name']['title'][0]['plain_text']
                
                status = 'Unknown'
                if 'Status' in item['properties'] and item['properties']['Status']['status']:
                    status = item['properties']['Status']['status']['name']
                
                context = {'status': status}
                
                if media_type == 'Books' and 'Author' in item['properties']:
                    if item['properties']['Author']['multi_select']:
                        context['author'] = item['properties']['Author']['multi_select'][0]['name']
                
                media_items.append({'name': name, 'type': media_type, 'context': context})
            except:
                pass
        
        return media_items

    def get_all_media_consumption(self):
        """Get all media"""
        all_media = []
        
        for db_id, media_type in [(self.movies_db_id, "Movies & TV"), 
                                    (self.books_db_id, "Books"), 
                                    (self.games_db_id, "Games")]:
            if db_id:
                try:
                    print(f"🎯 Getting {media_type}...")
                    media = self.notion_retry(self._query_media_database, db_id, media_type)
                    all_media.extend(media)
                    print(f"   Found {len(media)} items")
                except Exception as e:
                    print(f"   ❌ {media_type} error: {e}")
        
        return all_media

    def clean_quote_formatting(self, quote):
        """Clean quote formatting"""
        import re
        quote = re.sub(r'\*([^*]+)\*', r'\1', quote)
        quote = re.sub(r'\s+', ' ', quote)
        return quote.strip()

    def get_database_instructions(self, media_type):
        """Get database-specific instructions"""
        instructions = {
            'Books': "Search Goodreads quote collections for this book.",
            'Games': "Check IGN, Game-Quotes.com, Wikiquote, GamesRadar, Eneba for this game.",
            'Movies & TV': "Search QuoDB and IMDB quote databases for this content."
        }
        return instructions.get(media_type, "Search quote databases.")

    def try_get_quote_from_databases(self, media_item):
        """Get quote using GPT-5.1 Responses API"""
        media_context = ""
        if media_item['type'] == 'Books' and media_item.get('context', {}).get('author'):
            media_context = f" by {media_item['context']['author']}"
        
        db_instructions = self.get_database_instructions(media_item['type'])
        
        strategies = [
            f"{db_instructions} Find famous quote from '{media_item['name']}'{media_context}. Format: Quote - Character, {media_item['name']}. If not found: NO_QUOTE_FOUND",
            f"{db_instructions} Find memorable quote from '{media_item['name']}'{media_context}. Format: Quote - Character, {media_item['name']}. If none: NO_QUOTE_FOUND"
        ]
        
        for strategy_num, prompt in enumerate(strategies, 1):
            try:
                print(f"      → GPT-5.1 search {strategy_num}/2")
                
                # Use Responses API for GPT-5.1
                response = self.openai_client.responses.create(
                    model="gpt-5.1",
                    input=f"For BOOKS: Use Goodreads. For GAMES: Use IGN, Game-Quotes.com, Wikiquote, GamesRadar, Eneba. For MOVIES/TV: Use QuoDB and IMDB. {prompt}",
                    reasoning={"effort": "none"},  # Fast, low-latency responses
                    text={"verbosity": "low"},  # Concise output
                    max_output_tokens=120
                )
                
                quote = response.output_text.strip()
                
                failure_indicators = [
                    "NO_QUOTE_FOUND", "sorry", "don't have", "cannot", "unable",
                    "not found", "not available", "I apologize", "not documented"
                ]
                
                if any(indicator in quote.lower() for indicator in failure_indicators):
                    print(f"      ❌ Strategy {strategy_num}: No quote")
                    continue
                
                if '"' in quote and '-' in quote and 20 < len(quote) < 200:
                    quote = self.clean_quote_formatting(quote)
                    print(f"      ✅ GPT-5.1 SUCCESS!")
                    return quote
                else:
                    print(f"      ❌ Strategy {strategy_num}: Invalid format")
                    
            except Exception as e:
                print(f"      ⚠️ Strategy {strategy_num} error: {e}")
        
        return None

    def generate_media_inspired_quote(self, all_media):
        """Generate quote with fallback"""
        if not all_media:
            return self.get_guaranteed_backup_quote()
        
        popular_titles = [
            'harry potter', 'star wars', 'lord of the rings', 'game of thrones',
            'breaking bad', 'friends', 'marvel', 'spider-man', 'the godfather',
            'inception', 'the matrix', 'minecraft', 'the last of us', 'witcher'
        ]
        
        popular = [m for m in all_media if any(p in m['name'].lower() for p in popular_titles)]
        other = [m for m in all_media if m not in popular]
        
        random.shuffle(popular)
        random.shuffle(other)
        prioritized = popular + other
        
        max_attempts = min(20, len(prioritized))
        print(f"   🎯 GPT-5.1 searching {max_attempts} media items...")
        
        for attempt in range(max_attempts):
            selected = prioritized[attempt]
            priority = "🌟 POPULAR" if selected in popular else "📚 LIBRARY"
            print(f"   Media {attempt + 1}/{max_attempts}: {selected['name']} - {priority}")
            
            quote = self.try_get_quote_from_databases(selected)
            
            if quote and "NO_QUOTE_FOUND" not in quote:
                print(f"   🎉 GPT-5.1 SUCCESS from {selected['name']}")
                return quote
            else:
                print(f"   ⏭️ Next...")
        
        print("   🔄 Using guaranteed backup")
        return self.get_guaranteed_backup_quote()

    def get_guaranteed_backup_quote(self):
        """Guaranteed backup quotes"""
        quotes = [
            '"May the Force be with you." - Obi-Wan Kenobi, Star Wars',
            '"With great power comes great responsibility." - Uncle Ben, Spider-Man',
            '"Winter is coming." - Ned Stark, Game of Thrones',
            '"I\'ll be back." - The Terminator, The Terminator',
            '"Life is like a box of chocolates." - Forrest Gump, Forrest Gump',
            '"The truth is out there." - Fox Mulder, The X-Files',
            '"Why so serious?" - The Joker, The Dark Knight',
            '"Show me the money!" - Rod Tidwell, Jerry Maguire'
        ]
        return random.choice(quotes)

    def validate_quote(self, quote):
        """Validate quote"""
        if not quote or len(quote) < 15 or len(quote) > 300:
            return False
        if any(p in quote.lower() for p in ["NO_QUOTE_FOUND", "sorry", "cannot"]):
            return False
        return '"' in quote and '-' in quote

    def _update_notion_page(self, quote):
        """Update Notion page"""
        if not self.validate_quote(quote):
            print(f"   ⚠️ Invalid quote, using backup")
            quote = self.get_guaranteed_backup_quote()
        
        headers = {
            "Authorization": f"Bearer {self.notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        response = requests.get(f"https://api.notion.com/v1/blocks/{self.page_id}/children", 
                               headers=headers, timeout=10)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get blocks: {response.status_code}")
            
        quote_block_id = None
        for block in response.json().get('results', []):
            if (block['type'] == 'callout' and block.get('callout', {}).get('rich_text') and
                'Daily Quote' in block['callout']['rich_text'][0].get('plain_text', '')):
                quote_block_id = block['id']
                break
        
        current_date = self.get_current_ist_time().split(' - ')[0]
        quote_content = f"🌟 Daily Quote - {current_date}\n\n{quote}"
        
        new_block = {
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": quote_content}}],
                "icon": {"emoji": "✨"},
                "color": "blue_background"
            }
        }
        
        if quote_block_id:
            response = requests.patch(f"https://api.notion.com/v1/blocks/{quote_block_id}", 
                                     headers=headers, json=new_block, timeout=10)
            return "updated" if response.status_code == 200 else None
        else:
            response = requests.patch(f"https://api.notion.com/v1/blocks/{self.page_id}/children",
                                     headers=headers, json={"children": [new_block]}, timeout=10)
            return "created" if response.status_code == 200 else None

    def update_notion_page(self, quote):
        """Update with retry"""
        try:
            print("📝 Updating Notion with GPT-5.1 quote...")
            action = self.notion_retry(self._update_notion_page, quote)
            print(f"   ✅ Successfully {action} quote!")
        except Exception as e:
            print(f"❌ Update failed: {str(e)}")

    def run(self):
        """Main execution"""
        print(f"✨ GPT-5.1 Powered Quote Generator (Responses API)")
        print(f"🕐 Started: {self.get_current_ist_time()}")
        print(f"🤖 AI Model: GPT-5.1 (Latest OpenAI Model)")
        print(f"⚡ Reasoning: none (low-latency mode)")
        print(f"📊 Verbosity: low (concise output)\n")
        
        all_media = self.get_all_media_consumption()
        print(f"📊 Total media: {len(all_media)}\n")
        
        print("🔍 GPT-5.1 quote search...")
        quote = self.generate_media_inspired_quote(all_media)
        
        if not self.validate_quote(quote):
            print("   🚨 Final validation failed, using backup")
            quote = self.get_guaranteed_backup_quote()
        
        print(f"   🎯 Final: {quote[:80]}...\n")
        
        self.update_notion_page(quote)
        print(f"✅ Completed: {self.get_current_ist_time()}")

if __name__ == "__main__":
    generator = MediaInspiredQuoteGenerator()
    generator.run()
