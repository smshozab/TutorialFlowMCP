from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont, ImageOps

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


def render_thumbnail(project_id: str, title: str, brand: str = "education_global") -> dict:
    brief = build_thumbnail_brief(project_id, title, brand)
    root = project_path(project_id)
    screenshot = root / brief["evidence_frame_path"]
    colors = brief["brand"].get("colors", {})
    primary = colors.get("primary", "#16734A")
    background = colors.get("background", "#F7FCF9")
    canvas = Image.new("RGB", (1280, 720), background)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, 530, 720), fill=primary)
    draw.rounded_rectangle((58, 66, 214, 114), radius=24, fill="#FFFFFF")
    draw.text((78, 79), "TUTORIAL", font=_font(22), fill=primary)

    for size in range(62, 29, -2):
        title_font = _font(size)
        title_lines = _wrap_title(draw, title, title_font, 425)
        if len(title_lines) <= 5 and len(title_lines) * (size + 15) <= 415:
            break
    y = 190
    for line in title_lines[:5]:
        draw.text((58, y), line, font=title_font, fill="#FFFFFF")
        y += size + 15
    brand_name = str(brief["brand"].get("name", "TutorialFlow"))
    draw.text((58, 640), brand_name.upper(), font=_font(20), fill="#FFFFFF")

    draw.rounded_rectangle((560, 102, 1245, 622), radius=20, fill="#DAE5DF")
    draw.rounded_rectangle((552, 94, 1237, 614), radius=20, fill="#FFFFFF")
    with Image.open(screenshot) as source:
        preview = ImageOps.contain(source.convert("RGB"), (645, 475), Image.Resampling.LANCZOS)
        x = 572 + (645 - preview.width) // 2
        y = 114 + (475 - preview.height) // 2
        canvas.paste(preview, (x, y))
    target = root / "output" / "thumbnail.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(target, format="PNG", optimize=True)

    record = load_project(project_id)
    record["thumbnail"] = {"path": "output/thumbnail.png", "title": title, "brand": brand}
    save_project(project_id, record)
    return {"path": "output/thumbnail.png", "width": 1280, "height": 720}
