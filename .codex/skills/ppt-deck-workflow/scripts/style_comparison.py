"""Build a side-by-side review of the same approved pages across four IMG treatments."""
from PIL import Image, ImageDraw, ImageFont, ImageOps

from data_regions import validate
from region_artwork import draw_image


def prepare(run_dir, styles, page_count):
    expected = min(2, page_count)
    if not expected or not isinstance(styles, list) or len(styles) != 4:
        raise ValueError("record four visual style samples for the approved contents")
    folder = run_dir / ".workflow/style-samples"
    folder.mkdir(parents=True, exist_ok=True)
    seen_ids, image_paths = set(), set()
    indices = None
    boards = {}
    try:
        label_font = ImageFont.truetype("arial.ttf", 26)
    except OSError:
        label_font = ImageFont.load_default()
    for order, style in enumerate(styles):
        key = style.get("id") if isinstance(style, dict) else None
        if not isinstance(key, str) or not key.strip() or key in seen_ids:
            raise ValueError("give each direction a distinct id")
        seen_ids.add(key)
        pages = style.get("pages")
        if not isinstance(pages, list) or len(pages) != expected:
            raise ValueError(f"{key} needs {expected} representative pages")
        page_set = set()
        for page in pages:
            if not isinstance(page, dict):
                raise ValueError("each sample needs its page, short plan and image path")
            index = page.get("page")
            if type(index) != int or not 1 <= index <= page_count or index in page_set:
                raise ValueError(f"{key} uses an invalid or duplicate page number")
            page_set.add(index)
            if not isinstance(page.get("plan"), str) or not page["plan"].strip():
                raise ValueError(f"{key}, page {index} needs a short page plan")
            path = (run_dir / page["path"]).resolve()
            if path in image_paths:
                raise ValueError("use a separate generated image for each sample")
            image_paths.add(path)
            page["path"] = str(path)
            with Image.open(path) as source:
                sample = source.convert("RGB")
            regions = page.get("data_regions", [])
            if regions:
                validate(regions, f"{key}, page {index}")
                sample = draw_image(sample, regions, style.get("palette_tokens"))
                rendered = folder / f"sample-{order + 1}-p{index}.png"
                sample.save(rendered)
                page["review_image"] = str(rendered)
            if index not in boards:
                boards[index] = Image.new("RGB", (1600, 988), "#ECEDF0")
            board = boards[index]
            col, row = order % 2, order // 2
            x, y = col * 800 + 12, row * 494 + 6
            ImageDraw.Draw(board).text((x, y), key, font=label_font, fill="#1F2832")
            thumb = ImageOps.contain(sample, (776, 446), Image.Resampling.LANCZOS)
            board.paste(thumb, (x + (776 - thumb.width) // 2, y + 34 + (446 - thumb.height) // 2))
        if indices is None:
            indices = page_set
        elif indices != page_set:
            raise ValueError("use the same representative pages in all four directions")
    comparisons = []
    for index, board in sorted(boards.items()):
        path = folder / f"compare-page-{index:02d}.jpg"
        board.save(path, quality=93)
        comparisons.append(str(path))
    return comparisons
