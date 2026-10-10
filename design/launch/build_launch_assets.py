#!/usr/bin/env python3
"""Generate LuoShu launch assets: diffuse backdrop, glass card, grain and Android 12+ splash orb.

Reproducible (fixed seed). Requires numpy + Pillow. Run from the repository root:

    python3 design/launch/build_launch_assets.py [--icon PATH] [--preview DIR]

The launcher icon itself is never touched; the card tile is cut from the original icon art.
Geometry constants are mirrored by ui/launch/LuoShuLaunchArtwork.kt; keep both in sync.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "android-app/app/src/main/res"
DEFAULT_ICON = ROOT / "android-app/app/src/main/res/mipmap-xxxhdpi/ic_luoshu.webp"  # prefer the 512px source via --icon

# --- Geometry (dp) mirrored in LuoShuLaunchArtwork.kt ---
CARD_DP = 208.0          # glass card edge at scale 1
CARD_CANVAS_DP = 288.0   # card bitmap canvas (shadow margin included)
TILE_DP = 104.0          # icon tile edge at scale 1
CARD_START_SCALE = 0.955 # first frame (system splash / starting window hand-off)
SQUIRCLE_N = 4.2         # superellipse exponent of card and tile
CARD_PX_PER_DP = 4       # card bitmap resolution
ORB_CANVAS_PX = 720      # Android 12+ icon canvas = 288dp
ORB_PX_PER_DP = ORB_CANVAS_PX / 288.0

THEMES = {
    "light": {
        "base": (220, 224, 242),
        # (cx, cy, sigma as fraction of width, colour, strength)
        "blobs": [
            (0.10, 0.14, 0.62, (150, 182, 244), 0.92),
            (1.02, 0.40, 0.55, (200, 176, 240), 0.88),
            (0.04, 0.80, 0.58, (160, 222, 232), 0.90),
            (0.96, 0.95, 0.50, (236, 196, 226), 0.90),
            (0.52, 0.52, 0.34, (214, 210, 246), 0.55),
        ],
        "splash": None,  # computed from backdrop centre
        "shadow": ((84, 88, 178), 0.58),
        "fill_top": 0.52, "fill_bottom": 0.22,
        "rim": (1.0, 0.28),
        "highlight": 0.55,
        "tile_shadow": ((22, 36, 92), 0.50),
        "grain": 7.0,
    },
    "dark": {
        "base": (22, 26, 54),
        "blobs": [
            (0.10, 0.14, 0.62, (40, 74, 152), 0.92),
            (1.02, 0.40, 0.55, (88, 60, 166), 0.90),
            (0.04, 0.80, 0.58, (20, 100, 122), 0.88),
            (0.96, 0.95, 0.50, (108, 48, 128), 0.88),
            (0.52, 0.52, 0.34, (52, 54, 122), 0.60),
        ],
        "splash": None,
        "shadow": ((4, 4, 18), 0.72),
        "fill_top": 0.24, "fill_bottom": 0.09,
        "rim": (0.80, 0.14),
        "highlight": 0.26,
        "tile_shadow": ((0, 2, 12), 0.62),
        "grain": 5.0,
    },
}


def backdrop(theme: str, width: int, height: int) -> np.ndarray:
    spec = THEMES[theme]
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float64)
    color = np.ones((height, width, 3)) * np.array(spec["base"], dtype=np.float64)
    for cx, cy, sigma, rgb, strength in spec["blobs"]:
        d2 = ((xx - cx * width) ** 2 + (yy - cy * height) ** 2) / (sigma * width) ** 2
        weight = (strength * np.exp(-d2 * 1.6))[..., None]
        color = color * (1 - weight) + np.array(rgb, dtype=np.float64) * weight
    return color


def to_image(array: np.ndarray, mode: str = "RGB") -> Image.Image:
    return Image.fromarray(np.clip(np.rint(array), 0, 255).astype(np.uint8), mode)


def squircle_mask(size: int, edge: float, n: float = SQUIRCLE_N, supersample: int = 4) -> Image.Image:
    big = size * supersample
    c = (big - 1) / 2
    yy, xx = np.mgrid[0:big, 0:big].astype(np.float64)
    a = edge * supersample / 2
    inside = (np.abs((xx - c) / a) ** n + np.abs((yy - c) / a) ** n) <= 1
    return to_image(inside * 255.0, "L").resize((size, size), Image.Resampling.LANCZOS)


def grain_tile(theme: str, size: int = 128, seed: int = 1729) -> Image.Image:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, (size, size))
    amount = THEMES[theme]["grain"]
    alpha = np.clip(np.abs(noise) * amount, 0, 40)
    rgb = np.where(noise[..., None] > 0, 255.0, 0.0) * np.ones((1, 1, 3))
    return to_image(np.dstack([rgb, alpha]), "RGBA")


def card_overlay(theme: str, icon: Image.Image) -> Image.Image:
    spec = THEMES[theme]
    size = int(CARD_CANVAS_DP * CARD_PX_PER_DP)
    edge = CARD_DP * CARD_PX_PER_DP
    mask = squircle_mask(size, edge)
    m = np.asarray(mask, dtype=np.float64) / 255
    canvas = np.zeros((size, size, 4))

    def over(rgb, alpha):
        alpha = np.clip(alpha, 0, 1)[..., None]
        src = np.dstack([np.broadcast_to(np.array(rgb, dtype=np.float64), (size, size, 3)), np.ones((size, size))])
        out_a = alpha + canvas[..., 3:4] * (1 - alpha)
        out_rgb = (src[..., :3] * alpha + canvas[..., :3] * canvas[..., 3:4] * (1 - alpha)) / np.maximum(out_a, 1e-6)
        canvas[..., :3] = out_rgb
        canvas[..., 3:4] = out_a

    # 1. soft coloured shadow, outside the glass only.
    shadow_rgb, shadow_alpha = spec["shadow"]
    offset = int(16 * CARD_PX_PER_DP)
    shadow = Image.new("L", (size, size), 0)
    shadow.paste(mask, (0, offset))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14 * CARD_PX_PER_DP))
    s = np.asarray(shadow, dtype=np.float64) / 255 * shadow_alpha * (1 - m)
    over(shadow_rgb, s)
    # 2. translucent white fill, brighter at the top.
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    top = (size - edge) / 2
    v = np.clip((yy - top) / edge, 0, 1)
    fill = (spec["fill_top"] * (1 - v) + spec["fill_bottom"] * v) * m
    over((255, 255, 255), fill)
    # 3. specular highlight (top-left) and a faint diagonal sheen.
    hl = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(hl)
    d.ellipse([top + edge * 0.02, top - edge * 0.10, top + edge * 0.62, top + edge * 0.30], fill=255)
    hl = hl.filter(ImageFilter.GaussianBlur(edge * 0.07))
    h = np.asarray(hl, dtype=np.float64) / 255 * spec["highlight"] * m
    over((255, 255, 255), h)
    # 4. 1dp gradient rim: bright top-left -> faint bottom-right.
    inner = squircle_mask(size, edge - 2 * CARD_PX_PER_DP)
    ring = np.clip(m - np.asarray(inner, dtype=np.float64) / 255, 0, 1)
    t = np.clip(((xx - top) + (yy - top)) / (2 * edge), 0, 1)
    bright, faint = spec["rim"]
    over((255, 255, 255), ring * (bright * (1 - t) + faint * t))
    # inner soft glow along the rim for thickness.
    glow = Image.fromarray((ring * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3 * CARD_PX_PER_DP))
    g = np.asarray(glow, dtype=np.float64) / 255 * m * 0.35 * (bright * (1 - t) + faint * t)
    over((255, 255, 255), g)
    # 5. icon tile with its own shadow.
    tile_px = int(round(TILE_DP * CARD_PX_PER_DP))
    tile_shadow_rgb, tile_shadow_alpha = spec["tile_shadow"]
    tmask = squircle_mask(tile_px, tile_px)
    ts = Image.new("L", (size, size), 0)
    origin = (size - tile_px) // 2
    ts.paste(tmask, (origin, origin + int(7 * CARD_PX_PER_DP)))
    ts = ts.filter(ImageFilter.GaussianBlur(7 * CARD_PX_PER_DP))
    over(tile_shadow_rgb, np.asarray(ts, dtype=np.float64) / 255 * tile_shadow_alpha * m)
    image = to_image(np.dstack([canvas[..., :3], canvas[..., 3:4] * 255]), "RGBA")
    art = icon.convert("RGBA").resize((tile_px, tile_px), Image.Resampling.LANCZOS)
    tile = Image.new("RGBA", (tile_px, tile_px), (0, 0, 0, 0))
    tile.paste(art, (0, 0), tmask)
    image.alpha_composite(tile, (origin, origin))
    # tile rim
    tinner = squircle_mask(tile_px, tile_px - 2 * CARD_PX_PER_DP)
    tring = np.clip(np.asarray(tmask, dtype=np.float64) - np.asarray(tinner, dtype=np.float64), 0, 255) / 255
    tt = np.clip((np.mgrid[0:tile_px, 0:tile_px].sum(axis=0)) / (2 * tile_px), 0, 1)
    rim = to_image(np.dstack([np.full((tile_px, tile_px, 3), 255.0), tring * (0.55 * (1 - tt) + 0.08 * tt) * 255]), "RGBA")
    image.alpha_composite(rim, (origin, origin))
    return image


def splash_orb(theme: str, icon: Image.Image, splash_rgb: tuple[int, int, int]) -> Image.Image:
    spec = THEMES[theme]
    size = ORB_CANVAS_PX
    c = (size - 1) / 2
    radius = 92.0 * ORB_PX_PER_DP
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    r = np.hypot(xx - c, yy - c)
    base = np.ones((size, size, 3)) * np.array(splash_rgb, dtype=np.float64)
    # Local diffuse field inside the orb: the same colours as the full-screen backdrop.
    local = np.ones((size, size, 3)) * np.array(spec["base"], dtype=np.float64)
    for (cx, cy, sigma, rgb, strength) in (
        (0.30, 0.26, 0.26, spec["blobs"][0][3], 0.95),
        (0.80, 0.46, 0.24, spec["blobs"][1][3], 0.92),
        (0.28, 0.78, 0.24, spec["blobs"][2][3], 0.92),
        (0.76, 0.80, 0.20, spec["blobs"][3][3], 0.90),
    ):
        d2 = ((xx - cx * size) ** 2 + (yy - cy * size) ** 2) / (sigma * size) ** 2
        w = (strength * np.exp(-d2 * 1.4))[..., None]
        local = local * (1 - w) + np.array(rgb, dtype=np.float64) * w
    disc = np.clip((radius - r) / 2.5 + 0.5, 0, 1)[..., None]
    out = base * (1 - disc) + local * disc
    # frosted glass: white veil, brighter at the top.
    v = np.clip((yy - (c - radius)) / (2 * radius), 0, 1)[..., None]
    veil = (spec["fill_top"] * 0.85 * (1 - v) + spec["fill_bottom"] * 0.85 * v) * disc
    out = out * (1 - veil) + 255 * veil
    image = to_image(out).convert("RGBA")
    # coloured inner shadow under the tile and the specular highlight.
    tile_px = int(round(TILE_DP * CARD_START_SCALE * ORB_PX_PER_DP))
    tmask = squircle_mask(tile_px, tile_px)
    origin = (size - tile_px) // 2
    ts = Image.new("L", (size, size), 0)
    ts.paste(tmask, (origin, origin + int(7 * ORB_PX_PER_DP)))
    ts = ts.filter(ImageFilter.GaussianBlur(7 * ORB_PX_PER_DP))
    shadow_rgb, shadow_alpha = spec["tile_shadow"]
    layer = Image.new("RGBA", (size, size), shadow_rgb + (0,))
    layer.putalpha(ts.point(lambda p: int(p * shadow_alpha)))
    image.alpha_composite(layer)
    hl = Image.new("L", (size, size), 0)
    ImageDraw.Draw(hl).ellipse([c - radius * 0.82, c - radius * 0.96, c + radius * 0.30, c - radius * 0.40], fill=255)
    hl = hl.filter(ImageFilter.GaussianBlur(radius * 0.10))
    h = (np.asarray(hl, dtype=np.float64) * spec["highlight"] * disc[..., 0]).astype(np.uint8)
    white = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    white.putalpha(Image.fromarray(h))
    image.alpha_composite(white)
    # 1dp rim, bright top-left -> faint bottom-right
    ring = np.clip(1 - np.abs(r - (radius - 1.3)) / 1.6, 0, 1)
    t = np.clip(((xx - c) + (yy - c)) / (2 * radius) * 0.5 + 0.5, 0, 1)
    bright, faint = spec["rim"]
    rim = to_image(np.dstack([np.full((size, size, 3), 255.0), ring * (bright * (1 - t) + faint * t) * 255]), "RGBA")
    image.alpha_composite(rim)
    art = icon.convert("RGBA").resize((tile_px, tile_px), Image.Resampling.LANCZOS)
    tile = Image.new("RGBA", (tile_px, tile_px), (0, 0, 0, 0))
    tile.paste(art, (0, 0), tmask)
    image.alpha_composite(tile, (origin, origin))
    return image.convert("RGB")


def save_webp(image: Image.Image, path: Path, *, lossless: bool = False, quality: int = 92) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if lossless:
        image.save(path, "WEBP", lossless=True, quality=100, method=6)
    else:
        image.save(path, "WEBP", quality=quality, method=6, alpha_quality=100)


def splash_color(theme: str) -> tuple[int, int, int]:
    field = backdrop(theme, 108, 240)
    centre = field[96:144, 30:78].reshape(-1, 3).mean(axis=0)
    return tuple(int(round(value)) for value in centre)


def render_shell(theme: str, width: int, height: int, density: float, icon: Image.Image,
                 card_scale: float = 1.0, font: Path | None = None) -> Image.Image:
    """Static preview of the App launch shell (design review / bootstrap fixtures only)."""
    field = to_image(backdrop(theme, 540, 1200)).resize((width, height), Image.Resampling.BILINEAR)
    frame = field.convert("RGBA")
    grain = grain_tile(theme)
    for y in range(0, height, grain.height):
        for x in range(0, width, grain.width):
            frame.alpha_composite(grain, (x, y))
    overlay = card_overlay(theme, icon)
    edge = int(round(CARD_CANVAS_DP * density * card_scale))
    overlay = overlay.resize((edge, edge), Image.Resampling.LANCZOS)
    blurred = to_image(backdrop(theme, 54, 120)).resize((width, height), Image.Resampling.BILINEAR)
    card_px = int(round(CARD_DP * density * card_scale))
    mask = squircle_mask(card_px, card_px)
    cx, cy = width // 2, height // 2
    frame.paste(blurred.crop((cx - card_px // 2, cy - card_px // 2, cx - card_px // 2 + card_px, cy - card_px // 2 + card_px)),
                (cx - card_px // 2, cy - card_px // 2), mask)
    frame.alpha_composite(overlay, (cx - edge // 2, cy - edge // 2))
    if font is not None:
        draw = ImageDraw.Draw(frame)
        ink, sub = ((39, 54, 92), (74, 90, 128)) if theme == "light" else ((238, 241, 250), (174, 184, 214))
        big = ImageFont.truetype(str(font), int(32 * density))
        try:
            big.set_variation_by_axes([700])
        except Exception:
            pass
        small = ImageFont.truetype(str(font), int(13 * density))
        base = cy + CARD_DP * density / 2 + 58 * density
        draw.text((cx, base), "洛书", font=big, fill=ink, anchor="ms")
        draw.text((cx, base + 28 * density), "LuoShu · 字体管理", font=small, fill=sub, anchor="ms")
    return frame.convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icon", type=Path, default=DEFAULT_ICON)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    icon = Image.open(args.icon).convert("RGBA")
    for theme, folder in (("light", "drawable-nodpi"), ("dark", "drawable-night-nodpi")):
        out = RES / folder
        save_webp(to_image(backdrop(theme, 540, 1200)), out / "luoshu_launch_backdrop.webp", lossless=True)
        save_webp(to_image(backdrop(theme, 54, 120)), out / "luoshu_launch_backdrop_blur.webp", lossless=True)
        grain_tile(theme).save(out / "luoshu_launch_grain.png", optimize=True)
        save_webp(card_overlay(theme, icon), out / "luoshu_launch_card.webp")
        rgb = splash_color(theme)
        save_webp(splash_orb(theme, icon, rgb), out / "luoshu_splash_orb.webp")
        print(theme, "splash/background colour", "#%02X%02X%02X" % rgb)
        if args.preview:
            args.preview.mkdir(parents=True, exist_ok=True)
            render_shell(theme, 720, 1560, 1.75, icon, CARD_START_SCALE, args.font).save(args.preview / f"shell-{theme}.png")
            splash = Image.new("RGB", (720, 1560), rgb)
            orb = splash_orb(theme, icon, rgb).resize((504, 504), Image.Resampling.LANCZOS)
            circle = Image.new("L", (504, 504), 0)
            ImageDraw.Draw(circle).ellipse([84, 84, 420, 420], fill=255)
            splash.paste(orb, (108, 528), circle)
            splash.save(args.preview / f"splash-{theme}.png")


if __name__ == "__main__":
    main()
