"""Разбор документов во внутреннюю модель."""

from normocontrol.parser.docx_parser import DocxParser, parse_docx
from normocontrol.parser.model import Document, Paragraph, ParagraphRole
from normocontrol.parser.safety import InvalidDocumentError

__all__ = [
    "Document",
    "DocxParser",
    "InvalidDocumentError",
    "Paragraph",
    "ParagraphRole",
    "parse_docx",
]
