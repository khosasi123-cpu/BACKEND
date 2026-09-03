"""
Translation Validator
=======================
Cek sebelum render:
- jumlah unit tidak berubah
- semua ID masih ada
- tidak ada unit non-protected yang translated_text-nya kosong
- struktur tabel (jumlah cell per table_id) tidak berubah
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .unit_builder import TranslationUnit


@dataclass
class ValidationResult:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def validate(original_units: list[TranslationUnit], translated_units: list[TranslationUnit]) -> ValidationResult:
    errors = []
    warnings = []

    # 1. jumlah unit sama
    if len(original_units) != len(translated_units):
        errors.append(
            f"Jumlah unit berubah: {len(original_units)} -> {len(translated_units)}"
        )

    # 2. semua ID ada
    orig_ids = {u.id for u in original_units}
    trans_ids = {u.id for u in translated_units}
    if orig_ids != trans_ids:
        missing = orig_ids - trans_ids
        extra = trans_ids - orig_ids
        if missing:
            errors.append(f"ID hilang setelah translate: {missing}")
        if extra:
            errors.append(f"ID baru muncul (tidak seharusnya): {extra}")

    # 3. tidak ada translated_text kosong untuk unit non-protected
    empty = [u.id for u in translated_units if not u.protected and not u.translated_text.strip()]
    if empty:
        errors.append(f"Unit dengan hasil translate kosong: {empty}")

    # 4. struktur tabel: jumlah cell per table_id harus sama
    orig_table_counts = Counter(u.table_id for u in original_units if u.table_id)
    trans_table_counts = Counter(u.table_id for u in translated_units if u.table_id)
    for table_id, count in orig_table_counts.items():
        new_count = trans_table_counts.get(table_id, 0)
        if new_count != count:
            errors.append(f"Tabel {table_id}: jumlah cell berubah {count} -> {new_count}")

    # 5. warning kalau translated_text identik dengan original (mungkin gagal translate diam-diam)
    unchanged = [
        u.id for u in translated_units
        if not u.protected and u.translated_text.strip() == u.original_text.strip()
        and len(u.original_text.strip()) > 3
    ]
    if unchanged:
        warnings.append(f"{len(unchanged)} unit hasil translate identik dgn teks asli (cek manual): {unchanged[:10]}")

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)
