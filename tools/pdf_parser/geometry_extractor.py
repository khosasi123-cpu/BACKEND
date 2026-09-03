"""
Geometry Extractor (PyMuPDF)
============================
Tugas PyMuPDF di pipeline ini murni geometry: bbox, font, size, color, dan
posisi gambar/drawing per halaman. Ini TIDAK menentukan struktur dokumen
(itu tugas Docling) - hanya menyediakan detail visual presisi supaya nanti
teks terjemahan bisa ditulis ulang dengan tampilan semirip mungkin ke
aslinya.
"""

from dataclasses import dataclass, field

import pymupdf as fitz  # PyMuPDF (pymupdf>=1.24 rekomendasi import ini, bukan `import fitz`)


@dataclass
class TextSpan:
    text: str
    bbox: tuple  # (x0, y0, x1, y1), origin top-left, sama seperti PyMuPDF
    font: str
    size: float
    color: int
    page: int


@dataclass
class PageGeometry:
    page: int
    page_height: float
    page_width: float
    spans: list = field(default_factory=list)
    image_bboxes: list = field(default_factory=list)  # area yang HARUS di-skip dari redaction


def extract_geometry(pdf_path: str) -> list[PageGeometry]:
    doc = fitz.open(pdf_path)
    pages_geometry = []

    for page_idx, page in enumerate(doc):
        spans = []
        raw = page.get_text("dict")
        for block in raw["blocks"]:
            if block["type"] != 0:  # 0 = text block, 1 = image block
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"]
                    if not text.strip():
                        continue
                    spans.append(TextSpan(
                        text=text,
                        bbox=tuple(span["bbox"]),
                        font=span["font"],
                        size=span["size"],
                        color=span["color"],
                        page=page_idx,
                    ))

        # area gambar - jangan pernah disentuh saat redaction/rendering ulang
        image_bboxes = [tuple(img_rect) for img_rect in
                         [page.get_image_bbox(img) for img in page.get_images(full=True)]
                         if img_rect]

        pages_geometry.append(PageGeometry(
            page=page_idx,
            page_height=page.rect.height,
            page_width=page.rect.width,
            spans=spans,
            image_bboxes=image_bboxes,
        ))

    doc.close()
    return pages_geometry


def find_dominant_style(spans: list[TextSpan], target_bbox: tuple) -> dict:
    """
    Cari span PyMuPDF yang overlap dengan bbox suatu translation unit
    (dari Docling), lalu ambil font/size/color yang paling dominan.
    Dipakai oleh unit_builder untuk melengkapi styling tiap unit.
    """
    tx0, ty0, tx1, ty1 = target_bbox
    overlapping = []
    for s in spans:
        sx0, sy0, sx1, sy1 = s.bbox
        # overlap check sederhana (intersection area > 0)
        ix0, iy0 = max(tx0, sx0), max(ty0, sy0)
        ix1, iy1 = min(tx1, sx1), min(ty1, sy1)
        if ix1 > ix0 and iy1 > iy0:
            overlapping.append(s)

    if not overlapping:
        return {"font": "helv", "size": 10.0, "color": 0}

    # ambil span dengan area overlap terbesar sebagai representatif
    overlapping.sort(key=lambda s: (s.bbox[2] - s.bbox[0]) * (s.bbox[3] - s.bbox[1]), reverse=True)
    dominant = overlapping[0]
    return {"font": dominant.font, "size": dominant.size, "color": dominant.color}
