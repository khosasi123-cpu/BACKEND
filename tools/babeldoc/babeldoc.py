import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

import babeldoc.format.pdf.high_level

from babeldoc.docvision.doclayout import DocLayoutModel
from babeldoc.format.pdf.translation_config import TranslationConfig
from babeldoc.translator.translator import (
    OpenAITranslator,
    set_translate_rate_limiter,
)


load_dotenv(override=True)


MODEL = os.getenv("MODEL")
BASE_URL = os.getenv("LLM_BASE_URL")
API_KEY = os.getenv("OPENAI_API_KEY")


async def _translate_pdf(
    input_pdf: Path,
    output_dir: Path,
    source_lang: str,
    target_lang: str,
) -> Path:

    input_pdf = input_pdf.resolve()
    output_dir = output_dir.resolve()

    if not input_pdf.exists():
        raise FileNotFoundError(
            f"Input PDF not found: {input_pdf}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not MODEL:
        raise RuntimeError("MODEL is not configured")

    if not BASE_URL:
        raise RuntimeError("LLM_BASE_URL is not configured")

    if not API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    translator = OpenAITranslator(
        lang_in=source_lang,
        lang_out=target_lang,
        model=MODEL,
        base_url=BASE_URL,
        api_key=API_KEY,
    )

    set_translate_rate_limiter(1)

    doc_layout_model = DocLayoutModel.load_onnx()

    config = TranslationConfig(
        translator=translator,
        input_file=input_pdf,
        lang_in=source_lang,
        lang_out=target_lang,
        doc_layout_model=doc_layout_model,
        output_dir=output_dir,
        no_dual=True,
    )

    async for event in babeldoc.format.pdf.high_level.async_translate(config):

        if event["type"] == "error":
            raise RuntimeError(
                f"BabelDOC translation failed: {event['error']}"
            )

        if event["type"] == "finish":
            output_file = (
                output_dir
                / f"{input_pdf.stem}.{target_lang}.mono.pdf"
            )

            if not output_file.exists():
                raise FileNotFoundError(
                    f"Translated PDF not found: {output_file}"
                )

            return output_file

    raise RuntimeError(
        "BabelDOC translation finished without a result"
    )


def translate_pdf(
    input_pdf: str | Path,
    output_dir: str | Path,
    source_lang: str = "en",
    target_lang: str = "id",
) -> Path:

    return asyncio.run(
        _translate_pdf(
            input_pdf=Path(input_pdf),
            output_dir=Path(output_dir),
            source_lang=source_lang,
            target_lang=target_lang,
        )
    )