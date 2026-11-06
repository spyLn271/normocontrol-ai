"""Проверка загруженного файла до разбора: zip-бомбы, не-docx, повреждённые архивы."""

from __future__ import annotations

import io
import zipfile

MAIN_PART = "word/document.xml"
MAX_ENTRIES = 5_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class InvalidDocumentError(ValueError):
    """Файл не является корректным .docx или небезопасен для разбора."""


def validate_docx_bytes(
    data: bytes,
    *,
    max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES,
) -> None:
    if not data:
        raise InvalidDocumentError("Файл пустой")
    if not data.startswith(b"PK"):
        raise InvalidDocumentError("Файл не является документом .docx (ожидается ZIP-архив OOXML)")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InvalidDocumentError("Повреждённый архив .docx") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise InvalidDocumentError("Слишком много частей в архиве .docx")
        total = 0
        for info in infos:
            if info.flag_bits & 0x1:
                raise InvalidDocumentError("Зашифрованные документы не поддерживаются")
            total += info.file_size
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_COMPRESSION_RATIO and info.file_size > 10 * 1024 * 1024:
                raise InvalidDocumentError("Подозрительно высокая степень сжатия (zip-бомба)")
        if total > max_uncompressed_bytes:
            raise InvalidDocumentError("Документ слишком большой после распаковки")
        names = {info.filename for info in infos}
        if MAIN_PART not in names:
            raise InvalidDocumentError(
                "В архиве нет word/document.xml — это не документ Word (.docx)"
            )
