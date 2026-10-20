"""Renders logo-led.gif: the top right corner of a Cidoo V75 Pro and its logo light bar,
driven by the same arithmetic as src/logo.c (ease, flash, cascade, charge colour).

Usage: python make_gif.py  ->  logo-led.gif next to this script (needs numpy and Pillow)
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "logo-led.gif")
FPS = 20
TICK_HZ = 16_000_000
SS = 3  # supersampling of the static drawing

W, H, SCENE_H = 420, 330, 270
FONT = os.environ.get("GIF_FONT", r"C:\Windows\Fonts\seguisb.ttf")  # any TrueType font

TABLE = (236, 235, 231)
CASE = (218, 213, 200)
CASE_EDGE = (200, 194, 179)
CAP = (234, 230, 219)
CAP_SIDE = (206, 200, 186)
LEGEND = (70, 70, 72)
BAR_OFF = np.array([226, 226, 220], float)

BAR = (252, 36, 264, 98)  # x0, y0, x1, y1 of the light bar
LED_POS = (0.17, 0.5, 0.83)  # LED 0, 1, 2 along the bar from its top (0) to its bottom (1): 2 is the bottom one


# --- the firmware's arithmetic (src/logo.c) -------------------------------------------------
def ease(u):
    return 256 if u >= 256 else (u * u * (768 - 2 * u)) >> 16


def flash(t, shift):
    x = (int(t * TICK_HZ) >> shift) & 1023
    if x < 128:
        return ease(x * 2)
    if x < 896:
        return 256 - ease(((x - 128) * 85) >> 8)
    return 0


def cascade(t, n):
    x = (int(t * TICK_HZ) >> 16) & 1023
    k = 2 - n
    start = 288 * k
    if x >= 928:
        return 256 - ease((x - 928) * 4) if x < 992 else 0
    if x < start:
        return 0
    return ease(x - start) if k == 2 else ease(((x - start) * 205) >> 8)


def charge_rgb(pct):
    x = min(pct, 100) - 20
    if x <= 40:
        return (255, (x * 51) >> 3, 0)
    return (((80 - x) * 51) >> 3, 255, 0)


# --- drawing ----------------------------------------------------------------------------------
def font(size):
    return ImageFont.truetype(FONT, size * SS)


def keycap(d, x0, y0, x1, y1, label):
    s = SS
    d.rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), 8 * s, fill=CAP_SIDE)
    d.rounded_rectangle(((x0 + 4) * s, (y0 + 3) * s, (x1 - 4) * s, (y1 - 8) * s), 6 * s, fill=CAP)
    d.text(((x0 + 11) * s, (y0 + 9) * s), label, font=font(11), fill=LEGEND)


def background():
    s = SS
    im = Image.new("RGB", (W * s, H * s), TABLE)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((-40 * s, 8 * s, 392 * s, (SCENE_H + 40) * s), 24 * s, fill=CASE_EDGE)
    d.rounded_rectangle((-40 * s, 10 * s, 388 * s, (SCENE_H + 40) * s), 22 * s, fill=CASE)
    for x0, x1, y0, label in [(16, 86, 28, "F11"), (90, 160, 28, "F12"), (164, 234, 28, "DEL"),
                              (16, 86, 104, "=+"), (90, 234, 104, "BACKSPACE"), (286, 356, 104, "HOME"),
                              (16, 86, 180, "]}"), (90, 196, 180, "\\|"), (286, 356, 180, "PGUP")]:
        keycap(d, x0, y0, x1, y0 + 72, label)
    # knob: brushed aluminium, concentric rings
    cx, cy, r = 322, 66, 40
    for i in range(r * s, 0, -1):
        k = i / (r * s)
        v = int(155 + 65 * (1 - k) + 5 * np.sin(i / (1.2 * s)))
        d.ellipse(((cx * s - i), (cy * s - i), (cx * s + i), (cy * s + i)), fill=(v, v, v + 4))
    d.ellipse(((cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s), outline=(120, 120, 124), width=2 * s)
    # light bar seat and diffuser (off)
    x0, y0, x1, y1 = BAR
    d.rounded_rectangle(((x0 - 3) * s, (y0 - 3) * s, (x1 + 3) * s, (y1 + 3) * s), 8 * s, fill=CASE_EDGE)
    d.rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), 6 * s, fill=tuple(int(c) for c in BAR_OFF))
    # caption strip
    d.rectangle((0, SCENE_H * s, W * s, H * s), fill=TABLE)
    d.line((0, SCENE_H * s, W * s, SCENE_H * s), fill=(214, 212, 206), width=s)
    return im.resize((W, H), Image.LANCZOS)


def bar_mask():
    s = SS
    m = Image.new("L", (W * s, H * s), 0)
    x0, y0, x1, y1 = BAR
    ImageDraw.Draw(m).rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), 6 * s, fill=255)
    return np.asarray(m.resize((W, H), Image.LANCZOS), float) / 255


BG = background()
MASK = bar_mask()
YY = np.mgrid[0:H, 0:W][0].astype(float)


def light_layer(leds):
    """leds: three (rgb, v 0..256). Light inside the bar, from LEDs under a diffuser."""
    x0, y0, x1, y1 = BAR
    acc = np.zeros((H, W, 3))
    for (rgb, v), pos in zip(leds, LED_POS):
        if v <= 0:
            continue
        cy = y0 + pos * (y1 - y0)
        g = np.exp(-((YY - cy) / 15.0) ** 2)
        acc += g[..., None] * np.array(rgb, float) * (v / 256)
    return np.clip(acc, 0, 255)


def frame(leds, caption):
    base = np.asarray(BG, float).copy()
    lit = light_layer(leds)
    # diffuser: off colour plus the light, inside the bar shape
    peak = lit.max(axis=2, keepdims=True)
    hue = lit / np.maximum(peak, 1) * 255  # the colour at full strength
    a = np.clip(peak / 255, 0, 1)
    tinted = BAR_OFF * (1 - a) + (hue * 0.85 + 255 * 0.15) * a
    m = MASK[..., None]
    base = base * (1 - m) + tinted * m
    # glow on the case around the bar
    glow_src = Image.fromarray((lit * m).astype(np.uint8))
    glow = np.asarray(glow_src.filter(ImageFilter.GaussianBlur(9)), float)
    base[:SCENE_H] = np.clip(base[:SCENE_H] + glow[:SCENE_H] * 1.6 * (1 - m[:SCENE_H]), 0, 255)
    im = Image.fromarray(base.astype(np.uint8))
    draw_caption(ImageDraw.Draw(im), *caption)
    return im


def draw_caption(d, pct, colour, mode):
    """Battery icon with its level, the percentage, and a plug when the cable is in."""
    y = SCENE_H + 14
    d.rounded_rectangle((18, y, 70, y + 30), 6, outline=LEGEND, width=3)
    d.rectangle((71, y + 9, 76, y + 21), fill=LEGEND)
    fill_w = int(44 * pct / 100)
    if fill_w > 0:
        d.rounded_rectangle((22, y + 4, 22 + fill_w, y + 26), 3, fill=colour)
    f = ImageFont.truetype(FONT, 26)
    d.text((90, y - 3), "%d%%" % pct, font=f, fill=LEGEND)
    if mode != "battery":
        # plug
        px = 330
        d.rounded_rectangle((px, y + 6, px + 26, y + 26), 5, fill=LEGEND)
        d.rectangle((px + 6, y - 2, px + 9, y + 6), fill=LEGEND)
        d.rectangle((px + 17, y - 2, px + 20, y + 6), fill=LEGEND)
        d.rectangle((px + 11, y + 26, px + 15, y + 34), fill=LEGEND)
        if mode == "charging":  # bolt
            d.polygon([(372, y - 2), (362, y + 16), (370, y + 16), (364, y + 34), (382, y + 11),
                       (373, y + 11), (380, y - 2)], fill=(232, 168, 40))
        else:  # check mark
            d.line([(362, y + 15), (370, y + 24), (386, y + 4)], fill=(40, 170, 70), width=5)


def tone(rgb):
    return tuple(int(c * 0.82) for c in rgb)


def scenes():
    frames = []
    dt = 1 / FPS
    # battery 100 -> 20 %, steady colour (sped up: 4 s)
    n = int(4 * FPS)
    for i in range(n + 1):
        pct = round(100 - 80 * i / n)
        c = charge_rgb(pct)
        frames.append(frame([(c, 256)] * 3, (pct, tone(c), "battery")))
    for _ in range(int(0.6 * FPS)):
        frames.append(frames[-1])
    # below 20 %: red flash, two periods in real time
    for i in range(int(2 * 1024 * 2 ** 15 / TICK_HZ * FPS)):
        v = flash(i * dt, 15)
        frames.append(frame([((255, 0, 0), v)] * 3, (12, tone((255, 0, 0)), "battery")))
    # charging: the bar fills from the bottom, two periods in real time
    for i in range(int(2 * 1024 * 2 ** 16 / TICK_HZ * FPS)):
        t = i * dt
        frames.append(frame([((0, 255, 0), cascade(t, k)) for k in range(3)], (64, tone(charge_rgb(64)), "charging")))
    # charged: green flash, one period in real time
    for i in range(int(1024 * 2 ** 16 / TICK_HZ * FPS)):
        v = flash(i * dt, 16)
        frames.append(frame([((0, 255, 0), v)] * 3, (100, tone(charge_rgb(100)), "charged")))
    return frames


def main():
    frames = scenes()
    # one palette for all frames keeps the file small and the colours stable
    picks = np.linspace(0, len(frames) - 1, 24).astype(int)
    sample = Image.new("RGB", (W, H * len(picks)))
    for k, idx in enumerate(picks):
        sample.paste(frames[idx], (0, H * k))
    pal = sample.quantize(colors=255, method=Image.MEDIANCUT)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=int(1000 / FPS), loop=0, optimize=True, disposal=1)
    print(OUT, len(frames), "frames,", os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main()
