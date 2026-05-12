import base64
import json
import os
import random
import re
import threading
import time
from http.client import RemoteDisconnected
from io import BytesIO

import requests
from PIL import Image

from src.config import (
    AIRTABLE_FIELD_NAME,
    OPENROUTER_API_KEY,
    FALLBACK_MODELS,
    HOMECARTEL_FOOTER,
    LMSTUDIO_API_BASE_URL,
    LMSTUDIO_MODEL,
    LMSTUDIO_MAX_TOKENS,
    LMSTUDIO_CONNECT_TIMEOUT,
    LMSTUDIO_READ_TIMEOUT,
    CAPTION_HISTORY_PATH,
    CAPTION_HISTORY_LIMIT,
    CAPTION_HISTORY_PROMPT_LIMIT,
    CAPTION_RETRY_ATTEMPTS,
)

_CAPTION_HISTORY_LOCK = threading.RLock()
_TIP_HISTORY_LOCK = threading.RLock()
TIP_HISTORY_PATH = os.path.join(os.path.dirname(CAPTION_HISTORY_PATH), "tips_reel_history.json")
_FALLBACK_CAPTIONS = [
    "Sculpted calm, softly lit. ✨",
    "Quiet luxury in focus. 🤍",
    "Curves, glow, and poise. ✨",
    "Soft radiance, bold form. 💫",
    "Design that feels serene. 🌙",
    "Texture meets warm mood. 🕯️",
    "A statement in stillness. 🖤",
    "Refined glow, modern soul. ✨",
]

_VIDEO_TIP_FALLBACKS = {
    "lighting": [
        "Use warm light to define the focal area",
        "Let the fixture anchor the room mood",
        "Balance ceiling light with soft surrounding textures",
        "Highlight the fixture with calm neutral styling",
        "Use layered lighting to create visual depth",
        "Match warm illumination with natural room finishes",
    ],
    "seating": [
        "Anchor seating with texture and balanced spacing",
        "Pair soft upholstery with grounded accent pieces",
        "Create a conversation zone around the seating",
        "Use layered textiles to soften the seating area",
        "Balance bold seating with quiet surrounding decor",
    ],
    "surface": [
        "Style surfaces with height and breathing room",
        "Keep tabletop decor layered but visually light",
        "Use mixed heights for a curated surface moment",
        "Pair clean surfaces with warm natural accents",
        "Leave open space so the piece can stand out",
    ],
    "storage": [
        "Let storage pieces frame the room with structure",
        "Balance closed storage with soft decorative accents",
        "Use cabinet lines to create visual order",
        "Style shelves with rhythm, height, and negative space",
    ],
    "general": [
        "Style the focal piece with warm room balance",
        "Repeat natural textures for a cohesive room story",
        "Use negative space to let the design breathe",
        "Balance statement pieces with quieter surrounding details",
        "Ground the room with texture, warmth, and scale",
    ],
}


def _random_caption_style():
    """Return a randomized mood/style pairing for more variety."""
    moods = [
        "cozy", "dramatic", "serene", "bold", "romantic", "luxurious",
        "playful", "elegant", "sophisticated", "warm", "edgy", "dreamy",
        "refined", "striking", "inviting", "chic", "timeless", "modern",
    ]
    styles = [
        "poetic and evocative",
        "punchy and confident",
        "soft and inviting",
        "witty with a clever twist",
        "architectural and design-focused",
        "lifestyle and aspirational",
    ]
    return random.choice(moods), random.choice(styles)


def _clean_caption_output(content):
    """Normalize model output down to a single caption line."""
    if not content:
        return ""
    cleaned = re.sub(r"<\|[^>]+?\|>", "", content)
    cleaned = cleaned.strip().strip('"').strip("'").split("\n")[0].strip()
    return cleaned


def _normalize_caption(content):
    """Collapse formatting so duplicate comparisons are consistent."""
    cleaned = _clean_caption_output(content)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def _extract_chat_content(data):
    """Pull assistant text from an OpenAI-style chat response."""
    try:
        content = data["choices"][0]["message"].get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return content
    except (KeyError, IndexError, TypeError):
        return ""


def _encode_pil_image(img):
    """Resize and base64-encode a PIL image for the local vision model."""
    img = img.convert("RGB")
    max_side = 1024
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _encode_local_image(image_path):
    """Resize and base64-encode an uploaded image for the local vision model."""
    with Image.open(image_path) as img:
        return _encode_pil_image(img)


def _download_image_data_url(url):
    """Download an image URL and return a data URL for LM Studio vision."""
    resp = requests.get(str(url), timeout=(LMSTUDIO_CONNECT_TIMEOUT, 30))
    resp.raise_for_status()
    with Image.open(BytesIO(resp.content)) as img:
        return _encode_pil_image(img)


def _load_caption_history():
    """Load locally stored caption history."""
    with _CAPTION_HISTORY_LOCK:
        if not os.path.exists(CAPTION_HISTORY_PATH):
            return []
        try:
            with open(CAPTION_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except Exception:
            return []
    return []


def _save_caption_history(history):
    """Persist caption history to disk."""
    with _CAPTION_HISTORY_LOCK:
        os.makedirs(os.path.dirname(CAPTION_HISTORY_PATH), exist_ok=True)
        with open(CAPTION_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history[-CAPTION_HISTORY_LIMIT:], f, ensure_ascii=False, indent=2)


def _recent_captions(limit=CAPTION_HISTORY_PROMPT_LIMIT):
    """Return the most recent stored captions for prompt dedupe."""
    history = _load_caption_history()
    return history[-limit:]


def _store_caption(caption):
    """Store a successful caption and dedupe exact repeats in history."""
    cleaned = _clean_caption_output(caption)
    normalized = _normalize_caption(cleaned)
    if not normalized:
        return

    history = _load_caption_history()
    history = [item for item in history if _normalize_caption(item) != normalized]
    history.append(cleaned)
    _save_caption_history(history)


def _is_duplicate_caption(caption, recent_captions):
    """Check whether a caption already exists in the recent history."""
    normalized = _normalize_caption(caption)
    if not normalized:
        return False
    return normalized in {_normalize_caption(item) for item in recent_captions}


def _avoid_recent_prompt_block(recent_captions):
    """Build prompt text that steers the model away from recent outputs."""
    recent = [caption for caption in recent_captions if caption.strip()]
    if not recent:
        return ""

    lines = "\n".join(f"- {caption}" for caption in recent[-CAPTION_HISTORY_PROMPT_LIMIT:])
    return f"""

AVOID REUSING THESE RECENT CAPTIONS:
{lines}

If your draft matches or feels too close to any caption above, rewrite it into a fresh new line before answering."""


def _unique_fallback_caption():
    """Pick a stored-safe fallback caption when the model keeps repeating itself."""
    recent = _recent_captions(limit=CAPTION_HISTORY_LIMIT)
    for caption in _FALLBACK_CAPTIONS:
        if not _is_duplicate_caption(caption, recent):
            _store_caption(caption)
            return caption

    chosen = random.choice(_FALLBACK_CAPTIONS)
    _store_caption(chosen)
    return chosen


def _load_tip_history():
    """Load locally stored Tips Reel overlay text history."""
    with _TIP_HISTORY_LOCK:
        if not os.path.exists(TIP_HISTORY_PATH):
            return []
        try:
            with open(TIP_HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except Exception:
            return []
    return []


def _save_tip_history(history):
    """Persist Tips Reel overlay text history."""
    with _TIP_HISTORY_LOCK:
        os.makedirs(os.path.dirname(TIP_HISTORY_PATH), exist_ok=True)
        with open(TIP_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history[-CAPTION_HISTORY_LIMIT:], f, ensure_ascii=False, indent=2)


def _recent_tips(limit=CAPTION_HISTORY_PROMPT_LIMIT):
    """Return recent Tips Reel lines for prompt dedupe."""
    history = _load_tip_history()
    return history[-limit:]


def _normalize_tip(content):
    """Normalize Tips Reel text for duplicate comparisons."""
    cleaned = _clean_tip_output(content)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def _is_duplicate_tip(tip, recent_tips):
    """Return True when a generated tip repeats recent overlay text."""
    normalized = _normalize_tip(tip)
    if not normalized:
        return False
    return normalized in {_normalize_tip(item) for item in recent_tips}


def _store_tip(tip):
    """Store a successful Tips Reel line and dedupe exact repeats."""
    cleaned = _clean_tip_output(tip)
    normalized = _normalize_tip(cleaned)
    if not normalized:
        return

    history = _load_tip_history()
    history = [item for item in history if _normalize_tip(item) != normalized]
    history.append(cleaned)
    _save_tip_history(history)


def _avoid_recent_tips_prompt_block(recent_tips):
    """Build prompt text that steers the model away from recent Tips Reel lines."""
    recent = [tip for tip in recent_tips if tip.strip()]
    if not recent:
        return ""

    lines = "\n".join(f"- {tip}" for tip in recent[-CAPTION_HISTORY_PROMPT_LIMIT:])
    return f"""

RECENT TIPS TO AVOID:
{lines}

Do not reuse these exact lines or near-identical wording. If your draft sounds similar, write a new tip from another visible detail."""


def _lmstudio_timeout():
    """Return a requests-compatible timeout tuple for LM Studio."""
    return (LMSTUDIO_CONNECT_TIMEOUT, LMSTUDIO_READ_TIMEOUT)


def generate_short_caption(image_info):
    """Generate a single short catchy AI caption line via OpenRouter."""
    fields = image_info.get("fields", {})
    filename = image_info.get("filename", "image")

    context_parts = []
    for key, val in fields.items():
        if key == AIRTABLE_FIELD_NAME:
            continue
        if isinstance(val, str) and val.strip():
            context_parts.append(f"{key}: {val}")

    item_names = get_item_names(fields)
    if item_names:
        context_parts.insert(0, f"Product names: {item_names}")

    context = "\n".join(context_parts) if context_parts else f"Image filename: {filename}"
    recent_captions = _recent_captions()

    for model in FALLBACK_MODELS:
        for _ in range(CAPTION_RETRY_ATTEMPTS):
            mood, style = _random_caption_style()
            prompt = f"""You are a creative copywriter for HomeCartel, a premium lighting and home furniture brand in the Philippines.

PRODUCT DETAILS FROM OUR DATABASE:
{context}

YOUR TASK:
Write ONE short Facebook caption (3-6 words max) for this specific product.

REQUIREMENTS:
- Mood to convey: {mood}
- Writing style: {style}
- The caption must reference something specific about this product, such as the material, shape, color, texture, design style, or the feeling it creates
- Add ONE emoji at the end that matches the mood
- Output ONLY the caption line - no explanation, no quotes, no hashtags

BANNED PHRASES (never use these):
"Light up your space", "Illuminate your world", "Brighten your home", "Shine bright", "Glow up", "Golden glow"{_avoid_recent_prompt_block(recent_captions)}

YOUR CAPTION:"""

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
                content = _clean_caption_output(_extract_chat_content(resp.json()))
                if not content:
                    continue
                if _is_duplicate_caption(content, recent_captions):
                    print(f"  Duplicate caption from {model}; retrying...")
                    recent_captions.append(content)
                    recent_captions = recent_captions[-CAPTION_HISTORY_PROMPT_LIMIT:]
                    continue

                _store_caption(content)
                print(f"  Caption generated using: {model}")
                return content
            except Exception:
                continue

    return _unique_fallback_caption()


def generate_local_image_caption(image_path):
    """Generate a short caption from a locally uploaded image via LM Studio."""
    data_url = _encode_local_image(image_path)
    return generate_lmstudio_visual_caption(
        [{"label": "Uploaded image", "data_url": data_url}],
        visual_context="You are looking at ONE uploaded product or interior photo.",
        fallback_on_exhausted=True,
    )


def generate_lmstudio_visual_caption(image_inputs, text_context="", visual_context="", fallback_on_exhausted=False):
    """Generate a short caption from one or more images using LM Studio vision."""
    prepared_images = []
    for idx, item in enumerate(image_inputs or [], start=1):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or f"Image {idx}").strip() or f"Image {idx}"
        data_url = item.get("data_url")
        if not data_url and item.get("path"):
            data_url = _encode_local_image(item["path"])
        if not data_url and item.get("url"):
            data_url = _download_image_data_url(item["url"])
        if data_url:
            prepared_images.append({"label": label, "data_url": data_url})

    if not prepared_images:
        raise RuntimeError("No image was available for LM Studio caption generation.")

    recent_captions = _recent_captions()
    last_error = None
    image_count = len(prepared_images)
    visual_context = visual_context or (
        "You are looking at ONE product or interior photo."
        if image_count == 1
        else f"You are looking at {image_count} related product/interior photos from the same Airtable row."
    )
    label_lines = "\n".join(f"- Image {idx}: {item['label']}" for idx, item in enumerate(prepared_images, start=1))
    context_block = str(text_context or "").strip()
    if context_block:
        context_block = f"\nPRODUCT DETAILS FROM OUR DATABASE:\n{context_block}\n"

    for _ in range(CAPTION_RETRY_ATTEMPTS):
        mood, style = _random_caption_style()
        prompt = f"""You are a creative copywriter for HomeCartel, a premium lighting and home furniture brand in the Philippines.

{visual_context}

IMAGE LABELS:
{label_lines}
{context_block}

YOUR TASK:
Write ONE short Facebook caption (3-6 words max) inspired by the visible image content.

REQUIREMENTS:
- Mood to convey: {mood}
- Writing style: {style}
- The caption must reference something visible in the image or image set such as the material, silhouette, color, texture, finish, styling, ambiance, contrast, or design feeling
- Add ONE emoji at the end that matches the mood
- Output ONLY the caption line - no explanation, no quotes, no hashtags

BANNED PHRASES (never use these):
"Light up your space", "Illuminate your world", "Brighten your home", "Shine bright", "Glow up", "Golden glow"{_avoid_recent_prompt_block(recent_captions)}

YOUR CAPTION:"""

        content_parts = [{"type": "text", "text": prompt}]
        for idx, item in enumerate(prepared_images, start=1):
            content_parts.append({"type": "text", "text": f"Image {idx}: {item['label']}"})
            content_parts.append({"type": "image_url", "image_url": {"url": item["data_url"]}})

        try:
            resp = requests.post(
                f"{LMSTUDIO_API_BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "model": LMSTUDIO_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": content_parts,
                    }],
                    "max_tokens": LMSTUDIO_MAX_TOKENS,
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "stream": False,
                },
                timeout=_lmstudio_timeout(),
            )
            resp.raise_for_status()
            content = _clean_caption_output(_extract_chat_content(resp.json()))
            if not content:
                continue
            if _is_duplicate_caption(content, recent_captions):
                print("  Duplicate LM Studio caption detected; retrying...")
                recent_captions.append(content)
                recent_captions = recent_captions[-CAPTION_HISTORY_PROMPT_LIMIT:]
                continue

            _store_caption(content)
            print(f"  Caption generated using LM Studio model: {LMSTUDIO_MODEL}")
            return content
        except requests.exceptions.ReadTimeout as exc:
            raise RuntimeError(
                "LM Studio is still processing the image. Increase LMSTUDIO_READ_TIMEOUT or set it to none."
            ) from exc
        except Exception as exc:
            last_error = exc
            break

    if last_error is not None:
        raise RuntimeError(f"LM Studio caption generation failed: {last_error}") from last_error

    if fallback_on_exhausted:
        return _unique_fallback_caption()

    raise RuntimeError("LM Studio did not return a fresh unique caption. Retry after the model is ready.")


def _clean_tip_output(content):
    """Normalize model output for short on-video tips."""
    cleaned = _clean_caption_output(content)
    cleaned = re.sub(r"^[\-\*\d\.\)\s]+", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.encode("ascii", "ignore").decode("ascii").strip()
    return cleaned[:120].rstrip(" ,.;:-")


def _video_tip_category(item_names="", filename=""):
    """Infer a broad product category from known item context."""
    context = str(item_names or filename or "").lower()
    if any(word in context for word in ("lamp", "light", "chandelier", "sconce", "pendant", "ceiling", "mounted", "led")):
        return "lighting"
    if any(word in context for word in ("chair", "stool", "bench", "sofa", "seat", "couch")):
        return "seating"
    if any(word in context for word in ("table", "console", "desk", "sideboard", "coffee")):
        return "surface"
    if any(word in context for word in ("cabinet", "shelf", "storage", "drawer", "wardrobe")):
        return "storage"
    return "general"


def _fallback_video_tip(item_names="", filename="", recent_tips=None):
    """Return a varied safe on-video tip when the vision model gives an empty answer."""
    recent_tips = recent_tips or []
    category = _video_tip_category(item_names, filename)
    candidates = list(_VIDEO_TIP_FALLBACKS.get(category, [])) + list(_VIDEO_TIP_FALLBACKS["general"])
    random.shuffle(candidates)
    for tip in candidates:
        if not _is_duplicate_tip(tip, recent_tips):
            _store_tip(tip)
            return tip

    chosen = random.choice(candidates or _VIDEO_TIP_FALLBACKS["general"])
    _store_tip(chosen)
    return chosen


def _request_video_tip_from_lmstudio(content):
    """Send one video-tip vision request and return cleaned text."""
    resp = requests.post(
        f"{LMSTUDIO_API_BASE_URL}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json={
            "model": LMSTUDIO_MODEL,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": min(LMSTUDIO_MAX_TOKENS, 96),
            "temperature": 0.8,
            "top_p": 0.9,
            "stream": False,
        },
        timeout=_lmstudio_timeout(),
    )
    resp.raise_for_status()
    return _clean_tip_output(_extract_chat_content(resp.json()))


def _video_tip_prompt(item_names="", filename="", recent_tips=None, retry=False):
    """Build the prompt for short Tips Reel overlay text."""
    retry_note = """

Your previous answer was empty or too similar to recent tips. Use a different visible detail and produce a fresh line.""" if retry else ""
    return f"""You are writing short on-screen reel text for HomeCartel, a premium lighting and home furniture brand in the Philippines.

You are looking at one product/interior image from the same Airtable row as one Styled Reel.

PRODUCT CONTEXT:
{item_names or filename or "Furniture or home decor item from the reel"}

TASK:
Internally inspect the image in detail before writing. Identify at least three concrete visible details:
- What product type is visible?
- What shape, finish, color, material, or glow stands out?
- What room style and placement are shown?
- What mood does the product create?
- What practical styling advice follows from those visible details?

Then write ONE practical furniture or lighting styling tip based on one specific visible detail from that analysis.

REQUIREMENTS:
- 6 to 12 words only
- Mention a visible styling idea, material, silhouette, placement, glow, texture, or mood
- Avoid generic tips that could fit any room
- Make it useful as overlay text in a short reel
- No emojis, hashtags, quotes, bullets, explanations, or brand names
- Do not output the analysis
- Output only the tip text
{_avoid_recent_tips_prompt_block(recent_tips or [])}{retry_note}

TIP:"""


def generate_video_tip_from_frames(frame_paths, item_names="", filename=""):
    """Generate one unique short furniture styling tip from one row image or fallback video frame."""
    frames = [path for path in frame_paths if path and os.path.exists(path)]
    if not frames:
        raise ValueError("No visual image was available for AI analysis.")

    frame = frames[0]
    recent_tips = _recent_tips()
    last_error = None
    empty_count = 0
    duplicate_count = 0

    for attempt in range(3):
        prompt = _video_tip_prompt(
            item_names,
            filename,
            recent_tips=recent_tips,
            retry=attempt > 0,
        )
        try:
            tip = _request_video_tip_from_lmstudio([
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _encode_local_image(frame)}},
            ])
            if not tip:
                empty_count += 1
                print("  LM Studio returned an empty video tip; retrying...")
                continue
            if _is_duplicate_tip(tip, recent_tips):
                print("  Duplicate LM Studio video tip detected; retrying...")
                duplicate_count += 1
                recent_tips.append(tip)
                recent_tips = recent_tips[-CAPTION_HISTORY_PROMPT_LIMIT:]
                continue
            _store_tip(tip)
            return tip
        except requests.exceptions.ReadTimeout as exc:
            raise RuntimeError(
                "LM Studio is still processing the visual image. Increase LMSTUDIO_READ_TIMEOUT or set it to none."
            ) from exc
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError, RemoteDisconnected) as exc:
            last_error = exc
            if attempt < 2:
                print("  LM Studio disconnected while generating a video tip; retrying...")
                time.sleep(1.5)
                continue
            print(f"  LM Studio video tip connection failed after retries: {exc}")
        except Exception as exc:
            last_error = exc
            print(f"  LM Studio video tip warning: {exc}")

    if last_error is not None:
        raise RuntimeError(
            "LM Studio disconnected while generating a unique tip. Start LM Studio and retry this Tips Reel."
        ) from last_error
    if duplicate_count:
        raise RuntimeError(
            "LM Studio kept returning duplicate Tips Reel text. Retry to generate a fresh tip."
        )
    if empty_count:
        raise RuntimeError(
            "LM Studio returned empty Tips Reel text. Retry after the model is ready."
        )
    raise RuntimeError("LM Studio could not generate a unique Tips Reel tip. Retry this Tips Reel.")


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
