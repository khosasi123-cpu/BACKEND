"""
PDF Renderer
=============

Render translated PDF while preserving the original layout.

Design:

1. Protected units are NEVER redacted or rendered.
2. Normal text uses its original bbox.
3. Table cells use their declared cell bbox as the layout container.
4. Multiple translation units belonging to the same table cell
   are combined into one render job.
5. Table text may wrap naturally.
6. Font size is reduced only when the text genuinely does not fit.
7. Table borders are protected with a small inset.
8. Images and drawings are never directly modified.
"""

import logging

import pymupdf as fitz

from collections import defaultdict
from .unit_builder import TranslationUnit


LOGGER = logging.getLogger(__name__)
TABLE_PADDING_X = 1.5
TABLE_PADDING_Y = 1.0
MIN_TABLE_FONT_SIZE = 7.0
EMERGENCY_TABLE_FONT_SIZE = 6.0
FONT_SIZE_STEP = 0.5


# =====================================================================
# GENERAL HELPERS
# =====================================================================

def _safe_rect(bbox) -> fitz.Rect:
    """Convert bbox into a valid PyMuPDF rectangle."""

    x0, y0, x1, y1 = bbox

    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))

    if x1 <= x0:
        x1 = x0 + 1

    if y1 <= y0:
        y1 = y0 + 1

    return fitz.Rect(x0, y0, x1, y1)


def _union_rect(rects) -> fitz.Rect:
    """Return union of rectangles."""

    if not rects:
        return fitz.Rect()

    result = fitz.Rect(rects[0])

    for rect in rects[1:]:
        result |= rect

    return result


def _clamp_rect(rect: fitz.Rect, bounds: fitz.Rect) -> fitz.Rect:
    """Keep rect inside bounds."""

    result = fitz.Rect(
        max(rect.x0, bounds.x0),
        max(rect.y0, bounds.y0),
        min(rect.x1, bounds.x1),
        min(rect.y1, bounds.y1),
    )

    if result.x1 <= result.x0:
        result.x1 = result.x0 + 1

    if result.y1 <= result.y0:
        result.y1 = result.y0 + 1

    return result


# =====================================================================
# BACKGROUND
# =====================================================================

def _sample_background_color(page: fitz.Page, bbox) -> tuple:
    """
    Estimate background color.

    Prefer light pixels around the interior of the box so that
    text itself is unlikely to become the redaction color.
    """

    try:
        rect = _safe_rect(bbox)

        # Do not render an enormous pixmap unnecessarily.
        clip = rect

        pix = page.get_pixmap(
            clip=clip,
            matrix=fitz.Matrix(1, 1),
            alpha=False,
        )

        if pix.width <= 2 or pix.height <= 2:
            return (1, 1, 1)

        samples = []

        points = [
            (2, 2),
            (pix.width - 3, 2),
            (2, pix.height - 3),
            (pix.width - 3, pix.height - 3),
            (pix.width // 2, 2),
            (pix.width // 2, pix.height - 3),
            (2, pix.height // 2),
            (pix.width - 3, pix.height // 2),
        ]

        for x, y in points:
            if 0 <= x < pix.width and 0 <= y < pix.height:
                r, g, b = pix.pixel(x, y)[:3]
                samples.append((r, g, b))

        if not samples:
            return (1, 1, 1)

        # Prefer light pixels.
        samples.sort(
            key=lambda c: c[0] + c[1] + c[2],
            reverse=True,
        )

        r, g, b = samples[0]

        return (
            r / 255,
            g / 255,
            b / 255,
        )

    except Exception:
        return (1, 1, 1)


# =====================================================================
# FONT FITTING
# =====================================================================

def _estimate_text_width(text: str, fontsize: float) -> float:
    """Approximate width of text."""

    if not text:
        return 0.0

    try:
        return fitz.get_text_length(
            text,
            fontname="helv",
            fontsize=fontsize,
        )
    except Exception:
        return len(text) * fontsize * 0.5


def _estimate_lines(text: str, width: float, fontsize: float) -> int:
    """
    Rough estimate of wrapped lines.

    This is intentionally conservative. PyMuPDF remains the
    final authority through insert_textbox().
    """

    if not text:
        return 1

    width = max(width, 1)

    paragraphs = text.split("\n")

    total_lines = 0

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            total_lines += 1
            continue

        estimated_width = _estimate_text_width(
            paragraph,
            fontsize,
        )

        total_lines += max(
            1,
            int(estimated_width / width) + 1,
        )

    return total_lines


def _fit_font_size(
    text: str,
    rect: fitz.Rect,
    start_size: float,
    min_size: float = 5.0,
) -> float:
    """
    Find a reasonable font size.

    IMPORTANT:

    We do not immediately shrink the text.

    Start with the original font size and only reduce it when
    the estimated content genuinely cannot fit inside the cell.
    """

    if not text:
        return start_size

    width = max(rect.width - 3, 1)
    height = max(rect.height - 2, 1)

    size = max(float(start_size), min_size)

    while size > min_size:

        lines = _estimate_lines(
            text,
            width,
            size,
        )

        estimated_height = lines * size * 1.20

        if estimated_height <= height:
            return size

        size -= 0.5

    return min_size


def _insert_textbox_flexible(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    fontsize: float,
    color: tuple,
    min_size: float = 4.0,
) -> float | None:
    """
    Insert text.

    Try the requested size first, then reduce in small steps. Because
    ``insert_textbox`` is all-or-nothing, the first successful candidate is
    the largest font size that actually fits the available rectangle.
    """

    if not text:
        return float(fontsize)

    start_size = float(fontsize)
    floor = min(start_size, float(min_size))
    size = start_size

    while True:

        result = page.insert_textbox(
            rect,
            text,
            fontsize=size,
            fontname="helv",
            color=color,
            align=0,
        )

        if result >= 0:
            return size

        if size <= floor:
            break

        size = max(floor, size - FONT_SIZE_STEP)

    return None


# =====================================================================
# TABLE LAYOUT
# =====================================================================

def _inset_rect(rect: fitz.Rect, x_padding: float, y_padding: float) -> fitz.Rect:
    """Return an inset rectangle without collapsing a very small cell."""

    padded = fitz.Rect(
        rect.x0 + x_padding,
        rect.y0 + y_padding,
        rect.x1 - x_padding,
        rect.y1 - y_padding,
    )

    if padded.width <= 1 or padded.height <= 1:
        return fitz.Rect(rect)

    return padded


def _table_cell_container(cell_units: list[TranslationUnit]) -> fitz.Rect:
    """Return the declared cell container for a logical table cell.

    Docling's per-cell bbox is authoritative. If one logical cell produced
    multiple translation units, their union remains inside that one cell and
    becomes the common layout container. No neighbour-based inference is used.
    """

    return _union_rect([_safe_rect(unit.bbox) for unit in cell_units])


# =====================================================================
# IMAGE PROTECTION
# =====================================================================

def _get_image_rectangles(page: fitz.Page) -> list[fitz.Rect]:
    """Return every embedded-image placement on *page*.

    ``get_image_info`` supplies the displayed geometry, including images with
    multiple placements. ``get_image_rects`` is retained as a fallback for
    PDFs whose image info is incomplete. The renderer uses these rectangles
    solely as immutable exclusion regions; it never redraws an image.
    """

    rectangles = []
    seen = set()

    def add_rect(value) -> None:
        try:
            rect = fitz.Rect(value)
        except (TypeError, ValueError):
            return

        if rect.width <= 0 or rect.height <= 0:
            return

        key = tuple(round(coordinate, 3) for coordinate in rect)

        if key not in seen:
            seen.add(key)
            rectangles.append(rect)

    try:
        for image_info in page.get_image_info(xrefs=True):
            add_rect(image_info.get("bbox"))
    except Exception:
        pass

    try:
        for image in page.get_images(full=True):
            try:
                image_rects = page.get_image_rects(image)
            except Exception:
                image_rects = [page.get_image_bbox(image)]

            for image_rect in image_rects:
                add_rect(image_rect)
    except Exception:
        pass

    return rectangles


def _belongs_to_image(bbox, image_rectangles: list[fitz.Rect]) -> bool:
    """Whether a text unit may belong to an embedded image.

    Full containment is the normal case. A non-trivial overlap is treated as
    image-owned too: skipping an occasional boundary unit is preferable to
    modifying even a small part of an immutable screenshot. The tiny area
    tolerance avoids classifying edge-only floating-point contact as overlap.
    """

    if not image_rectangles:
        return False

    unit_rect = _safe_rect(bbox)
    unit_area = max(unit_rect.get_area(), 0.01)

    for image_rect in image_rectangles:
        if (
            unit_rect.x0 >= image_rect.x0 - 0.5
            and unit_rect.y0 >= image_rect.y0 - 0.5
            and unit_rect.x1 <= image_rect.x1 + 0.5
            and unit_rect.y1 <= image_rect.y1 + 0.5
        ):
            return True

        overlap = unit_rect & image_rect
        overlap_area = overlap.get_area()

        if overlap_area > 0.01 and overlap_area / unit_area >= 0.01:
            return True

    return False


# =====================================================================
# MAIN RENDERER
# =====================================================================

def render_translated_pdf(
    input_pdf: str,
    units: list[TranslationUnit],
    output_pdf: str,
):
    """
    Render translated PDF.

    Normal text:
        original text bbox

    Table cell:
        its Docling-provided cell bbox

    Protected:
        completely untouched
    """

    doc = fitz.open(input_pdf)

    # ---------------------------------------------------------------
    # Group by page.
    # ---------------------------------------------------------------

    units_by_page = defaultdict(list)

    for unit in units:
        units_by_page[unit.page].append(unit)

    # ---------------------------------------------------------------
    # Process pages.
    # ---------------------------------------------------------------

    for page_idx, page in enumerate(doc):

        page_units = units_by_page.get(
            page_idx,
            [],
        )

        if not page_units:
            continue

        # -----------------------------------------------------------
        # Protected units and image-owned units NEVER participate in
        # rendering. This filtering must happen before redaction so image
        # pixels can never be blanked and then left without replacement.
        # -----------------------------------------------------------

        image_rectangles = _get_image_rectangles(page)

        render_units = [
            unit
            for unit in page_units
            if (
                not unit.protected
                and not _belongs_to_image(unit.bbox, image_rectangles)
            )
        ]

        if not render_units:
            continue

        # -----------------------------------------------------------
        # Build render jobs.
        # -----------------------------------------------------------

        table_groups = defaultdict(list)
        normal_units = []

        for unit in render_units:

            if unit.unit_type == "table_cell":

                if (
                    unit.table_id is not None
                    and unit.row is not None
                    and unit.col is not None
                ):
                    key = (
                        unit.page,
                        unit.table_id,
                        unit.row,
                        unit.col,
                    )
                else:
                    # Keep a table cell on the cell-layout path even when
                    # extraction did not supply complete grid metadata.
                    key = ("unkeyed", unit.id)

                table_groups[key].append(unit)

            else:

                normal_units.append(unit)

        jobs = []

        # -----------------------------------------------------------
        # TABLE JOBS
        # -----------------------------------------------------------

        for key, cell_units in table_groups.items():

            texts = []

            for unit in cell_units:

                text = (
                    unit.translated_text
                    or unit.original_text
                )

                if text and text.strip():
                    texts.append(
                        text.strip()
                    )

            if not texts:
                continue

            combined_text = "\n".join(texts)

            first = cell_units[0]
            cell_box = _table_cell_container(cell_units)

            jobs.append(
                {
                    "units": cell_units,
                    "text": combined_text,
                    "box": _inset_rect(
                        cell_box,
                        TABLE_PADDING_X,
                        TABLE_PADDING_Y,
                    ),
                    "cell_box": cell_box,
                    # Keep source regions separate from the layout box.
                    # This lets us remove the original text without using a
                    # neighbouring cell as redaction space.
                    "redaction_boxes": [
                        _safe_rect(unit.bbox)
                        for unit in cell_units
                    ],
                    "fontsize": max(
                        float(unit.font_size)
                        for unit in cell_units
                    ),
                    "color": first.color,
                    "type": "table",
                    "table_ref": (
                        f"page {first.page + 1}, table {first.table_id}, "
                        f"row {first.row}, col {first.col}"
                    ),
                }
            )

        # -----------------------------------------------------------
        # NORMAL TEXT JOBS
        # -----------------------------------------------------------

        for unit in normal_units:

            text = (
                unit.translated_text
                or unit.original_text
            )

            if not text:
                continue

            jobs.append(
                {
                    "units": [unit],
                    "text": text,
                    "box": _safe_rect(unit.bbox),
                    "redaction_boxes": [_safe_rect(unit.bbox)],
                    "fontsize": float(unit.font_size),
                    "color": unit.color,
                    "type": "normal",
                }
            )

        if not jobs:
            continue

        # -----------------------------------------------------------
        # REDACTION
        # -----------------------------------------------------------

        redaction_jobs = []

        for job in jobs:
            seen_boxes = set()

            for source_box in job["redaction_boxes"]:
                # Redact source text areas only. For table jobs this remains
                # independent from the larger cell layout container.
                redact_box = _inset_rect(source_box, 0.8, 0.8)
                box_key = tuple(round(value, 3) for value in redact_box)

                if box_key in seen_boxes:
                    continue

                seen_boxes.add(box_key)
                bg = _sample_background_color(page, tuple(redact_box))
                page.add_redact_annot(redact_box, fill=bg)

            redaction_jobs.append(job)

        # Preserve image and drawing objects. Redaction is limited to the
        # text regions added above, never to a detected table border itself.
        page.apply_redactions(images=0, graphics=0)

        # -----------------------------------------------------------
        # INSERT TRANSLATIONS
        # -----------------------------------------------------------

        for job in redaction_jobs:

            text = job["text"]
            rect = job["box"]

            color_value = job["color"]

            r = (
                (color_value >> 16) & 255
            ) / 255

            g = (
                (color_value >> 8) & 255
            ) / 255

            b = (
                color_value & 255
            ) / 255

            text_color = (
                r,
                g,
                b,
            )

            # =======================================================
            # TABLE CELL
            # =======================================================

            if job["type"] == "table":

                # ---------------------------------------------------
                # First attempt:
                # original font size.
                #
                # This is the important change.
                # Do NOT aggressively shrink before trying.
                # ---------------------------------------------------

                success = _insert_textbox_flexible(
                    page,
                    rect,
                    text,
                    job["fontsize"],
                    text_color,
                    min_size=MIN_TABLE_FONT_SIZE,
                )

                if success:
                    continue

                # At this point the translation did not fit at the minimum
                # readable size. Give it the remaining in-cell padding before
                # reporting the failure; never expand into another cell.
                LOGGER.warning(
                    "Table cell %s does not fit at %.1fpt; "
                    "trying the full cell interior at %.1fpt.",
                    job["table_ref"],
                    MIN_TABLE_FONT_SIZE,
                    EMERGENCY_TABLE_FONT_SIZE,
                )

                emergency_rect = _inset_rect(
                    job["cell_box"],
                    0.4,
                    0.2,
                )

                success = _insert_textbox_flexible(
                    page,
                    emergency_rect,
                    text,
                    EMERGENCY_TABLE_FONT_SIZE,
                    text_color,
                    min_size=EMERGENCY_TABLE_FONT_SIZE,
                )

                if not success:
                    LOGGER.warning(
                        "Table cell %s could not render its "
                        "translation inside the declared cell bbox.",
                        job["table_ref"],
                    )

                continue

            # =======================================================
            # NORMAL TEXT
            # =======================================================

            fitted_size = _fit_font_size(
                text,
                rect,
                job["fontsize"],
                min_size=5.0,
            )

            success = _insert_textbox_flexible(
                page,
                rect,
                text,
                fitted_size,
                text_color,
                min_size=5.0,
            )

            if success:
                continue

            # -------------------------------------------------------
            # Normal-text fallback.
            #
            # Only vertical relaxation.
            # Do not modify table cells.
            # -------------------------------------------------------

            expanded_rect = fitz.Rect(
                rect.x0,
                rect.y0,
                rect.x1,
                rect.y1 + max(
                    rect.height * 0.5,
                    fitted_size * 2,
                ),
            )

            _insert_textbox_flexible(
                page,
                expanded_rect,
                text,
                max(
                    fitted_size - FONT_SIZE_STEP,
                    4.0,
                ),
                text_color,
                min_size=4.0,
            )

    # ---------------------------------------------------------------
    # SAVE
    # ---------------------------------------------------------------

    doc.save(
        output_pdf,
        garbage=4,
        deflate=True,
    )

    doc.close()
