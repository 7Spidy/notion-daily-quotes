def select_random_two(self, all_media):
    """Select 2 random items from media pool (CHANGED FROM 3)"""
    if len(all_media) < 2:
        print(f"   ⚠️ Only {len(all_media)} items available, using all")
        return all_media
    
    selected = random.sample(all_media, 2)  # CHANGED: Select only 2
    return selected

def generate_content_remix_synthesis(self, two_media):
    """Generate synthesis using GPT-5 with Responses API (UPDATED FOR 2 ITEMS)"""
    
    if not two_media:
        return self.get_fallback_synthesis()
    
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
    
    # Construct prompt for GPT-5 (UPDATED FOR 2 ITEMS)
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
        
        # GPT-5 Responses API call with medium reasoning
        response = self.openai_client.responses.create(
            model="gpt-5",
            input=synthesis_prompt,
            reasoning={"effort": "medium"},
            text={"verbosity": "medium"}
        )
        
        synthesis = response.output_text.strip()
        
        print("   ✅ GPT-5 synthesis generated successfully")
        return synthesis
        
    except Exception as e:
        print(f"   ❌ GPT-5 API error: {e}")
        return self.get_fallback_synthesis()

def get_fallback_synthesis(self):
    """Fallback synthesis if API fails (UPDATED FOR CLEANER FORMAT)"""
    fallbacks = [
        """Every story we consume teaches us about resilience, creativity, and the human experience. They push us to think differently and challenge our perspectives.

What's one lesson from your recent media consumption that you can apply to a real challenge you're facing today?""",
        
        """The narratives we engage with shape how we see the world. Movies inspire us emotionally, books expand our thinking, and games teach us strategic problem-solving.

Which medium has influenced your thinking the most recently, and why?"""
    ]
    
    return random.choice(fallbacks)

def _update_notion_page(self, synthesis, two_media):
    """Update Notion page with Content Remix Summary (NO LABELS)"""
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
    
    # Find existing synthesis block
    synthesis_block_id = None
    for block in blocks.get('results', []):
        if (block['type'] == 'callout' and 
            block.get('callout', {}).get('rich_text') and
            len(block['callout']['rich_text']) > 0 and
            'Content Remix' in block['callout']['rich_text'][0].get('plain_text', '')):
            synthesis_block_id = block['id']
            break
    
    # Build sources list (without label)
    sources = []
    for media in two_media:
        sources.append(f"• {media['name']} ({media['type']})")
    sources_text = "\n".join(sources)
    
    # Build content (NO SECTION LABELS)
    synthesis_content = f"""🎨 Content Remix - {current_date}

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

def update_notion_page(self, synthesis, two_media):
    """Update synthesis with retry logic (UPDATED PARAMETER NAME)"""
    try:
        print("📝 Updating Notion page with Content Remix...")
        action = self.notion_retry(self._update_notion_page, synthesis, two_media)
        print(f"   ✅ Successfully {action} synthesis block!")
    except Exception as e:
        print(f"❌ Failed to update Notion after retries: {str(e)}")

def run(self):
    """Main execution function (UPDATED FOR 2 ITEMS)"""
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
        two_media = []
    else:
        print(f"📊 Found {len(all_media)} total items across all databases\n")
        
        print("🎲 Selecting 2 random items for synthesis...")
        two_media = self.select_random_two(all_media)  # CHANGED TO 2
        
        for i, media in enumerate(two_media, 1):
            print(f"   {i}. {media['name']} ({media['type']}) - {media['context'].get('status', 'Unknown')}")
        
        print("\n🔍 Generating AI synthesis...")
        synthesis = self.generate_content_remix_synthesis(two_media)
    
    print(f"\n📄 Generated Synthesis Preview:")
    print(f"   {synthesis[:100]}...\n")
    
    self.update_notion_page(synthesis, two_media)
    print(f"\n✅ Content Remix generation completed at: {self.get_current_ist_time()}")
