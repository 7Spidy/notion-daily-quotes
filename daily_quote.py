import openai
import requests
import json
import os
from datetime import datetime

def generate_daily_quote():
    """Generate a personalized daily quote using OpenAI"""
    current_date = datetime.now().strftime("%B %d, %Y")
    
    prompt = f"""
    Generate an inspiring and thoughtful quote for {current_date}. 
    
    Consider that this is for someone who is:
    - Interested in AI development and technology
    - Enjoys gaming and strategic thinking
    - Values personal growth and productivity
    - Appreciates travel and new experiences
    - Focused on knowledge management and learning
    
    The quote should be:
    - Motivational but not cliché
    - Relevant to personal development
    - Either original or from a notable thinker/leader
    - Include attribution if from someone else
    - Max 2 sentences
    
    Format: "Quote text" - Author (or "Daily Reflection" if original)
    """
    
    try:
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a thoughtful quote curator who creates meaningful daily inspiration."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.8
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        return f'"Today is a new opportunity to grow and learn." - Daily Reflection'

def update_notion_page(quote):
    """Update the specific section in your Notion page"""
    current_date = datetime.now().strftime("%B %d, %Y")
    
    notion_token = os.getenv('NOTION_API_KEY')
    page_id = os.getenv('NOTION_PAGE_ID')
    
    # Get current page blocks
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    try:
        # Get page blocks
        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        response = requests.get(blocks_url, headers=headers)
        blocks = response.json()
        
        # Look for existing quote block
        quote_block_id = None
        for block in blocks.get('results', []):
            if (block['type'] == 'callout' and 
                block.get('callout', {}).get('rich_text') and
                len(block['callout']['rich_text']) > 0 and
                'Daily Quote' in block['callout']['rich_text'][0].get('plain_text', '')):
                quote_block_id = block['id']
                break
        
        # Prepare the new content
        quote_content = f"🌟 Daily Quote - {current_date}\n\n{quote}"
        
        new_block_data = {
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
            response = requests.patch(update_url, headers=headers, json=new_block_data)
            print(f"Updated existing quote block: {quote}")
        else:
            # Create new block at the beginning
            create_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
            payload = {"children": [new_block_data]}
            response = requests.patch(create_url, headers=headers, json=payload)
            print(f"Created new quote block: {quote}")
            
        if response.status_code in [200, 201]:
            print("Successfully updated Notion page!")
        else:
            print(f"Error updating Notion: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Error updating Notion: {str(e)}")

def main():
    """Main function to generate and update daily quote"""
    print(f"Generating daily quote for {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Generate quote
    quote = generate_daily_quote()
    print(f"Generated quote: {quote}")
    
    # Update Notion page
    update_notion_page(quote)
    print("Daily quote process completed!")

if __name__ == "__main__":
    main()
