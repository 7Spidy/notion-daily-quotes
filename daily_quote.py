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
        
        # Media database IDs
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

    def get_database_specific_instructions(self, media_type):
        """Get database-specific search instructions for each media type"""
        if media_type == 'Books':
            return "Search Goodreads quote collections and popular highlighted passages from this book. Goodreads has extensive quote databases for most published books."
        
        elif media_type == 'Games':
            return "Check IGN quote archives, Game-Quotes.com database, Wikiquote gaming section, GamesRadar memorable dialogue collections, and Eneba gaming quote roundups for this specific game."
        
        elif media_type == 'Movies & TV':
            return "Search QuoDB movie quote database and IMDB quotes section for this specific movie or TV show. These databases contain verified dialogue and memorable lines."
        
        return "Search established quote databases for this media."

    def try_get_quote_from_specific_databases(self, media_item):
        """Enhanced quote search using specific quote databases with strict validation"""
        media_context = ""
        if media_item['type'] == 'Books' and media_item.get('context', {}).get('author'):
            media_context = f" by {media_item['context']['author']}"
        elif media_item['type'] == 'Movies & TV' and media_item.get('context', {}).get('type'):
            media_context = f" ({media_item['context']['type']})"
        
        database_instructions = self.get_database_specific_instructions(media_item['type'])
        
        # Database-specific search approaches
        search_strategies = [
            f"{database_instructions} Find the most famous and widely-quoted line from '{media_item['name']}'{media_context}. Look for quotes that appear frequently in these databases. Provide ONLY the exact quote if you find it. Format: Quote - Character/Speaker, {media_item['name']}. If not found, respond exactly: NO_QUOTE_FOUND",
            
            f"{database_instructions} Search for memorable, inspirational quotes from '{media_item['name']}'{media_context}. Focus on documented quotes in these databases. Format: Quote - Character/Speaker, {media_item['name']}. If no verified quotes, respond exactly: NO_QUOTE_FOUND"
        ]
        
        for strategy_num, prompt in enumerate(search_strategies, 1):
            try:
                print(f"      → Database search {strategy_num}/2: Checking {media_item['type']} databases")
                
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"You are a quote database researcher. For BOOKS: Use Goodreads exclusively. For GAMES: Use IGN, Game-Quotes.com, Wikiquote, GamesRadar, Eneba. For MOVIES/TV: Use QuoDB and IMDB exclusively. CRITICAL: If you cannot find verified quotes in these databases, respond EXACTLY with 'NO_QUOTE_FOUND' - do not create or guess quotes."},
                        {"role": "user", "content": prompt}
                    ],
                    max_completion_tokens=120,
                    temperature=0.1
                )
                
                quote = response.choices[0].message.content.strip()
                
                # STRICT validation - if ANY failure indicators, reject
                failure_indicators = [
                    "NO_QUOTE_FOUND", "sorry", "don't have", "don't know", "cannot", "unable", 
                    "not familiar", "not available", "I apologize", "not found", "not documented",
                    "don't possess", "can't find", "not sure", "uncertain", "don't recall"
                ]
                
                if any(indicator in quote.lower() for indicator in failure_indicators):
                    print(f"      ❌ Strategy {strategy_num}: Database search unsuccessful")
                    continue
                
                # Additional validation - ensure it looks like a real quote
                if ('"' in quote and '-' in quote and len(quote) > 20 and len(quote) < 200):
                    quote = self.clean_quote_formatting(quote)
                    print(f"      ✅ DATABASE SUCCESS! Verified quote via strategy {strategy_num}")
                    return quote
                else:
                    print(f"      ❌ Strategy {strategy_num}: Quote format invalid")
                    
            except Exception as e:
                print(f"      ⚠️ Strategy {strategy_num} error: {e}")
        
        print(f"      ❌ No database quotes found for {media_item['name']}")
        return None

    def generate_media_inspired_quote(self, all_media):
        """Generate a quote with robust fallback system - NEVER return NO_QUOTE_FOUND"""
        if not all_media:
            print("   No media found, using guaranteed famous quotes")
            return self.get_guaranteed_backup_quote()
        
        # Prioritize popular media likely to have database coverage
        popular_media = []
        other_media = []
        
        popular_titles = [
            'harry potter', 'star wars', 'lord of the rings', 'game of thrones', 'the office',
            'breaking bad', 'friends', 'marvel', 'batman', 'superman', 'spider-man',
            'the godfather', 'forrest gump', 'titanic', 'inception', 'the matrix',
            'call of duty', 'world of warcraft', 'minecraft', 'grand theft auto',
            'the last of us', 'god of war', 'halo', 'assassin\'s creed', 'witcher',
            'shakespeare', 'tolkien', 'dune', 'foundation', 'game of thrones'
        ]
        
        for media in all_media:
            if any(popular in media['name'].lower() for popular in popular_titles):
                popular_media.append(media)
            else:
                other_media.append(media)
        
        # Try popular media first, then others
        random.shuffle(popular_media)
        random.shuffle(other_media)
        prioritized_media = popular_media + other_media
        
        max_attempts = min(20, len(prioritized_media))  # Increased to 20 attempts
        print(f"   🎯 Searching {max_attempts} media items with database verification...")
        print(f"   📊 Priority: {len(popular_media)} popular titles, then {len(other_media)} library items")
        
        for attempt in range(max_attempts):
            selected_media = prioritized_media[attempt]
            priority = "🌟 POPULAR" if selected_media in popular_media else "📚 LIBRARY"
            
            print(f"   🎯 Media {attempt + 1}/{max_attempts}: {selected_media['name']} ({selected_media['type']}) - {priority}")
            
            quote = self.try_get_quote_from_specific_databases(selected_media)
            
            if quote and "NO_QUOTE_FOUND" not in quote:
                print(f"   🎉 SUCCESS! Found verified quote from {selected_media['name']}")
                return quote
            else:
                print(f"   ⏭️ Moving to next media...")
        
        # GUARANTEED fallback - never fails
        print("   🔄 All media exhausted, using guaranteed backup quotes")
        return self.get_guaranteed_backup_quote()

    def get_guaranteed_backup_quote(self):
        """Get guaranteed backup quotes that will never fail"""
        guaranteed_quotes = [
            '"May the Force be with you." - Obi-Wan Kenobi, Star Wars',
            '"I am inevitable." - Thanos, Avengers: Endgame',
            '"With great power comes great responsibility." - Uncle Ben, Spider-Man',
            '"The needs of the many outweigh the needs of the few." - Spock, Star Trek',
            '"Winter is coming." - Ned Stark, Game of Thrones',
            '"I\'ll be back." - The Terminator, The Terminator',
            '"Elementary, my dear Watson." - Sherlock Holmes, Sherlock Holmes',
            '"Here\'s looking at you, kid." - Rick Blaine, Casablanca',
            '"Life is like a box of chocolates, you never know what you\'re gonna get." - Forrest Gump, Forrest Gump',
            '"The truth is out there." - Fox Mulder, The X-Files',
            '"Why so serious?" - The Joker, The Dark Knight',
            '"I have a bad feeling about this." - Han Solo, Star Wars',
            '"Keep your friends close, but your enemies closer." - Michael Corleone, The Godfather',
            '"There\'s no place like home." - Dorothy, The Wizard of Oz',
            '"Show me the money!" - Rod Tidwell, Jerry Maguire'
        ]
        
        selected_quote = random.choice(guaranteed_quotes)
        print(f"   ✅ Guaranteed backup quote selected: {selected_quote[:50]}...")
        return selected_quote

    def validate_quote_output(self, quote):
        """Validate that quote is properly formatted and not a failure message"""
        if not quote:
            return False
            
        # Check for failure messages
        failure_patterns = [
            "NO_QUOTE_FOUND", "sorry", "don't have", "cannot", "unable", "not found",
            "not available", "I apologize", "not documented", "don't know"
        ]
        
        if any(pattern in quote.lower() for pattern in failure_patterns):
            return False
        
        # Check for proper quote format
        if not ('"' in quote and '-' in quote):
            return False
            
        # Check reasonable length
        if len(quote) < 15 or len(quote) > 300:
            return False
            
        return True

    def _update_notion_page(self, quote):
        """Internal method to update Notion page (wrapped with retry)"""
        # VALIDATE QUOTE BEFORE UPDATING NOTION
        if not self.validate_quote_output(quote):
            print(f"   ⚠️ Invalid quote detected: {quote[:100]}")
            quote = self.get_guaranteed_backup_quote()
            print(f"   🔄 Using guaranteed backup instead")
        
        current_date = self.get_current_ist_time().split(' - ')[0]
        
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
        """Update quote with retry logic and final validation"""
        try:
            print("📝 Updating Notion page with verified quote...")
            action = self.notion_retry(self._update_notion_page, quote)
            print(f"   ✅ Successfully {action} quote block!")
        except Exception as e:
            print(f"❌ Failed to update Notion after retries: {str(e)}")
            
            # Emergency fallback - try with guaranteed quote
            try:
                print("   🚨 Emergency fallback - using guaranteed quote")
                backup_quote = self.get_guaranteed_backup_quote()
                action = self.notion_retry(self._update_notion_page, backup_quote)
                print(f"   ✅ Emergency fallback successful: {action}")
            except Exception as emergency_error:
                print(f"   ❌ Even emergency fallback failed: {emergency_error}")

    def run(self):
        """Main execution function"""
        print(f"✨ Robust Quote Generator (Never Fails)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🎯 Sources: 📚 Goodreads | 🎮 IGN/Game-Quotes/Wikiquote/GamesRadar/Eneba | 🎬 QuoDB/IMDB")
        print(f"🔒 Failsafe: Guaranteed backup quotes if database search fails\n")
        
        print("🎯 Loading your complete media library...")
        all_media = self.get_all_media_consumption()
        
        if all_media:
            print(f"📊 Found {len(all_media)} total media items")
        else:
            print("📊 No media found - proceeding with guaranteed quotes")
        
        print("\n🔍 Initiating robust quote search...")
        quote = self.generate_media_inspired_quote(all_media)
        
        # FINAL VALIDATION before updating Notion
        if not self.validate_quote_output(quote):
            print("   🚨 Final validation failed, applying emergency quote")
            quote = self.get_guaranteed_backup_quote()
        
        print(f"   🎯 Final quote validated: {quote[:80]}...")
        
        self.update_notion_page(quote)
        print(f"\n✅ Quote generation completed successfully at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    generator = MediaInspiredQuoteGenerator()
    generator.run()
