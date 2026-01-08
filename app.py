import io
import time
import requests
from flask import Flask, send_file
from PIL import Image

app = Flask(__name__)

# --- CONFIGURATION ---
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
CACHE_DURATION = 3600  # Refresh every 1 hour

BASE_URL = "https://cataas.com"

# Global Cache
last_generation_time = 0
cached_image_buffer = None

# 3-Color Palette (Black, White, Red)
pal_image = Image.new("P", (1, 1))
pal_image.putpalette(
    [
        0, 0, 0,       # Black
        255, 255, 255, # White
        255, 0, 0,     # Red
    ] + [0, 0, 0] * 253
)

def fetch_cat_json(tag_mode=True):
    """
    Helper to get JSON data from Cataas.
    tag_mode=True  -> Tries to find 'black' or 'white' cats.
    tag_mode=False -> Gets any random cat (fallback).
    """
    
    # We use headers to strictly request JSON, which is more reliable
    headers = {'Accept': 'application/json'}
    
    if tag_mode:
        # Try specifically for high-contrast cats
        url = f"{BASE_URL}/cat/black,white" 
    else:
        # Fallback: Random cat
        url = f"{BASE_URL}/cat"

    try:
        # We removed '?type=medium' because it often causes 404s if no medium cat exists
        print(f"Requesting: {url}")
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            return r.json()
        else:
            print(f"API Error {r.status_code} for URL: {url}")
            return None
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

def get_best_cat_url():
    """
    Tries to find a suitable cat.
    First attempts to find a Black/White cat.
    If that fails, falls back to ANY cat.
    """
    # Attempt 1 & 2: Try to find a black or white cat
    for _ in range(2):
        data = fetch_cat_json(tag_mode=True)
        if data:
            # Check for GIF (animations don't work on E-ink)
            if "gif" in data.get("mimetype", ""):
                print("Skipping GIF...")
                continue
            
            # Support both '_id' (new API) and 'id' (old API)
            cat_id = data.get('_id') or data.get('id')
            if cat_id:
                return f"{BASE_URL}/cat/{cat_id}?width={DISPLAY_WIDTH}"

    print("High-contrast filter failed. Switching to random fallback.")

    # Attempt 3: Just get ANY random cat (Fallback)
    data = fetch_cat_json(tag_mode=False)
    if data:
        cat_id = data.get('_id') or data.get('id')
        if cat_id:
            return f"{BASE_URL}/cat/{cat_id}?width={DISPLAY_WIDTH}"
            
    return None

def process_cat_image(image_url):
    try:
        print(f"Downloading image: {image_url}")
        r = requests.get(image_url, timeout=15)
        if r.status_code != 200:
            return None
            
        img = Image.open(io.BytesIO(r.content)).convert('RGB')

        # Crop to Fill 800x480
        img_ratio = img.width / img.height
        target_ratio = DISPLAY_WIDTH / DISPLAY_HEIGHT

        if target_ratio > img_ratio:
            scale = DISPLAY_WIDTH / img.width
            new_height = int(img.height * scale)
            img = img.resize((DISPLAY_WIDTH, new_height), Image.Resampling.LANCZOS)
            top = (new_height - DISPLAY_HEIGHT) // 2
            img = img.crop((0, top, DISPLAY_WIDTH, top + DISPLAY_HEIGHT))
        else:
            scale = DISPLAY_HEIGHT / img.height
            new_width = int(img.width * scale)
            img = img.resize((new_width, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
            left = (new_width - DISPLAY_WIDTH) // 2
            img = img.crop((left, 0, left + DISPLAY_WIDTH, DISPLAY_HEIGHT))

        # Dither
        out = img.quantize(palette=pal_image, dither=Image.FLOYDSTEINBERG)
        
        buf = io.BytesIO()
        out.save(buf, format='BMP')
        buf.seek(0)
        return buf

    except Exception as e:
        print(f"Processing error: {e}")
        return None

@app.route('/')
def home():
    return "Cat Server is Running. Go to /cat-ink"

@app.route('/cat-ink')
def get_cat_ink():
    global last_generation_time, cached_image_buffer
    
    now = time.time()
    
    # 1. Use Cache if available (prevents spamming API)
    if cached_image_buffer and (now - last_generation_time < CACHE_DURATION):
        print("Serving from cache")
        cached_image_buffer.seek(0)
        return send_file(cached_image_buffer, mimetype='image/bmp')

    # 2. Fetch New Cat
    print("Cache expired. Fetching new cat...")
    cat_url = get_best_cat_url()
    
    if cat_url:
        processed = process_cat_image(cat_url)
        if processed:
            cached_image_buffer = processed
            last_generation_time = now
            return send_file(cached_image_buffer, mimetype='image/bmp')
        else:
            return "Error processing image", 500
    
    return "Failed to find a cat (API Down?)", 502

if __name__ == '__main__':
    # Cloud host logic
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
