"""
PDF Analyzer
============
Deteksi apakah PDF itu digital (ada text layer) atau hasil scan (butuh OCR
sebelum pipeline ini bisa jalan). Pipeline translation-unit ini didesain
untuk PDF digital saja.
"""

from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF (pymupdf>=1.24 rekomendasi import ini, bukan `import fitz`)


@dataclass
class PDFAnalysisResult:
    is_digital: bool
    total_pages: int
    pages_with_text: int
    text_char_count: int


def analyze_pdf(pdf_path: str, min_chars_per_page: int = 20) -> PDFAnalysisResult:
    """
    Heuristik sederhana: kalau rata-rata karakter per halaman terlalu sedikit,
    kemungkinan besar itu PDF scan (gambar) tanpa text layer asli.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pages_with_text = 0
    total_chars = 0

    for page in doc:
        text = page.get_text("text")
        char_count = len(text.strip())
        total_chars += char_count
        if char_count >= min_chars_per_page:
            pages_with_text += 1

    doc.close()

    # Anggap digital kalau mayoritas halaman punya text layer memadai
    is_digital = total_pages > 0 and (pages_with_text / total_pages) >= 0.6

    return PDFAnalysisResult(
        is_digital=is_digital,
        total_pages=total_pages,
        pages_with_text=pages_with_text,
        text_char_count=total_chars,
    )


if __name__ == "__main__":
    import sys

    result = analyze_pdf(sys.argv[1])
    print(result)
    if not result.is_digital:
        print("PDF ini kemungkinan hasil scan. Jalankan OCR dulu sebelum translation pipeline.")
