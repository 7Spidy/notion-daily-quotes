def generate_content_remix_synthesis(self, two_media):
    """Generate synthesis using GPT-5 with Responses API - BOLD sources in text"""
    
    if not two_media:
        print("   ⚠️ No media provided, using fallback")
        return self.get_fallback_synthesis()
    
    # Extract just the media names for the prompt
    media_names = [media['name'] for media in two_media]
    
    # Build context strings for each media item
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
5. CRITICAL: Start your synthesis by mentioning BOTH content titles naturally in the first sentence or two (e.g., "Moneyball shows... Baramulla reveals..."). Do NOT use bold formatting or asterisks - write plain text only.
6. Do NOT add any section labels or headers.

Write your response as continuous prose followed by the actionable question on a new line."""

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
        
        # POST-PROCESSING: Make first occurrence of each media name BOLD
        for media in two_media:
            media_name = media['name']
            # Only bold the FIRST occurrence
            if media_name in synthesis:
                synthesis = synthesis.replace(media_name, f"**{media_name}**", 1)
        
        print("   ✅ GPT-5 synthesis generated successfully")
        print(f"      Preview: {synthesis[:100]}...")
        return synthesis
        
    except Exception as e:
        print(f"   ❌ GPT-5 API error: {e}")
        print(f"      Full traceback: {traceback.format_exc()}")
        print(f"   🔄 Using fallback synthesis")
        return self.get_fallback_synthesis()

def _update_notion_page(self, synthesis, two_media):
    """Update Notion page with Content Remix Summary - NO SOURCE LIST"""
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
    
    # Build content WITHOUT source list - just header and synthesis
    synthesis_content = f"🎨 Content Remix - {current_date}\n\n{synthesis}"
    
    print(f"      → Content preview: {synthesis_content[:100]}...")
    
    # Convert markdown bold (**text**) to Notion rich text format
    rich_text_blocks = self._parse_markdown_to_notion_rich_text(synthesis_content)
    
    new_block = {
        "callout": {
            "rich_text": rich_text_blocks,
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

def _parse_markdown_to_notion_rich_text(self, text):
    """Convert markdown bold (**text**) to Notion rich text format"""
    import re
    
    rich_text_blocks = []
    
    # Split by **bold** patterns
    parts = re.split(r'(\*\*[^*]+\*\*)', text)
    
    for part in parts:
        if not part:
            continue
            
        # Check if this part is bold
        if part.startswith('**') and part.endswith('**'):
            # Remove the ** markers and make it bold
            clean_text = part[2:-2]
            rich_text_blocks.append({
                "type": "text",
                "text": {
                    "content": clean_text
                },
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
            # Regular text
            rich_text_blocks.append({
                "type": "text",
                "text": {
                    "content": part
                },
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
