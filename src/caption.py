import random
import requests
from src.config import AIRTABLE_FIELD_NAME, OPENROUTER_API_KEY, FALLBACK_MODELS, HOMECARTEL_FOOTER


def generate_short_caption(image_info):
    """Generate a single short catchy AI caption line via OpenRouter."""
    fields = image_info.get("fields", {})
    filename = image_info.get("filename", "image")

    # Build product context from Airtable fields
    context_parts = []
    for key, val in fields.items():
        if key == AIRTABLE_FIELD_NAME:
            continue
        if isinstance(val, str) and val.strip():
            context_parts.append(f"{key}: {val}")

    # Get item names for extra context
    item_names = get_item_names(fields)
    if item_names:
        context_parts.insert(0, f"Product names: {item_names}")

    context = "\n".join(context_parts) if context_parts else f"Image filename: {filename}"

    # Randomize mood for variety
    moods = ["cozy", "dramatic", "serene", "bold", "romantic", "luxurious",
             "playful", "elegant", "sophisticated", "warm", "edgy", "dreamy",
             "refined", "striking", "inviting", "chic", "timeless", "modern"]
    mood = random.choice(moods)

    # Randomize caption style for even more variety
    styles = [
        "poetic and evocative",
        "punchy and confident",
        "soft and inviting",
        "witty with a clever twist",
        "architectural and design-focused",
        "lifestyle and aspirational",
    ]
    style = random.choice(styles)

    prompt = f"""You are a creative copywriter for HomeCartel, a premium lighting and home furniture brand in the Philippines.

PRODUCT DETAILS FROM OUR DATABASE:
{context}

YOUR TASK:
Write ONE short Facebook caption (3-6 words max) for this specific product.

REQUIREMENTS:
- Mood to convey: {mood}
- Writing style: {style}
- The caption MUST reference something specific about THIS product — its material, shape, color, texture, design style, or the feeling it creates
- Add ONE emoji at the end that matches the mood
- Output ONLY the caption line — no explanation, no quotes, no hashtags

BANNED PHRASES (never use these):
"Light up your space", "Illuminate your world", "Brighten your home", "Shine bright", "Glow up", "Golden glow"

EXAMPLES OF GREAT CAPTIONS:
- Brass curves, warm soul. ✨
- Rattan dreams, island charm. 🌿
- Midnight drama, crystal edge. 🌙
- Marble meets soft radiance. 💎
- Industrial chic, redefined. 🔥
- Woven warmth for evenings. 🏝️
- Sleek lines, bold presence. 🖤
- Sculpted shadows, pure art. 🎨

YOUR CAPTION:"""

    # Try each model until one works (handles rate limits)
    for model in FALLBACK_MODELS:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 50,
                    "temperature": 1.0,
                    "top_p": 0.95,
                },
                timeout=30,
            )
            data = resp.json()
            if "choices" in data:
                content = data["choices"][0]["message"].get("content", "")
                if content:
                    content = content.strip().strip('"').strip("'").split("\n")[0].strip()
                    if content:
                        print(f"  Caption generated using: {model}")
                        return content
            # If rate limited or error, try next model
            print(f"  Model {model} failed, trying next...")
        except Exception:
            continue

    return "Timeless design, crafted beauty. ✨"


def get_item_names(fields):
    """Build item names string from Airtable fields."""
    name1 = fields.get("Item Name from File", "")
    name2 = fields.get("Item Name from File2", "")

    if isinstance(name1, list):
        name1 = ", ".join(str(x) for x in name1)
    if isinstance(name2, list):
        name2 = ", ".join(str(x) for x in name2)

    name1 = str(name1).strip() if name1 else ""
    name2 = str(name2).strip() if name2 else ""

    parts = [n for n in [name1, name2] if n]
    return "\n".join(parts)


def compose_caption(ai_line, item_names):
    """Compose the full caption from AI line + item names + footer."""
    sections = [ai_line]
    if item_names:
        sections.append(item_names)
    sections.append(HOMECARTEL_FOOTER)
    return "\n\n".join(sections)
