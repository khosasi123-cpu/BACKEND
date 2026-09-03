"""
Translator (Ministral)
========================
Menerjemahkan TranslationUnit yang belum protected, dalam batch,
dengan ID eksplisit di payload supaya:
1. Model tetap dapat konteks (karena teksnya sudah per-paragraf/cell,
   bukan per-span kata terpisah - lihat unit_builder.py)
2. Kita bisa validasi hasilnya per-ID (bukan cuma ngandelin urutan array)
"""

import json
import os
import time
from httpcore import URL
from openai import OpenAI
from .unit_builder import TranslationUnit
from dotenv import load_dotenv
from pydantic import BaseModel, TypeAdapter

load_dotenv()  # load .env kalau ada

API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
MODEL = os.getenv("MODEL")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

class TranslationResult(BaseModel):
    id: str
    text: str

class TranslationResponse(BaseModel):
    translations: list[TranslationResult]

def _build_system_prompt(source_lang: str, target_lang: str) -> str:
    return (
        f"Kamu adalah mesin penerjemah dokumen teknis dari {source_lang} ke {target_lang}.\n"
        "Kamu menerima JSON array berisi objek {\"id\": ..., \"text\": ...}.\n"
        "ATURAN WAJIB:\n"
        "1. Terjemahkan field 'text' saja. JANGAN ubah 'id'.\n"
        "2. Jangan gabungkan atau pecah objek - jumlah objek di output HARUS SAMA dengan input.\n"
        "3. Pertahankan angka, satuan, nama produk, dan kode teknis apa adanya.\n"
        "4. Jangan tambahkan objek baru, jangan hapus objek yang ada.\n"
        "5. Balas HANYA dengan JSON array, tanpa markdown fences, tanpa komentar/penjelasan.\n"
        "Format output: [{\"id\": \"u1\", \"text\": \"...\"}, {\"id\": \"u2\", \"text\": \"...\"}]"
    )


def _translate_batch(
    batch: list[TranslationUnit],
    source_lang: str,
    target_lang: str,
    max_retries: int = 2,
) -> dict:
    """Translate satu batch, return dict {id: translated_text}."""

    payload = [
        {
            "id": u.id,
            "text": u.original_text,
        }
        for u in batch
    ]

    system_prompt = _build_system_prompt(source_lang, target_lang)

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False),
        },
    ]

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = client.responses.parse(
                model=MODEL,
                input=messages,
                text_format=TranslationResponse,
                temperature=0,
            )

            result = response.output_parsed

            result_map = {
                item.id: item.text
                for item in result.translations
            }

            expected_ids = {u.id for u in batch}
            actual_ids = set(result_map.keys())

            missing = expected_ids - actual_ids
            unexpected = actual_ids - expected_ids

            # Semua unit harus kembali
            if missing or unexpected:
                if attempt < max_retries and len(batch) > 1:
                    mid = len(batch) // 2

                    left = _translate_batch(
                        batch[:mid],
                        source_lang,
                        target_lang,
                        max_retries - 1,
                    )

                    right = _translate_batch(
                        batch[mid:],
                        source_lang,
                        target_lang,
                        max_retries - 1,
                    )

                    return {**left, **right}

                last_error = (
                    f"Translation ID mismatch: "
                    f"missing={missing}, unexpected={unexpected}"
                )
                continue

            # Jumlah juga harus sama
            if len(result.translations) != len(batch):
                last_error = (
                    f"Translation count mismatch: "
                    f"expected={len(batch)}, "
                    f"got={len(result.translations)}"
                )
                continue

            return result_map

        except Exception as e:
            last_error = e

            if attempt < max_retries:
                time.sleep(1)

    raise RuntimeError(
        f"Gagal translate batch setelah {max_retries} retry: "
        f"{last_error}"
    )


def translate_units(
    units: list[TranslationUnit],
    source_lang: str,
    target_lang: str,
    batch_size: int = 25,
) -> list[TranslationUnit]:
    to_translate = [u for u in units if not u.protected]
    print(f"  Translating {len(to_translate)} unit (dari total {len(units)}, "
          f"{len(units) - len(to_translate)} protected/di-skip)")

    all_results = {}
    for i in range(0, len(to_translate), batch_size):
        batch = to_translate[i:i + batch_size]
        batch_result = _translate_batch(batch, source_lang, target_lang)
        all_results.update(batch_result)
        print(f"    batch {i // batch_size + 1}: {len(batch)} unit selesai")

    for u in units:
        if not u.protected:
            u.translated_text = all_results.get(u.id, u.original_text)  # fallback ke asli kalau gagal

    return units
