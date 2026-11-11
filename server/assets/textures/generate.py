"""Rebuild original Pillow artwork (macOS Heiti or supplied CJK font)."""
from pathlib import Path
import os
import random
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
FONT = os.environ.get('WORKSTATION_FONT', '/System/Library/Fonts/STHeiti Medium.ttc')

def label(name, title, subtitle, background, size=(1024, 384)):
    image = Image.new('RGB', size, background)
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rounded_rectangle((12, 12, w-13, h-13), radius=20, outline='#eacb88', width=6)
    for y, text, pixels in ((h*.15, title, int(h*.36)), (h*.66, subtitle, int(h*.12))):
        font = ImageFont.truetype(FONT, pixels)
        draw.text((w/2, y), text, font=font, fill='#fff0cf', anchor='mt')
    image.save(ROOT / f'{name}.png')

for name, title, subtitle, color in [
    ('jipai', '香酥雞排', 'CRISPY CHICKEN  /  夜市 01', '#8b2822'),
    ('pepper', '炭烤胡椒餅', 'PEPPER BUN  /  夜市 02', '#73452b'),
    ('tea', '手搖珍珠奶茶', 'BUBBLE TEA  /  夜市 03', '#245a50'),
    ('bag', '夜市', 'FRESH & HOT', '#a67944'),
    ('pickup', '取餐區', 'PICK UP', '#286451'),
    ('season', '椒鹽', 'SEASON', '#9b4b29'),
    ('cup', '茶', 'NIGHT TEA', '#b89466'),
]:
    label(name, title, subtitle, color)

rng = random.Random(41)
for name, base in [('crust', (189, 118, 39)), ('bread', (199, 142, 65)), ('steel', (111, 129, 128))]:
    image = Image.new('RGB', (256, 256), base)
    draw = ImageDraw.Draw(image)
    for _ in range(5000):
        x, y = rng.randrange(256), rng.randrange(256)
        delta = rng.randint(-48, 45) if name != 'steel' else rng.randint(-7, 7)
        color = tuple(max(0, min(255, c+delta)) for c in base)
        r = rng.randrange(1, 4)
        draw.ellipse((x, y, x+r*2, y+r), fill=color)
    if name == 'bread':
        for _ in range(140):
            x, y = rng.randrange(256), rng.randrange(256)
            draw.ellipse((x, y, x+2, y+5), fill='#f6dfab')
    image.save(ROOT / f'{name}.png')
