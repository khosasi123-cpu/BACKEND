"""
Translation Unit Builder
========================

Menggabungkan output Docling (struktur/semantik) dengan output PyMuPDF
(geometry/styling), lalu menghasilkan TranslationUnit final.

Protected unit ditentukan HANYA berdasarkan isi teks.
Label struktur dan frekuensi kemunculan tidak menentukan protection.

Untuk table_cell:
- Docling bbox dipakai sebagai referensi posisi/struktur.
- Geometry PyMuPDF digunakan untuk memperluas bbox jika tight text bbox
  terlalu kecil untuk kebutuhan rendering terjemahan.
- Bbox tidak boleh berubah menjadi table-wide bbox.

Tujuan:
- menjaga struktur PDF;
- memberikan renderer area yang cukup untuk teks hasil terjemahan;
- mencegah "TEXT DOES NOT FIT" sebanyak mungkin;
- tidak mengubah logic protected dari Step 1.
"""

import re
from dataclasses import dataclass

from .geometry_extractor import PageGeometry, find_dominant_style
from .structure_extractor import StructureItem


# ============================================================
# PROTECTED TEXT REGEX
# ============================================================

RE_DOC_IDENTIFIER = re.compile(
    r"^[A-Z0-9]+(-[A-Z0-9]+){3,}$"
)

RE_PAGE_NUMBER = re.compile(
    r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$",
    re.I,
)

RE_DATE = re.compile(
    r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$|"
    r"^\d{1,2}\s+"
    r"(jan|feb|mar|apr|mei|may|jun|jul|agu|aug|sep|okt|oct|nov|des|dec)"
    r"\w*\s+\d{2,4}$",
    re.I,
)

RE_REVISION_CODE = re.compile(
    r"^(rev\.?|revision)\s*[:\-]?\s*\w+$",
    re.I,
)

RE_URL = re.compile(
    r"^[a-zA-Z][a-zA-Z0-9+.\-]*://\S+$"
)

RE_FILE_PATH = re.compile(
    r"^("
    r"[A-Za-z]:[\\/]\S*"
    r"|\.{0,2}/\S+"
    r"|[^\\/\s]+\.[A-Za-z]{1,4}([\\/]|$)"
    r")"
)

RE_TECH_CODE = re.compile(
    r"^[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*[0-9][A-Za-z0-9]*$"
)

RE_BARE_NUMBER = re.compile(
    r"^-?[\d,]+(?:\.\d+)?$"
)

RE_PUNCT_ONLY = re.compile(
    r"^[\-–—•:.;,()\[\]{}|/\\@*_#&%=+^~`\s]+$"
)

RE_URL_ANYWHERE = re.compile(
    r"[a-zA-Z][a-zA-Z0-9+.\-]*://\S+"
)


def _is_url_or_path(text: str) -> bool:
    """
    True jika seluruh teks merupakan URL/path, atau teks sangat didominasi
    URL.
    """
    t = text.strip()

    if not t:
        return True

    if RE_URL.match(t):
        return True

    if RE_FILE_PATH.match(t):
        return True

    match = RE_URL_ANYWHERE.search(t)

    if match:
        stripped = t.replace(match.group(0), "").strip()

        if len(stripped) <= 8:
            return True

    return False


def _looks_protected(text: str) -> bool:
    """
    Protection ditentukan HANYA dari isi teks.

    Tidak menggunakan:
    - structure label
    - page_header/page_footer
    - frekuensi kemunculan
    """

    t = text.strip()

    if not t:
        return True

    if RE_DOC_IDENTIFIER.match(t):
        return True

    if RE_PAGE_NUMBER.match(t):
        return True

    if RE_DATE.match(t):
        return True

    if RE_REVISION_CODE.match(t):
        return True

    if _is_url_or_path(t):
        return True

    if RE_BARE_NUMBER.match(t):
        return True

    if RE_PUNCT_ONLY.match(t):
        return True

    if (
        len(t) >= 5
        and " " not in t
        and RE_TECH_CODE.match(t)
    ):
        return True

    return False


# ============================================================
# TRANSLATION UNIT
# ============================================================

@dataclass
class TranslationUnit:
    id: str
    page: int
    bbox: tuple
    original_text: str

    font: str
    font_size: float
    color: int

    unit_type: str

    table_id: str | None = None
    row: int | None = None
    col: int | None = None

    protected: bool = False

    translated_text: str = ""


# ============================================================
# GEOMETRY HELPERS
# ============================================================

def _normalize_bbox(bbox):
    """
    Normalize bbox menjadi:

        (x0, y0, x1, y1)

    dengan x0 <= x1 dan y0 <= y1.
    """

    if bbox is None:
        return None

    try:
        x0, y0, x1, y1 = bbox

        x0 = float(x0)
        y0 = float(y0)
        x1 = float(x1)
        y1 = float(y1)

        return (
            min(x0, x1),
            min(y0, y1),
            max(x0, x1),
            max(y0, y1),
        )

    except (TypeError, ValueError):
        return None


def _bbox_area(bbox):
    bbox = _normalize_bbox(bbox)

    if bbox is None:
        return 0.0

    x0, y0, x1, y1 = bbox

    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _bbox_intersection(a, b):
    """
    Return intersection bbox atau None.
    """

    a = _normalize_bbox(a)
    b = _normalize_bbox(b)

    if a is None or b is None:
        return None

    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b

    x0 = max(ax0, bx0)
    y0 = max(ay0, by0)
    x1 = min(ax1, bx1)
    y1 = min(ay1, by1)

    if x1 <= x0 or y1 <= y0:
        return None

    return (x0, y0, x1, y1)


def _bbox_iou(a, b):
    """
    IoU sederhana antara dua bbox.
    """

    intersection = _bbox_intersection(a, b)

    if intersection is None:
        return 0.0

    inter_area = _bbox_area(intersection)

    union = (
        _bbox_area(a)
        + _bbox_area(b)
        - inter_area
    )

    if union <= 0:
        return 0.0

    return inter_area / union


def _bbox_contains(outer, inner, tolerance=1.0):
    """
    Apakah inner berada di dalam outer dengan tolerance.
    """

    outer = _normalize_bbox(outer)
    inner = _normalize_bbox(inner)

    if outer is None or inner is None:
        return False

    ox0, oy0, ox1, oy1 = outer
    ix0, iy0, ix1, iy1 = inner

    return (
        ix0 >= ox0 - tolerance
        and iy0 >= oy0 - tolerance
        and ix1 <= ox1 + tolerance
        and iy1 <= oy1 + tolerance
    )


def _expand_bbox(
    bbox,
    left=0.0,
    top=0.0,
    right=0.0,
    bottom=0.0,
):
    """
    Expand bbox.
    """

    bbox = _normalize_bbox(bbox)

    if bbox is None:
        return None

    x0, y0, x1, y1 = bbox

    return (
        x0 - left,
        y0 - top,
        x1 + right,
        y1 + bottom,
    )


# ============================================================
# EXTRACT PYMuPDF SPANS
# ============================================================

def _get_page_spans(page_geometry: PageGeometry):
    """
    Mengambil span geometry PyMuPDF.

    Karena struktur PageGeometry dapat berbeda antar versi implementasi,
    helper ini dibuat tolerant.
    """

    if page_geometry is None:
        return []

    spans = getattr(page_geometry, "spans", None)

    if spans is None:
        return []

    return spans


def _span_bbox(span):
    """
    Ambil bbox dari span geometry.
    """

    if span is None:
        return None

    bbox = getattr(span, "bbox", None)

    if bbox is not None:
        return _normalize_bbox(bbox)

    if isinstance(span, dict):
        bbox = span.get("bbox")

        if bbox is not None:
            return _normalize_bbox(bbox)

    return None


# ============================================================
# TABLE CELL GEOMETRY
# ============================================================

def _find_cell_text_bbox(
    cell_bbox,
    page_geometry,
    min_iou=0.05,
):
    """
    Cari bbox geometry PyMuPDF yang berhubungan dengan cell.

    Penting:
    Kita TIDAK menggunakan table bbox.

    Hanya span teks yang:
    - intersect dengan cell bbox
    - atau cukup dekat dengan cell bbox

    Hasil berupa union dari span-span tersebut.

    Jika tidak ditemukan, None dikembalikan sehingga caller tetap
    menggunakan bbox Docling.
    """

    cell_bbox = _normalize_bbox(cell_bbox)

    if cell_bbox is None:
        return None

    spans = _get_page_spans(page_geometry)

    if not spans:
        return None

    matching = []

    for span in spans:
        span_bbox = _span_bbox(span)

        if span_bbox is None:
            continue

        intersection = _bbox_intersection(
            cell_bbox,
            span_bbox,
        )

        if intersection is None:
            continue

        iou = _bbox_iou(
            cell_bbox,
            span_bbox,
        )

        # Span yang benar-benar berada di dalam cell
        # biasanya punya intersection besar terhadap span-nya.
        if (
            _bbox_contains(cell_bbox, span_bbox, tolerance=2.0)
            or iou >= min_iou
        ):
            matching.append(span_bbox)

    if not matching:
        return None

    x0 = min(b[0] for b in matching)
    y0 = min(b[1] for b in matching)
    x1 = max(b[2] for b in matching)
    y1 = max(b[3] for b in matching)

    return (x0, y0, x1, y1)


def _build_table_cell_bbox(
    docling_bbox,
    page_geometry,
):
    """
    Menentukan bbox final untuk table cell.

    Prinsip penting:

    Docling bbox = authoritative location.

    PyMuPDF spans = membantu mengetahui area teks aktual.

    Kita tidak menggunakan PyMuPDF table bbox.

    Karena tujuan renderer adalah menyediakan ruang untuk hasil
    translation, bbox diperluas sedikit dari text bbox, tetapi tidak
    boleh mengambil seluruh area tabel.
    """

    docling_bbox = _normalize_bbox(docling_bbox)

    if docling_bbox is None:
        return None

    text_bbox = _find_cell_text_bbox(
        docling_bbox,
        page_geometry,
    )

    if text_bbox is None:
        return docling_bbox

    # Jangan mengganti bbox Docling dengan bbox PyMuPDF secara penuh.
    #
    # Docling sudah memberikan cell text region yang benar.
    # Kita hanya gunakan span geometry untuk memastikan area teks
    # aktual tidak terpotong.

    x0 = min(docling_bbox[0], text_bbox[0])
    y0 = min(docling_bbox[1], text_bbox[1])
    x1 = max(docling_bbox[2], text_bbox[2])
    y1 = max(docling_bbox[3], text_bbox[3])

    merged = (x0, y0, x1, y1)

    # Berikan sedikit breathing room untuk rendering.
    #
    # Jangan terlalu besar karena cell yang bersebelahan bisa overlap.
    merged = _expand_bbox(
        merged,
        left=1.0,
        top=0.5,
        right=1.0,
        bottom=0.5,
    )

    return merged


# ============================================================
# UNIT TYPE
# ============================================================

def _resolve_unit_type(label: str) -> str:
    """
    Mapping structure label -> translation unit type.
    """

    if label == "table_cell":
        return "table_cell"

    if (
        "header" in label.lower()
        and label != "page_header"
    ):
        return "heading"

    return label


# ============================================================
# MAIN BUILDER
# ============================================================

def build_translation_units(
    structure_items: list[StructureItem],
    pages_geometry: list[PageGeometry],
    total_pages: int,
) -> list[TranslationUnit]:
    """
    Build final TranslationUnit list.

    Step 1 protection logic dipertahankan.

    Step 2 geometry:
    - non-table tetap memakai Docling bbox;
    - table_cell mendapatkan bbox yang sedikit diperluas berdasarkan
      geometry teks PyMuPDF;
    - table-wide bbox tidak pernah digunakan.
    """

    geometry_by_page = {
        pg.page: pg
        for pg in pages_geometry
    }

    units = []

    for item in structure_items:

        page_geometry = geometry_by_page.get(item.page)

        if page_geometry is None:
            spans = []
        else:
            spans = getattr(page_geometry, "spans", [])

        # --------------------------------------------------------
        # Style
        # --------------------------------------------------------

        style = find_dominant_style(
            spans,
            item.bbox,
        )

        # --------------------------------------------------------
        # Protection
        # --------------------------------------------------------

        is_protected = _looks_protected(
            item.text
        )

        # --------------------------------------------------------
        # Unit type
        # --------------------------------------------------------

        unit_type = _resolve_unit_type(
            item.label
        )

        # --------------------------------------------------------
        # BBOX
        # --------------------------------------------------------

        original_bbox = _normalize_bbox(
            item.bbox
        )

        final_bbox = original_bbox

        if (
            unit_type == "table_cell"
            and not is_protected
        ):
            final_bbox = _build_table_cell_bbox(
                original_bbox,
                page_geometry,
            )

        # Safety fallback
        if final_bbox is None:
            final_bbox = original_bbox

        # --------------------------------------------------------
        # TranslationUnit
        # --------------------------------------------------------

        units.append(
            TranslationUnit(
                id=item.id,
                page=item.page,
                bbox=final_bbox,
                original_text=item.text,

                font=style["font"],
                font_size=style["size"],
                color=style["color"],

                unit_type=unit_type,

                table_id=item.table_id,
                row=item.row,
                col=item.col,

                protected=is_protected,

                # Protected unit tetap kosong.
                # Translator hanya mengisi non-protected.
                translated_text="",
            )
        )

    return units