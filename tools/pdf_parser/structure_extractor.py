"""
Structure Extractor (Docling)
==============================
Docling bertugas memahami STRUKTUR dokumen: mana heading, paragraph,
table cell, header/footer, dan reading order yang benar (termasuk untuk
tabel multi-kolom yang urutannya tidak selalu top-to-bottom sederhana).

PyMuPDF tidak tahu "ini judul" vs "ini isi tabel" - dia cuma tahu koordinat.
Docling yang mengisi kekosongan itu.

Catatan versi: API Docling bisa berubah antar versi. Kode ini ditulis untuk
docling>=2.0. Kalau ada breaking change, cek docs terbaru di
https://docling-project.github.io/docling/
"""

from dataclasses import dataclass

from docling.document_converter import DocumentConverter


@dataclass
class StructureItem:
    id: str
    page: int  # 0-indexed, disamakan dengan PyMuPDF
    bbox: tuple  # (x0, y0, x1, y1), TOP-LEFT origin (disamakan dgn PyMuPDF)
    text: str
    label: str  # "section_header", "paragraph", "page_header", "page_footer",
                # "table_cell", "caption", "footnote", "list_item", dst
    table_id: str | None = None
    row: int | None = None
    col: int | None = None


def _bbox_to_top_left(bbox, page_height: float) -> tuple:
    """Docling bbox default origin bisa BOTTOMLEFT (standar PDF spec).
    PyMuPDF pakai TOPLEFT. Normalisasi di sini supaya semua modul lain
    konsisten pakai satu sistem koordinat (top-left)."""
    try:
        # docling_core BoundingBox punya helper resmi untuk ini
        tl = bbox.to_top_left_origin(page_height=page_height)
        return (tl.l, tl.t, tl.r, tl.b)
    except AttributeError:
        # fallback manual kalau versi docling berbeda / bbox sudah top-left
        l, t, r, b = bbox.l, bbox.t, bbox.r, bbox.b
        return (l, t, r, b)


def extract_structure(pdf_path: str) -> list[StructureItem]:
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    doc = result.document

    items: list[StructureItem] = []
    counter = 0

    # --- teks (paragraph, heading, header/footer, caption, dll) ---
    for text_item in doc.texts:
        for prov in text_item.prov:
            page_no = prov.page_no - 1  # docling 1-indexed -> samakan ke 0-indexed
            page_size = doc.pages[prov.page_no].size
            bbox = _bbox_to_top_left(prov.bbox, page_size.height)

            counter += 1
            items.append(StructureItem(
                id=f"u{counter}",
                page=page_no,
                bbox=bbox,
                text=text_item.text,
                label=str(text_item.label),
            ))

    # --- tabel: tiap cell jadi translation unit sendiri ---
    for t_idx, table_item in enumerate(doc.tables):
        for prov in table_item.prov:
            page_no = prov.page_no - 1
            page_size = doc.pages[prov.page_no].size

        table_data = table_item.data
        for cell in table_data.table_cells:
            if not cell.text or not cell.text.strip():
                continue
            # bbox per-cell kalau tersedia, kalau tidak pakai bbox tabel
            cell_bbox = getattr(cell, "bbox", None)
            if cell_bbox is not None:
                bbox = _bbox_to_top_left(cell_bbox, page_size.height)
            else:
                bbox = _bbox_to_top_left(prov.bbox, page_size.height)

            counter += 1
            items.append(StructureItem(
                id=f"u{counter}",
                page=page_no,
                bbox=bbox,
                text=cell.text,
                label="table_cell",
                table_id=f"table_{t_idx}",
                row=getattr(cell, "start_row_offset_idx", None),
                col=getattr(cell, "start_col_offset_idx", None),
            ))

    return items
