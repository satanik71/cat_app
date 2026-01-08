import io
import time
import random
import urllib.parse
import requests
from flask import Flask, send_file
from PIL import Image

app = Flask(__name__)

# --- CONFIGURATION ---
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
CACHE_DURATION = 180  # 3 Minutes

# --- GLOBAL CACHE ---
last_generation_time = 0
cached_image_bytes = None

# 3-Color Palette (Black, White, Red)
pal_image = Image.new("P", (1, 1))
pal_image.putpalette(
    [
        0, 0, 0,       # Black
        255, 255, 255, # White
        255, 0, 0,     # Red
    ] + [0, 0, 0] * 253
)

# A list of prompts to keep the sketches interesting
PROMPTS = [
    "minimalist continuous line drawing of a cat, black ink on white background, red collar",
    "vector sketch of a cute cat face, simple lines, white background, small red heart",
    "stippling art style drawing of a cat sleeping, high contrast, white background, red ball of yarn",
    "pen and ink sketch of a cat sitting on a fence, white background, red bowtie",
    "japanese ink wash painting of a cat, minimal, white background, red sun in background"
]

def generate_sketch_url():
    """Constructs the Pollinations URL for a random sketch"""
    prompt = random.choice(PROMPTS)
    encoded_prompt = urllib.parse.quote(prompt)
    
    # We add a random seed to ensure a NEW picture every time
    seed = random.randint(0, 100000)
    
    # Requesting slightly larger image to ensure crisp lines when resized
    return f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true&model=flux"

def process_image(image_url):
    try:
        print(f"Generating AI Sketch: {image_url}")
        # Pollinations can take 3-6 seconds, so we increase timeout
        r = requests.get(image_url, timeout=30)
        if r.status_code != 200:
            print(f"Pollinations Error: {r.status_code}")
            return None
            
        img = Image.open(io.BytesIO(r.content)).convert('RGB')

        # 1. Resize & Crop to 800x480
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

        # 2. Dither
        # Even though it's a sketch, dithering helps smooth the diagonal lines
        out = img.quantize(palette=pal_image, dither=Image.FLOYDSTEINBERG)
        
        # 3. Save to raw bytes
        buf = io.BytesIO()
        out.save(buf, format='BMP')
        return buf.getvalue()

    except Exception as e:
        print(f"Processing error: {e}")
        return None

@app.route('/')
def home():
    return "Cat Sketch Server Running. Go to /cat-ink"

@app.route('/cat-ink')
def get_cat_ink():
    global last_generation_time, cached_image_bytes
    
    now = time.time()
    
    # --- 1. CACHE CHECK ---
    if cached_image_bytes and (now - last_generation_time < CACHE_DURATION):
        remaining = CACHE_DURATION - (now - last_generation_time)
        print(f"Serving Cache ({remaining:.0f}s left)")
        return send_file(io.BytesIO(cached_image_bytes), mimetype='image/bmp')

    # --- 2. GENERATE NEW ---
    print("Cache expired. Generating new sketch...")
    url = generate_sketch_url()
    
    new_bytes = process_image(url)
    
    if new_bytes:
        cached_image_bytes = new_bytes
        last_generation_time = now
        return send_file(io.BytesIO(cached_image_bytes), mimetype='image/bmp')
    else:
        # If AI fails, try to serve old cache if it exists, otherwise error
        if cached_image_bytes:
             return send_file(io.BytesIO(cached_image_bytes), mimetype='image/bmp')
        return "Failed to generate sketch", 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
