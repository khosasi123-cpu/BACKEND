from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from zipfile import ZipFile
import posixpath
import shutil
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import os

load_dotenv()
IMAGE_DRIRECTORY = os.getenv("IMAGE_DIRECTORY")

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
IMAGE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)


@dataclass(frozen=True)
class ExtractedImage:
    filename: str
    path: Path
    relationship_id: str
    source_path: str
    position: int


@dataclass(frozen=True)
class ParsedDocx:
    text: str
    images: list[ExtractedImage]


@dataclass(frozen=True)
class ImageRelationship:
    relationship_id: str
    target: str
    source_path: str | None
    is_external: bool


## Fungsi utama untuk membaca file DOCX, mengekstrak gambar, dan mengembalikan
## satu teks hasil rekonstruksi sesuai urutan asli dokumen.
def parse_docx(
    docx_path: str | Path,
    image_output_dir: str | Path = IMAGE_DRIRECTORY,
) -> ParsedDocx:
    """Parse a DOCX file into ordered text and extracted image files."""
    docx_path = Path(docx_path)
    image_output_dir = Path(image_output_dir)

    image_output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    with ZipFile(docx_path) as docx:
        relationships = _read_image_relationships(docx)
        document_root = ET.fromstring(docx.read("word/document.xml"))

        extractor = _ImageExtractor(docx, relationships, image_output_dir)
        blocks = list(_iter_body_blocks(document_root))
        text_blocks = [
            block_text
            for block in blocks
            for block_text in _parse_block(block, extractor)
            if block_text
        ]

    return ParsedDocx(text="\n\n".join(text_blocks), images=extractor.images)


## Membaca file relationship DOCX untuk memetakan relationship id gambar
## seperti rId9 ke lokasi asli gambar di dalam paket DOCX.
def _read_image_relationships(docx: ZipFile) -> dict[str, ImageRelationship]:
    try:
        rels_xml = docx.read("word/_rels/document.xml.rels")
    except KeyError:
        return {}

    root = ET.fromstring(rels_xml)
    relationships: dict[str, ImageRelationship] = {}

    for relationship in root:
        rel_type = relationship.attrib.get("Type")
        if rel_type != IMAGE_REL_TYPE:
            continue

        relationship_id = relationship.attrib["Id"]
        target = relationship.attrib["Target"]
        is_external = relationship.attrib.get("TargetMode") == "External"
        source_path = None if is_external else _resolve_docx_target("word", target)

        relationships[relationship_id] = ImageRelationship(
            relationship_id=relationship_id,
            target=target,
            source_path=source_path,
            is_external=is_external,
        )

    return relationships


## Mengubah target relatif dari relationship DOCX menjadi path internal ZIP
## yang bisa dibaca, misalnya media/image1.png menjadi word/media/image1.png.
def _resolve_docx_target(base_dir: str, target: str) -> str:
    return posixpath.normpath(posixpath.join(base_dir, target))


## Menghasilkan blok utama dokumen sesuai urutan asli di word/document.xml.
## Saat ini hanya paragraf dan tabel yang diproses karena keduanya memuat teks/gambar.
def _iter_body_blocks(document_root: ET.Element) -> Iterable[ET.Element]:
    body = document_root.find("w:body", NS)
    if body is None:
        return

    for child in body:
        if child.tag in {_tag("w", "p"), _tag("w", "tbl")}:
            yield child


## Mengarahkan proses parsing berdasarkan jenis blok: paragraf diproses sebagai
## paragraf, tabel diproses baris demi baris dan sel demi sel.
def _parse_block(block: ET.Element, extractor: "_ImageExtractor") -> list[str]:
    if block.tag == _tag("w", "p"):
        return _parse_paragraph(block, extractor)

    if block.tag == _tag("w", "tbl"):
        return _parse_table(block, extractor)

    return []


## Membaca tabel DOCX dalam urutan baris dan sel, lalu menggabungkan isi sel
## menggunakan pemisah sederhana agar teks tabel tetap terbaca.
def _parse_table(table: ET.Element, extractor: "_ImageExtractor") -> list[str]:
    table_blocks: list[str] = []
    for row in table.findall("w:tr", NS):
        row_cells: list[str] = []
        for cell in row.findall("w:tc", NS):
            cell_blocks = [
                block_text
                for block in cell
                for block_text in _parse_block(block, extractor)
                if block_text
            ]
            row_cells.append(" ".join(cell_blocks).strip())

        row_text = " | ".join(cell for cell in row_cells if cell)
        if row_text:
            table_blocks.append(row_text)

    return table_blocks


## Membaca satu paragraf DOCX dengan mempertahankan urutan child element,
## termasuk teks, hyperlink, line break, dan gambar di dalam paragraf.
def _parse_paragraph(
    paragraph: ET.Element,
    extractor: "_ImageExtractor",
) -> list[str]:
    parts: list[str] = []

    for child in paragraph:
        parts.extend(_parse_paragraph_child(child, extractor))

    return _group_paragraph_parts(parts)


## Memproses child element di dalam paragraf. Run dan hyperlink ditangani
## khusus karena keduanya dapat berisi teks dan gambar.
def _parse_paragraph_child(
    element: ET.Element,
    extractor: "_ImageExtractor",
) -> list[str]:
    if element.tag == _tag("w", "r"):
        return _parse_run(element, extractor)

    if element.tag == _tag("w", "hyperlink"):
        parts: list[str] = []
        for child in element:
            parts.extend(_parse_paragraph_child(child, extractor))
        return parts

    return _extract_text_and_images(element, extractor)


## Membaca satu run Word. Run adalah unit kecil di dalam paragraf yang dapat
## berisi teks, tab, line break, drawing, atau elemen Word lain.
def _parse_run(run: ET.Element, extractor: "_ImageExtractor") -> list[str]:
    parts: list[str] = []

    for child in run:
        if child.tag == _tag("w", "t"):
            parts.append(child.text or "")
        elif child.tag == _tag("w", "tab"):
            parts.append("\t")
        elif child.tag in {_tag("w", "br"), _tag("w", "cr")}:
            parts.append("\n")
        elif child.tag in {_tag("w", "drawing"), _tag("w", "pict")}:
            parts.extend(_extract_images(child, extractor))
        else:
            parts.extend(_extract_text_and_images(child, extractor))

    return parts


## Fungsi rekursif cadangan untuk mengambil teks dan gambar dari elemen yang
## tidak ditangani secara khusus oleh parser run/paragraf.
def _extract_text_and_images(
    element: ET.Element,
    extractor: "_ImageExtractor",
) -> list[str]:
    parts: list[str] = []

    if element.tag == _tag("w", "t"):
        parts.append(element.text or "")

    if element.tag in {_tag("w", "drawing"), _tag("w", "pict")}:
        parts.extend(_extract_images(element, extractor))
        return parts

    for child in element:
        parts.extend(_extract_text_and_images(child, extractor))

    return parts


## Mengambil relationship id dari elemen gambar DOCX, mengekstrak file gambarnya,
## lalu mengembalikan marker figure yang akan dimasukkan ke teks.
def _extract_images(
    element: ET.Element,
    extractor: "_ImageExtractor",
) -> list[str]:
    markers: list[str] = []

    relationship_ids = [
        blip.attrib.get(_tag("r", "embed")) or blip.attrib.get(_tag("r", "link"))
        for blip in element.findall(".//a:blip", NS)
    ]
    relationship_ids.extend(
        image.attrib.get(_tag("r", "id"))
        for image in element.findall(".//v:imagedata", NS)
    )

    for relationship_id in relationship_ids:
        if relationship_id:
            marker = extractor.extract_marker(relationship_id)
            if marker:
                markers.append(marker)

    return markers


## Memecah isi paragraf menjadi blok teks dan blok marker gambar. Ini membuat
## marker gambar menjadi bagian terpisah sehingga posisinya tetap jelas.
def _group_paragraph_parts(parts: list[str]) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []

    for part in parts:
        if _is_figure_marker(part):
            text = "".join(current).strip()
            if text:
                blocks.append(text)
            blocks.append(part)
            current = []
        else:
            current.append(part)

    text = "".join(current).strip()
    if text:
        blocks.append(text)

    return blocks


## Mengecek apakah sebuah string adalah marker gambar yang dibuat parser.
def _is_figure_marker(value: str) -> bool:
    return value.startswith("[Figure: ") and "\n\nImage Description:\n<empty>" in value


## Membuat nama tag XML lengkap dengan namespace agar pencarian elemen Word
## lebih aman dan tidak bergantung pada prefix XML di file sumber.
def _tag(namespace: str, local_name: str) -> str:
    return f"{{{NS[namespace]}}}{local_name}"


class _ImageExtractor:
    ## Menyiapkan extractor dengan akses ke ZIP DOCX, daftar relationship gambar,
    ## direktori output, counter nama file, dan metadata gambar yang diekstrak.
    def __init__(
        self,
        docx: ZipFile,
        relationships: dict[str, ImageRelationship],
        output_dir: Path,
    ) -> None:
        self._docx = docx
        self._relationships = relationships
        self._output_dir = output_dir
        self._counter = 0
        self.images: list[ExtractedImage] = []

    ## Mengekstrak satu gambar berdasarkan relationship id, menyimpan file gambar
    ## ke disk, mencatat metadata, lalu mengembalikan marker untuk teks.
    def extract_marker(self, relationship_id: str) -> str | None:
        relationship = self._relationships.get(relationship_id)
        if relationship is None or relationship.is_external or relationship.source_path is None:
            return None

        suffix = PurePosixPath(relationship.source_path).suffix or ".bin"
        filename = self._next_filename(suffix)
        output_path = self._output_dir / filename
        self._output_dir.mkdir(parents=True, exist_ok=True)

        with self._docx.open(relationship.source_path) as source:
            with output_path.open("wb") as destination:
                shutil.copyfileobj(source, destination)

        position = len(self.images) + 1
        self.images.append(
            ExtractedImage(
                filename=filename,
                path=output_path,
                relationship_id=relationship.relationship_id,
                source_path=relationship.source_path,
                position=position,
            )
        )

        return f"[Figure: {Path(filename)}]\n\nImage Description:\n<empty>"

    ## Membuat nama file gambar berurutan yang belum ada di folder output agar
    ## file lama tidak tertimpa ketika parser dijalankan berulang.
    def _next_filename(self, suffix: str) -> str:
        while True:
            self._counter += 1
            filename = f"img_{self._counter:06d}{suffix.lower()}"
            if not (self._output_dir / filename).exists():
                return filename
            
def write_markdown(parsed_docx : ParsedDocx,
                   output_path = "storage/file/test.md"):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        parsed_docx.text,
        encoding="utf-8"
    )
    return output_path

if __name__ == "__main__":
    parsed = parse_docx("C:\\Users\\User\\Downloads\\test.docx")
    write_markdown(parsed)