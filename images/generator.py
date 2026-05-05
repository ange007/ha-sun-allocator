#!/usr/bin/env python3
"""
SunAllocator HACS image generator
Requires: pip install Pillow
Usage: python generate_hacs_images.py
Place logo.jpg and icon.ico (or icon.png/icon.jpg) in the project root.
"""

from pathlib import Path
from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = Path(BASE_DIR).resolve().parent / "custom_components/sun_allocator/brand"

LIGHT_BG = (255, 255, 255, 255)
DARK_BG = (28, 28, 30, 255)

GENERATE_DARK_VARIANTS = False
GENERATE_TRANSPARENT_VARIANTS = False
UPSCALE_IMAGES = True

# Background modes: "full", "circle", "transparent"
LIGHT_ICON_BG_MODE = "transparent"
DARK_ICON_BG_MODE = "circle"
LIGHT_LOGO_BG_MODE = "transparent"
DARK_LOGO_BG_MODE = "full"

FULL_BG_CONTENT_SCALE = 1.00
CIRCLE_BG_CONTENT_SCALE = 0.78
TRANSPARENT_BG_CONTENT_SCALE = 1.00
CIRCLE_DIAMETER_RATIO = 0.92


def remove_white_matte(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    out = Image.new("RGBA", img.size)
    src = img.load()
    dst = out.load()
    w, h = img.size

    for y in range(h):
        for x in range(w):
            r, g, b, a0 = src[x, y]

            if a0 == 0:
                dst[x, y] = (0, 0, 0, 0)
                continue

            alpha = 255 - min(r, g, b)
            if alpha <= 0:
                dst[x, y] = (0, 0, 0, 0)
                continue

            def unblend(c: int) -> int:
                value = (c - (255 - alpha)) * 255 / alpha
                return max(0, min(255, int(round(value))))

            dst[x, y] = (unblend(r), unblend(g), unblend(b), alpha)

    return out


def load_icon(path_no_ext: Path) -> Image.Image:
    for ext in (".ico", ".png", ".jpg", ".jpeg"):
        path = path_no_ext.with_suffix(ext)
        if path.exists():
            img = Image.open(path)

            if hasattr(img, "ico") and img.ico is not None:
                sizes = img.ico.sizes()
                if sizes:
                    largest = max(sizes, key=lambda s: s[0] * s[1])
                    img = img.ico.getimage(largest)

            print(f"  loaded {path}  original size: {img.size}")
            return img.convert("RGBA")

    raise FileNotFoundError(f"No icon file found for base name: {path_no_ext}")


def load_logo(path_no_ext: Path) -> Image.Image:
    for ext in (".png", ".jpg", ".jpeg", ".ico"):
        path = path_no_ext.with_suffix(ext)
        if path.exists():
            img = Image.open(path)

            if hasattr(img, "ico") and img.ico is not None:
                sizes = img.ico.sizes()
                if sizes:
                    largest = max(sizes, key=lambda s: s[0] * s[1])
                    img = img.ico.getimage(largest)

            print(f"  loaded {path}  original size: {img.size}")
            return img.convert("RGBA")

    raise FileNotFoundError(f"No logo file found for base name: {path_no_ext}")


def square_canvas(
    img: Image.Image,
    size: int,
    bg=(0, 0, 0, 0),
    upscale: bool = UPSCALE_IMAGES,
    content_scale: float = 1.0,
) -> Image.Image:
    img = img.copy()
    src_w, src_h = img.size
    fit_size = max(1, int(round(size * content_scale)))

    if upscale:
        scale = min(fit_size / src_w, fit_size / src_h)
        new_size = (
            max(1, int(round(src_w * scale))),
            max(1, int(round(src_h * scale))),
        )
        img = img.resize(new_size, Image.LANCZOS)
    else:
        img.thumbnail((fit_size, fit_size), Image.LANCZOS)

    canvas = Image.new("RGBA", (size, size), bg)
    offset = ((size - img.width) // 2, (size - img.height) // 2)
    canvas.paste(img, offset, img)
    return canvas


def make_circle_background(size: int, color, diameter_ratio: float = CIRCLE_DIAMETER_RATIO) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    diameter = int(round(size * diameter_ratio))
    left = (size - diameter) // 2
    top = (size - diameter) // 2
    right = left + diameter - 1
    bottom = top + diameter - 1
    draw.ellipse((left, top, right, bottom), fill=color)
    return canvas


def render_variant(img: Image.Image, size: int, mode: str, bg_color) -> Image.Image:
    mode = mode.lower()

    if mode == "circle":
        content_scale = CIRCLE_BG_CONTENT_SCALE
    elif mode == "transparent":
        content_scale = TRANSPARENT_BG_CONTENT_SCALE
    else:
        content_scale = FULL_BG_CONTENT_SCALE

    staged = square_canvas(img, size, LIGHT_BG, UPSCALE_IMAGES, content_scale)
    fg = remove_white_matte(staged)

    if mode == "transparent":
        return fg

    if mode == "circle":
        bg = make_circle_background(size, bg_color)
        bg.alpha_composite(fg)
        return bg

    bg = Image.new("RGBA", (size, size), bg_color)
    bg.alpha_composite(fg)
    return bg


def save_png(img: Image.Image, filename: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUT_DIR / filename
    img.convert("RGBA").save(output_path, "PNG", optimize=True)
    print(f"  ✓  {output_path}  ({img.size[0]}×{img.size[1]})")


def main() -> None:
    icon_src = load_icon(BASE_DIR / "icon")
    logo_src = load_logo(BASE_DIR / "logo")

    print("\\nGenerating light variants...")
    save_png(render_variant(icon_src, 256, LIGHT_ICON_BG_MODE, LIGHT_BG), "icon.png")
    save_png(render_variant(icon_src, 512, LIGHT_ICON_BG_MODE, LIGHT_BG), "icon@2x.png")
    save_png(render_variant(logo_src, 256, LIGHT_LOGO_BG_MODE, LIGHT_BG), "logo.png")
    save_png(render_variant(logo_src, 512, LIGHT_LOGO_BG_MODE, LIGHT_BG), "logo@2x.png")

    if GENERATE_TRANSPARENT_VARIANTS:
        print("\\nGenerating transparent variants...")
        save_png(render_variant(icon_src, 256, "transparent", LIGHT_BG), "transparent_icon.png")
        save_png(render_variant(icon_src, 512, "transparent", LIGHT_BG), "transparent_icon@2x.png")
        save_png(render_variant(logo_src, 256, "transparent", LIGHT_BG), "transparent_logo.png")
        save_png(render_variant(logo_src, 512, "transparent", LIGHT_BG), "transparent_logo@2x.png")

    if GENERATE_DARK_VARIANTS:
        print("\\nGenerating dark variants...")
        save_png(render_variant(icon_src, 256, DARK_ICON_BG_MODE, DARK_BG), "dark_icon.png")
        save_png(render_variant(icon_src, 512, DARK_ICON_BG_MODE, DARK_BG), "dark_icon@2x.png")
        save_png(render_variant(logo_src, 256, DARK_LOGO_BG_MODE, DARK_BG), "dark_logo.png")
        save_png(render_variant(logo_src, 512, DARK_LOGO_BG_MODE, DARK_BG), "dark_logo@2x.png")

    print("\\nImage generation completed successfully!")


if __name__ == "__main__":
    main()
