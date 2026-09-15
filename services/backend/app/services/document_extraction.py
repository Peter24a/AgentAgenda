"""Local document extraction. Never treat decoded binary bytes as document text.

Limits are rejection thresholds, not truncation lengths. OCR tools run locally,
with bounded subprocess deadlines; callers must run this service off the event loop.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Optional
from zipfile import ZipFile

from docx import Document as WordDocument
from docx.table import Table
from pypdf import PdfReader


MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 2_000_000
MAX_PDF_PAGES = 500
MAX_EXPANDED_DOCX_BYTES = 100 * 1024 * 1024
OCR_TIMEOUT_SECONDS = 90
EXTRACTION_TIMEOUT_SECONDS = 300
TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    text: Optional[str] = None
    detail: str = ""
    page_count: int = 0
    ocr_pages: tuple[int, ...] = ()


class ExtractionNeedsReview(Exception):
    pass


def _check_length(text: str) -> None:
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise ExtractionNeedsReview(
            f"Texto excede el límite de {MAX_EXTRACTED_CHARACTERS} caracteres; "
            "divida el documento. No se guardó texto recortado."
        )


def _clean_text(text: str) -> str:
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _run_ocr_tool(command: list[str], deadline: float) -> str:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ExtractionNeedsReview("Se agotó el tiempo límite de extracción local.")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=True, timeout=min(OCR_TIMEOUT_SECONDS, remaining),
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionNeedsReview("OCR local excedió el tiempo límite.") from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        # Tool stderr can contain private file contents or server paths.
        raise ExtractionNeedsReview("La herramienta OCR local no pudo leer el documento.") from exc
    return result.stdout


def _ocr_language(deadline: float) -> str:
    if not shutil.which("tesseract"):
        raise ExtractionNeedsReview("OCR no disponible: falta tesseract (idiomas spa y eng).")
    available = set(_run_ocr_tool(["tesseract", "--list-langs"], deadline).splitlines())
    languages = [lang for lang in ("spa", "eng") if lang in available]
    if not languages:
        raise ExtractionNeedsReview("OCR no disponible: faltan los idiomas español/inglés.")
    return "+".join(languages)


def _ocr_image(path: Path, language: str, deadline: float) -> str:
    return _clean_text(_run_ocr_tool(
        ["tesseract", str(path), "stdout", "-l", language, "--psm", "3"], deadline
    ))


def _ocr_pdf_page(path: Path, number: int, language: str, deadline: float) -> str:
    if not shutil.which("pdftoppm"):
        raise ExtractionNeedsReview("OCR de PDF no disponible: falta pdftoppm (Poppler).")
    with tempfile.TemporaryDirectory(prefix="agenda-ocr-") as directory:
        prefix = Path(directory) / "page"
        _run_ocr_tool([
            "pdftoppm", "-f", str(number), "-l", str(number), "-singlefile",
            "-scale-to", "3000", "-png", str(path), str(prefix),
        ], deadline)
        return _ocr_image(prefix.with_suffix(".png"), language, deadline)


def _has_large_image(page) -> bool:
    def inspect(resources, depth=0):
        if not resources or depth > 5:
            return False
        resources = resources.get_object()
        objects = resources.get("/XObject", {})
        if hasattr(objects, "get_object"):
            objects = objects.get_object()
        for reference in objects.values():
            obj = reference.get_object()
            if obj.get("/Subtype") == "/Image":
                if int(obj.get("/Width", 0)) >= 400 and int(obj.get("/Height", 0)) >= 400:
                    return True
            elif obj.get("/Subtype") == "/Form" and inspect(obj.get("/Resources"), depth + 1):
                return True
        return False
    return inspect(page.get("/Resources"))


def _extract_pdf(path: Path, deadline: float) -> ExtractionResult:
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        return ExtractionResult("needs_review", detail="PDF cifrado: requiere una copia sin contraseña.")
    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ExtractionNeedsReview(f"PDF excede el límite de {MAX_PDF_PAGES} páginas; divida el archivo.")
    sections, issues, ocr_pages = [], [], []
    total_characters = 0
    language = None
    ocr_unavailable = None
    for number, page in enumerate(reader.pages, start=1):
        if time.monotonic() >= deadline:
            issues.append(f"Página {number} y siguientes: tiempo límite de extracción agotado.")
            break
        try:
            native = _clean_text(page.extract_text() or "")
            needs_ocr = not native or (len(native) < 200 and _has_large_image(page))
        except Exception:
            native, needs_ocr = "", True
        text = native
        if needs_ocr:
            try:
                if ocr_unavailable:
                    raise ExtractionNeedsReview(ocr_unavailable)
                if language is None:
                    try:
                        language = _ocr_language(deadline)
                    except ExtractionNeedsReview as exc:
                        ocr_unavailable = str(exc)
                        raise
                ocr = _ocr_pdf_page(path, number, language, deadline)
                if not ocr:
                    issues.append(f"Página {number}: OCR sin texto legible; podría estar vacía o ser una imagen.")
                else:
                    ocr_pages.append(number)
                    # Keep native text if OCR misses a value in a partially scanned page.
                    if native and native not in ocr:
                        text = native + "\n" + ocr
                    else:
                        text = ocr
            except ExtractionNeedsReview as exc:
                issues.append(f"Página {number}: {exc}")
        if text:
            section = f"[Página {number}]\n{text}"
            total_characters += len(section) + (2 if sections else 0)
            if total_characters > MAX_EXTRACTED_CHARACTERS:
                raise ExtractionNeedsReview(
                    f"Texto excede el límite de {MAX_EXTRACTED_CHARACTERS} caracteres; "
                    "divida el documento. No se guardó texto recortado."
                )
            sections.append(section)
    text = "\n\n".join(sections) or None
    if not text and not issues:
        issues.append("PDF sin páginas con texto extraíble.")
    return ExtractionResult(
        "needs_review" if issues else "ready", text, "; ".join(issues), page_count, tuple(ocr_pages)
    )


def _word_blocks(container):
    for item in container.iter_inner_content():
        if isinstance(item, Table):
            for row in item.rows:
                # A merged cell can occur several times in the row API.
                seen, cells = set(), []
                for cell in row.cells:
                    if cell._tc not in seen:
                        seen.add(cell._tc)
                        cells.append("\n".join(_word_blocks(cell)))
                yield " | ".join(cells)
        else:
            yield item.text


def _extract_docx(path: Path) -> ExtractionResult:
    with ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_EXPANDED_DOCX_BYTES:
            raise ExtractionNeedsReview("DOCX excede el límite de 100 MB descomprimidos.")
        names = archive.namelist()
        has_images = any(name.startswith("word/media/") for name in names)
        has_notes = any(name in names for name in ("word/footnotes.xml", "word/endnotes.xml"))
        has_embedded_objects = any(name.startswith(("word/charts/", "word/embeddings/")) for name in names)
        has_textboxes = b"txbxContent" in archive.read("word/document.xml")
    document = WordDocument(path)
    parts = list(_word_blocks(document))
    seen_parts = set()
    for section in document.sections:
        for container in (
            section.header, section.first_page_header, section.even_page_header,
            section.footer, section.first_page_footer, section.even_page_footer,
        ):
            if container.part.partname not in seen_parts:
                seen_parts.add(container.part.partname)
                parts.extend(_word_blocks(container))
    text = _clean_text("\n\n".join(parts))
    _check_length(text)
    issues = []
    if has_images:
        issues.append("DOCX contiene imágenes incrustadas que requieren revisión visual.")
    if has_notes or has_textboxes:
        issues.append("DOCX contiene notas o cuadros de texto fuera de los párrafos y tablas extraídos.")
    if has_embedded_objects:
        issues.append("DOCX contiene gráficas u objetos incrustados que requieren revisión visual.")
    if not text:
        issues.append("DOCX sin texto extraíble.")
    return ExtractionResult("needs_review" if issues else "ready", text or None, "; ".join(issues))


def extract_document(path: str | Path, filename: str, mime_type: str) -> ExtractionResult:
    """Extract an entire supported file; diagnostics are never stored as content."""
    path = Path(path).resolve()
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ExtractionNeedsReview("Archivo excede el límite de extracción de 50 MB; divídalo.")
        extension = Path(filename).suffix.lower()
        deadline = time.monotonic() + EXTRACTION_TIMEOUT_SECONDS
        if extension == ".pdf" or mime_type == "application/pdf":
            return _extract_pdf(path, deadline)
        if extension == ".docx" or mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return _extract_docx(path)
        if extension in IMAGE_EXTENSIONS:
            language = _ocr_language(deadline)
            text = _ocr_image(path, language, deadline)
            _check_length(text)
            return ExtractionResult(
                "ready" if text else "needs_review", text or None,
                "" if text else "Imagen sin texto legible por OCR; requiere revisión visual.",
                1, (1,) if text else (),
            )
        if extension in TEXT_EXTENSIONS or mime_type in {"text/plain", "text/markdown"}:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                return ExtractionResult("needs_review", detail="Texto no válido en UTF-8; conviértalo antes de importar.")
            if any(ord(char) < 32 and char not in "\r\n\t\f" for char in text):
                return ExtractionResult("unsupported", detail="El archivo declarado como texto contiene datos binarios.")
            text = _clean_text(text)
            _check_length(text)
            return ExtractionResult("ready" if text else "needs_review", text or None, "" if text else "Archivo de texto vacío.")
        return ExtractionResult("unsupported", detail=f"Formato sin extractor: {extension or mime_type}.")
    except ExtractionNeedsReview as exc:
        return ExtractionResult("needs_review", detail=str(exc))
    except FileNotFoundError:
        return ExtractionResult("failed", detail="El archivo físico no existe en disco.")
    except Exception as exc:
        return ExtractionResult("failed", detail=f"No se pudo extraer el documento ({type(exc).__name__}).")
