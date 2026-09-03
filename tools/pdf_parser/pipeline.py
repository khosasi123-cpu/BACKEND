"""
Pipeline End-to-End
=====================
PDF -> PDF Analyzer -> [PyMuPDF geometry + Docling structure]
    -> Translation Unit Builder -> Ministral -> Validator -> Renderer
    -> PDF terjemahan (layout dipertahankan)

Usage:
    python pipeline.py input.pdf output.pdf --source English --target Indonesian
"""

import argparse
import sys

from .pdf_analyzer import analyze_pdf
from .geometry_extractor import extract_geometry
from .structure_extractor import extract_structure
from .unit_builder import build_translation_units
from .translator import translate_units
from .validator import validate
from .renderer import render_translated_pdf


def run_pipeline(input_pdf: str, output_pdf: str, source_lang: str, target_lang: str,
                  batch_size: int = 25, strict: bool = True):
    print(f"[1/6] Analyzing PDF: {input_pdf}")
    analysis = analyze_pdf(input_pdf)
    print(f"      {analysis}")
    if not analysis.is_digital:
        print("      PDF ini kemungkinan hasil SCAN (tidak ada text layer memadai).")
        print("      Pipeline ini butuh OCR dulu sebelum translation unit bisa dibuat. Berhenti.")
        sys.exit(1)

    print("[2/6] Extracting geometry (PyMuPDF)...")
    pages_geometry = extract_geometry(input_pdf)
    total_spans = sum(len(pg.spans) for pg in pages_geometry)
    print(f"      {total_spans} text spans di {len(pages_geometry)} halaman")

    print("[3/6] Extracting structure (Docling)...")
    structure_items = extract_structure(input_pdf)
    print(f"      {len(structure_items)} structure items ditemukan")

    print("[4/6] Building translation units...")
    units = build_translation_units(structure_items, pages_geometry, analysis.total_pages)
    protected_count = sum(1 for u in units if u.protected)
    print(f"      {len(units)} unit total, {protected_count} ditandai protected (tidak diterjemahkan)")

    print(f"[5/6] Translating {source_lang} -> {target_lang} via Ministral...")
    original_snapshot = [
        type(u)(**{**u.__dict__})  # shallow copy untuk validasi before/after
        for u in units
    ]
    translated_units = translate_units(units, source_lang, target_lang, batch_size=batch_size)

    print("      Validating...")
    result = validate(original_snapshot, translated_units)
    for w in result.warnings:
        print(f"      WARNING: {w}")
    if not result.ok:
        print("      VALIDATION FAILED:")
        for e in result.errors:
            print(f"        - {e}")
        if strict:
            print("      Berhenti (strict mode). Jalankan dengan --no-strict untuk tetap render.")
            sys.exit(1)
        else:
            print("      Lanjut render meski ada error (--no-strict).")

    print(f"[6/6] Rendering translated PDF -> {output_pdf}")
    render_translated_pdf(input_pdf, translated_units, output_pdf)

    print("Selesai.")
    return output_pdf


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate PDF sambil mempertahankan layout asli")
    parser.add_argument("input_pdf")
    parser.add_argument("output_pdf")
    parser.add_argument("--source", default="English", help="Bahasa sumber")
    parser.add_argument("--target", default="Indonesian", help="Bahasa target")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--no-strict", dest="strict", action="store_false",
                         help="Tetap render walau validasi gagal")
    args = parser.parse_args()

    run_pipeline(args.input_pdf, args.output_pdf, args.source, args.target,
                 batch_size=args.batch_size, strict=args.strict)
