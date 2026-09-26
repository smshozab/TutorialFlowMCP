from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from tutorialflow.storage.workspace import load_project, project_path, save_project
from tutorialflow.tools.get_result import build_thumbnail_brief


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "arialbd.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _wrap_title(draw: ImageDraw.ImageDraw, title: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in title.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textlength(candidate, font=font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _product_mark(name: str | None) -> str:
    if not name:
        return "APP"
    words = [word for word in name.split() if word]
    if len(words) > 1:
        return "".join(word[0] for word in words[:2]).upper()
    return words[0][:2].upper()


def _paste_rounded(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    x0, y0, x1, y1 = box
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), radius=radius, fill=255)
    canvas.paste(image, (x0, y0), mask)


def render_thumbnail(project_id: str, title: str, brand: str = "general",
                     product_name: str | None = None) -> dict:
    brief = build_thumbnail_brief(project_id, title, brand, product_name)
    root = project_path(project_id)
    screenshot = root / brief["evidence_frame_path"]
    colors = brief["brand"].get("colors", {})
    accent = colors.get("accent", "#6AAED6")
    canvas = Image.new("RGB", (1280, 720), "#101827")
    draw = ImageDraw.Draw(canvas)
    # Layered dark panels and restrained accents create depth without imposing a fixed company brand.
    draw.rectangle((0, 0, 1280, 720), fill="#101827")
    draw.polygon([(0, 0), (720, 0), (515, 720), (0, 720)], fill="#172337")
    draw.ellipse((1030, -175, 1460, 250), fill="#1E3550")
    draw.ellipse((-170, 540, 300, 1010), fill="#1A2C42")
    draw.rounded_rectangle((0, 0, 11, 720), radius=5, fill=accent)

    # Product name badge: the name comes from visible recording content; initials are a neutral fallback mark.
    mark = _product_mark(product_name)
    draw.rounded_rectangle((58, 48, 450, 116), radius=24, fill="#202E40", outline="#34445A", width=2)
    draw.rounded_rectangle((70, 59, 116, 105), radius=14, fill=accent)
    mark_font = _font(17)
    mark_box = draw.textbbox((0, 0), mark, font=mark_font)
    draw.text((93 - (mark_box[2] - mark_box[0]) / 2, 82 - (mark_box[3] - mark_box[1]) / 2 - mark_box[1]),
              mark, font=mark_font, fill="#101827")
    label = (product_name or "SOFTWARE TUTORIAL").strip().upper()
    if len(label) > 28:
        label = label[:26].rstrip() + "…"
    draw.text((132, 73), label, font=_font(18), fill="#E5EEF8")

    draw.text((62, 160), "STEP-BY-STEP GUIDE", font=_font(17), fill=accent)
    for size in range(66, 37, -2):
        title_font = _font(size)
        title_lines = _wrap_title(draw, title, title_font, 430)
        if len(title_lines) <= 5 and len(title_lines) * (size + 14) <= 410:
            break
    y = 210
    for line in title_lines[:5]:
        draw.text((60, y), line, font=title_font, fill="#F8FAFC", stroke_width=0)
        y += size + 14
    draw.rounded_rectangle((62, 630, 138, 637), radius=4, fill=accent)
    draw.text((62, 658), "TUTORIAL", font=_font(16), fill="#9FB0C2")

    # Browser-style screenshot card with a soft shadow and full-frame screen content.
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((535, 101, 1237, 628), radius=30, fill=(0, 0, 0, 115))
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((520, 78, 1225, 605), radius=28, fill="#F8FAFC", outline="#FFFFFF", width=2)
    draw.rounded_rectangle((522, 80, 1223, 130), radius=26, fill="#E8EDF3")
    draw.rectangle((522, 105, 1223, 130), fill="#E8EDF3")
    for x, color in ((550, "#F87171"), (573, "#FBBF24"), (596, "#34D399")):
        draw.ellipse((x, 98, x + 12, 110), fill=color)
    draw.rounded_rectangle((635, 92, 1115, 118), radius=13, fill="#F8FAFC")
    draw.text((650, 97), label[:35], font=_font(12), fill="#64748B")

    screen_box = (540, 140, 1205, 585)
    screen_size = (screen_box[2] - screen_box[0], screen_box[3] - screen_box[1])
    screen_bg = Image.new("RGB", screen_size, "#CBD5E1")
    with Image.open(screenshot) as source:
        source = source.convert("RGB")
        # Use a softened, cropped copy as a backdrop, then show the entire source frame over it.
        backdrop = ImageOps.fit(source, screen_size, method=Image.Resampling.LANCZOS)
        backdrop = backdrop.filter(ImageFilter.GaussianBlur(18))
        backdrop = Image.blend(backdrop, Image.new("RGB", screen_size, "#142235"), 0.54)
        screen_bg.paste(backdrop)
        preview = ImageOps.contain(source, (screen_size[0] - 34, screen_size[1] - 34), Image.Resampling.LANCZOS)
        px = (screen_size[0] - preview.width) // 2
        py = (screen_size[1] - preview.height) // 2
        screen_bg.paste(preview, (px, py))
    _paste_rounded(canvas, screen_bg, screen_box, 12)
    target = root / "output" / "thumbnail.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)

    record = load_project(project_id)
    record["thumbnail"] = {"path": "output/thumbnail.png", "title": title, "brand": brand,
                           "product_name": product_name}
    save_project(project_id, record)
    return {"path": "output/thumbnail.png", "width": 1280, "height": 720}
