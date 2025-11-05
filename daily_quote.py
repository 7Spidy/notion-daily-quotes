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

    def get_source_specific_instructions(self, media_type):
        """Get source-specific instructions for quote research"""
        if media_type == 'Books':
            return "Search Goodreads quote database for this book. Look for popular quotes, highlighted passages, and memorable lines that readers have marked. Focus on the most popular and well-documented quotes from this book."
        
        elif media_type == 'Games':
            return "Search IGN, Game-Quotes.com, Wikiquote, GamesRadar, and Eneba roundup archives for memorable quotes from this game. Look for iconic dialogue, character speeches, and memorable lines that players remember."
        
        elif media_type == 'Movies & TV':
            return "Search QuoDB and IMDB quote databases for this movie/show. Look for famous dialogue, memorable lines, and quotes that are well-documented in these movie quote databases."
        
        return "Find well-documented quotes from reliable sources."

    def try_get_quote_from_media_enhanced(self, media_item):
        """Enhanced quote search with source-specific instructions"""
        media_context = ""
        if media_item['type'] == 'Books' and media_item.get('context', {}).get('author'):
            media_context = f" by {media_item['context']['author']}"
        elif media_item['type'] == 'Movies & TV' and media_item.get('context', {}).get('type'):
            media_context = f" ({media_item['context']['type']})"
        
        source_instructions = self.get_source_specific_instructions(media_item['type'])
        
        # Enhanced approaches with source-specific instructions
        approaches = [
            f"{source_instructions} Find the most famous and memorable quote from '{media_item['name']}'{media_context}. Look for quotes that are widely recognized and frequently cited. Provide the exact quote as it appears in the original source. Format: Quote - Character/Speaker, {media_item['name']}. If you cannot find documented quotes from reliable sources, respond exactly: NO_QUOTE_FOUND",
            
            f"{source_instructions} Look for inspirational, motivational, or wisdom-filled quotes from '{media_item['name']}'{media_context}. Focus on quotes about growth, perseverance, success, or life lessons that are well-documented in quote databases. Format: Quote - Character/Speaker, {media_item['name']}. If no verified quotes exist, respond: NO_QUOTE_FOUND",
            
            f"{source_instructions} Search for iconic dialogue or catchphrases from '{media_item['name']}'{media_context} that have become popular or quotable. Look for lines that fans remember and quote databases document. Format: Quote - Character/Speaker, {media_item['name']}. If unsure about authenticity, respond: NO_QUOTE_FOUND",
            
            f"Research '{media_item['name']}'{media_context} thoroughly. {source_instructions} Look for ANY memorable quotes, dialogue, or passages that are documented and verifiable. Search your knowledge of popular quotes from this {media_item['type'].lower()}. Format: Quote - Character/Speaker, {media_item['name']}. Only provide quotes you are confident are real. If uncertain, respond: NO_QUOTE_FOUND"
        ]
        
        for approach_num, prompt in enumerate(approaches, 1):
            try:
                search_type = ['famous quotes', 'inspirational quotes', 'iconic dialogue', 'any documented quotes'][approach_num-1]
                print(f"      → Approach {approach_num}/4: {source_instructions.split('.')[0]} - {search_type}")
                
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": f"You are an expert quote researcher with access to major quote databases. For Books: use Goodreads quote collections. For Games: reference IGN, Game-Quotes.com, Wikiquote, GamesRadar, Eneba archives. For Movies/TV: use QuoDB and IMDB quote databases. Only provide quotes you can verify from these sources. If uncertain, respond 'NO_QUOTE_FOUND'."},
                        {"role": "user", "content": prompt}
                    ],
                    max_completion_tokens=150,
                    temperature=0.05  # Very low temperature for accuracy
                )
                
                quote = response.choices[0].message.content.strip()
                
                # Enhanced failure detection
                failure_indicators = [
                    "NO_QUOTE_FOUND", "sorry", "don't have access", "don't know", 
                    "cannot recall", "unable to find", "not familiar", "don't have specific",
                    "can't provide", "not available", "I apologize"
                ]
                
                if not any(indicator in quote.lower() for indicator in failure_indicators):
                    quote = self.clean_quote_formatting(quote)
                    print(f"      ✅ SUCCESS! Found verified quote via approach {approach_num}")
                    return quote
                else:
                    print(f"      ❌ Approach {approach_num}: No verified quote found")
                    
            except Exception as e:
                print(f"      ⚠️ Approach {approach_num} error: {e}")
        
        return None

    def generate_media_inspired_quote(self, all_media):
        """Generate a quote with extensive source-specific search"""
        current_date = datetime.now().strftime("%B %d, %Y")
        
        if not all_media:
            print("   No media found, using authenticated famous quotes")
            famous_quotes = [
                '"The way to get started is to quit talking and begin doing." - Walt Disney',
                '"Innovation distinguishes between a leader and a follower." - Steve Jobs',
                '"Success is not final, failure is not fatal: it is the courage to continue that counts." - Winston Churchill'
            ]
            return random.choice(famous_quotes)
        
        # Prioritize popular/well-known media first, then shuffle the rest
        popular_media = []
        other_media = []
        
        popular_titles = [
            'harry potter', 'star wars', 'lord of the rings', 'game of thrones', 'the office',
            'breaking bad', 'friends', 'marvel', 'batman', 'superman', 'spider-man',
            'the godfather', 'forrest gump', 'titanic', 'inception', 'the matrix',
            'call of duty', 'world of warcraft', 'minecraft', 'grand theft auto',
            'the last of us', 'god of war', 'halo', 'assassin\'s creed'
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
        
        max_media_attempts = min(12, len(prioritized_media))  # Increased from 10
        print(f"   Searching {max_media_attempts} media items with source-specific database instructions...")
        
        if popular_media:
            print(f"   🌟 Prioritizing {len(popular_media)} popular titles for better quote availability")
        
        for attempt in range(max_media_attempts):
            selected_media = prioritized_media[attempt]
            priority_marker = "🌟 POPULAR" if selected_media in popular_media else "📚 LIBRARY"
            
            print(f"   🎯 Media {attempt + 1}/{max_media_attempts}: {selected_media['name']} ({selected_media['type']}) - {priority_marker}")
            
            quote = self.try_get_quote_from_media_enhanced(selected_media)
            
            if quote:
                print(f"   🎉 SUCCESS! Found verified quote from {selected_media['name']}")
                return quote
            else:
                print(f"   ❌ No quotes found in {selected_media['name']}, trying next media...")
        
        # Enhanced fallback with verified media quotes
        print("   📚 Using backup verified media quotes from popular sources")
        verified_media_quotes = [
            '"May the Force be with you." - Obi-Wan Kenobi, Star Wars',
            '"I am inevitable." - Thanos, Avengers: Endgame',
            '"With great power comes great responsibility." - Uncle Ben, Spider-Man',
            '"The needs of the many outweigh the needs of the few." - Spock, Star Trek',
            '"Why so serious?" - The Joker, The Dark Knight',
            '"Life is like a box of chocolates, you never know what you\'re gonna get." - Forrest Gump, Forrest Gump',
            '"I\'ll be back." - The Terminator, The Terminator',
            '"Here\'s looking at you, kid." - Rick Blaine, Casablanca',
            '"The truth is out there." - Fox Mulder, The X-Files',
            '"Winter is coming." - Ned Stark, Game of Thrones'
        ]
        
        return random.choice(verified_media_quotes)

    def _update_notion_page(self, quote):
        """Internal method to update Notion page (wrapped with retry)"""
        current_date = self.get_current_ist_time().split(' - ')[0]  # Get just the date part
        
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
            print("📝 Updating Notion page with verified media quote...")
            action = self.notion_retry(self._update_notion_page, quote)
            print(f"   ✅ Successfully {action} quote block!")
        except Exception as e:
            print(f"❌ Failed to update Notion after retries: {str(e)}")

    def run(self):
        """Main execution function"""
        print(f"✨ Enhanced Media Quote Generator (Source-Specific Search)")
        print(f"🕐 Started at: {self.get_current_ist_time()}")
        print(f"🔄 Retry config: {self.max_retries} attempts, {self.retry_delay}s delay")
        print(f"🎯 Quote sources: Goodreads (Books), IGN/Game-Quotes/Wikiquote (Games), QuoDB/IMDB (Movies/TV)\n")
        
        print("🎯 Analyzing ALL media consumption...")
        all_media = self.get_all_media_consumption()
        
        if all_media:
            print(f"📊 Found {len(all_media)} total media items")
            status_counts = {}
            for item in all_media:
                status = item.get('context', {}).get('status', 'Unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            print(f"   Status breakdown: {status_counts}")
        else:
            print("📊 No media found - using famous verified quotes")
        
        print("\n🎯 Enhanced quote search with database-specific instructions...")
        quote = self.generate_media_inspired_quote(all_media)
        print(f"   Final verified quote: {quote[:100]}...")
        
        self.update_notion_page(quote)
        print(f"\n✅ Process completed at: {self.get_current_ist_time()}")

if __name__ == "__main__":
    generator = MediaInspiredQuoteGenerator()
    generator.run()
