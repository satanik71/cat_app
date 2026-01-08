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

# Filter for cats that look best on e-ink (High contrast)
# We ask Cataas for cats tagged with 'black' or 'white'
CATAAS_TAGS = ["black", "white"] 
BASE_URL = "https://cataas.com"

# Global Cache
last_generation_time = 0
cached_image_buffer = None

# 3-Color Palette (Black, White, Red) for E-Ink
pal_image = Image.new("P", (1, 1))
pal_image.putpalette(
    [
        0, 0, 0,       # Black
        255, 255, 255, # White
        255, 0, 0,     # Red
    ] + [0, 0, 0] * 253
)

def get_best_cat_url():
    """
    Queries Cataas JSON API to find a suitable cat image.
    Retries up to 3 times if it gets a GIF or bad response.
    """
    # We join tags with commas to find cats that have ANY of these tags
    tags_param = ",".join(CATAAS_TAGS)
    
    # We request JSON to check metadata first
    # 'type=medium' avoids thumbnails or massive 4k images
    json_url = f"{BASE_URL}/cat/{tags_param}?json=true&type=medium"

    for attempt in range(3):
        try:
            r = requests.get(json_url, timeout=5)
            if r.status_code == 200:
                data = r.json()
                
                # FILTER 1: Strict File Type Check
                if "gif" in data.get("mimetype", ""):
                    print("Skipping GIF...")
                    continue
                
                # Success: Return the download URL with width parameter
                # We ask Cataas to resize close to our target width to save bandwidth
                return f"{BASE_URL}/cat/{data['_id']}?width={DISPLAY_WIDTH}"
            
        except Exception as e:
            print(f"Error fetching metadata: {e}")
    
    return None

def process_cat_image(image_url):
    """Downloads, Crops, and Dithers the image"""
    try:
        # 1. Download the image bytes
        r = requests.get(image_url, timeout=10)
        if r.status_code != 200:
            return None
            
        img = Image.open(io.BytesIO(r.content)).convert('RGB')

        # 2. Aspect Fill Crop (to fill 800x480 exactly)
        img_ratio = img.width / img.height
        target_ratio = DISPLAY_WIDTH / DISPLAY_HEIGHT

        if target_ratio > img_ratio:
            # Image is too tall, fit to width
            scale = DISPLAY_WIDTH / img.width
            new_height = int(img.height * scale)
            img = img.resize((DISPLAY_WIDTH, new_height), Image.Resampling.LANCZOS)
            # Center Crop Vertical
            top = (new_height - DISPLAY_HEIGHT) // 2
            img = img.crop((0, top, DISPLAY_WIDTH, top + DISPLAY_HEIGHT))
        else:
            # Image is too wide, fit to height
            scale = DISPLAY_HEIGHT / img.height
            new_width = int(img.width * scale)
            img = img.resize((new_width, DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
            # Center Crop Horizontal
            left = (new_width - DISPLAY_WIDTH) // 2
            img = img.crop((left, 0, left + DISPLAY_WIDTH, DISPLAY_HEIGHT))

        # 3. Apply Red/Black/White Dithering
        # This converts the photo into the dot pattern the screen needs
        out = img.quantize(palette=pal_image, dither=Image.FLOYDSTEINBERG)
        
        # 4. Save to buffer
        buf = io.BytesIO()
        out.save(buf, format='BMP')
        buf.seek(0)
        return buf

    except Exception as e:
        print(f"Processing error: {e}")
        return None

@app.route('/cat-ink')
def get_cat_ink():
    global last_generation_time, cached_image_buffer
    
    now = time.time()
    
    # Serve cached image if valid
    if cached_image_buffer and (now - last_generation_time < CACHE_DURATION):
        cached_image_buffer.seek(0)
        return send_file(cached_image_buffer, mimetype='image/bmp')

    # Otherwise generate new one
    print("Fetching new cat...")
    cat_url = get_best_cat_url()
    
    if cat_url:
        processed = process_cat_image(cat_url)
        if processed:
            cached_image_buffer = processed
            last_generation_time = now
            return send_file(cached_image_buffer, mimetype='image/bmp')

    return "Failed to find a cat", 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)