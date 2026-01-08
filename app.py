import io
import time
import requests
from flask import Flask, send_file
from PIL import Image

app = Flask(__name__)

# --- CONFIGURATION ---
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# 3 Minutes = 180 seconds
CACHE_DURATION = 180  

BASE_URL = "https://cataas.com"

# --- GLOBAL CACHE VARIABLES ---
last_generation_time = 0
cached_cat_bytes = None

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
    headers = {'Accept': 'application/json'}
    if tag_mode:
        url = f"{BASE_URL}/cat/black,white" 
    else:
        url = f"{BASE_URL}/cat"

    try:
        # Request metadata
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Connection Error: {e}")
    return None

def get_best_cat_url():
    # Attempt 1 & 2: Try High Contrast (Black/White)
    for _ in range(2):
        data = fetch_cat_json(tag_mode=True)
        if data:
            if "gif" in data.get("mimetype", ""):
                continue
            cat_id = data.get('_id') or data.get('id')
            if cat_id:
                return f"{BASE_URL}/cat/{cat_id}?width={DISPLAY_WIDTH}"

    print("High-contrast filter failed. Switching to random fallback.")

    # Attempt 3: Fallback to ANY cat
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
        
        # Save to Bytes
        buf = io.BytesIO()
        out.save(buf, format='BMP')
        
        # Return raw bytes
        return buf.getvalue()

    except Exception as e:
        print(f"Processing error: {e}")
        return None

@app.route('/')
def home():
    return "Cat Server is Running. Go to /cat-ink"

@app.route('/cat-ink')
def get_cat_ink():
    global last_generation_time, cached_cat_bytes
    
    now = time.time()
    
    # --- LOGIC START ---
    
    # 1. Check if Cache is valid (less than 3 minutes old)
    if cached_cat_bytes and (now - last_generation_time < CACHE_DURATION):
        print(f"Serving from cache ({(CACHE_DURATION - (now - last_generation_time)):.0f}s remaining)")
        return send_file(io.BytesIO(cached_cat_bytes), mimetype='image/bmp')

    # 2. Cache expired or empty -> Fetch New
    print("Cache expired. Fetching new cat...")
    cat_url = get_best_cat_url()
    
    if cat_url:
        new_bytes = process_cat_image(cat_url)
        if new_bytes:
            # Update Cache
            cached_cat_bytes = new_bytes
            last_generation_time = now
            return send_file(io.BytesIO(cached_cat_bytes), mimetype='image/bmp')
        else:
            return "Error processing image", 500
    
    return "Failed to find a cat (API Down?)", 502

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
