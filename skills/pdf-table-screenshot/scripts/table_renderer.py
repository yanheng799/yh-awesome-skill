"""Table rendering and image saving using PyMuPDF."""

import io
import json
import os

import fitz  # PyMuPDF
from PIL import Image


def crop_table_as_image(
    doc: fitz.Document,
    page_num: int,
    bbox: tuple,
    dpi: int = 200,
    padding: float = 8,
) -> Image.Image:
    """Crop a table region from a PDF page as a PIL Image.

    Args:
        doc: Opened PyMuPDF document.
        page_num: 1-based page number.
        bbox: (x0, top, x1, bottom) from pdfplumber in PDF points.
        dpi: Output image resolution.
        padding: Extra padding around the table in PDF points.

    Returns:
        PIL.Image.Image of the cropped table region.
    """
    page = doc[page_num - 1]  # Convert to 0-based

    # Apply padding, clamp to page bounds
    x0 = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    x1 = min(page.rect.width, bbox[2] + padding)
    bottom = min(page.rect.height, bbox[3] + padding)

    clip_rect = fitz.Rect(x0, top, x1, bottom)

    # Zoom matrix for desired DPI (72 is the base PDF DPI)
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)

    pix = page.get_pixmap(matrix=mat, clip=clip_rect)
    img_data = pix.tobytes("png")
    image = Image.open(io.BytesIO(img_data))
    return image


def crop_merged_table_as_image(
    doc: fitz.Document,
    page_num: int,
    bbox: tuple,
    page_width: float,
    dpi: int = 200,
    padding: float = 8,
) -> Image.Image:
    """Crop a merged dual-column table using full page width.

    For tables that span both columns, render the full width of the page
    at the table's vertical extent, so both halves are captured together.

    Args:
        doc: Opened PyMuPDF document.
        page_num: 1-based page number.
        bbox: (x0, top, x1, bottom) merged bounding box.
        page_width: Full page width for the clip rectangle.
        dpi: Output image resolution.
        padding: Extra padding around the table in PDF points.

    Returns:
        PIL.Image.Image of the cropped table region at full page width.
    """
    page = doc[page_num - 1]

    # Use full page width, but table's vertical extent
    x0 = max(0, padding)
    top = max(0, bbox[1] - padding)
    x1 = min(page.rect.width, page_width - padding)
    bottom = min(page.rect.height, bbox[3] + padding)

    clip_rect = fitz.Rect(x0, top, x1, bottom)

    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)

    pix = page.get_pixmap(matrix=mat, clip=clip_rect)
    img_data = pix.tobytes("png")
    image = Image.open(io.BytesIO(img_data))
    return image


def crop_table_smart(
    doc: fitz.Document,
    page_num: int,
    bbox: tuple,
    is_merged: bool,
    page_width: float,
    dpi: int = 200,
    padding: float = 8,
) -> Image.Image:
    """Smart crop: use full width for merged tables, bbox crop otherwise.

    Args:
        doc: Opened PyMuPDF document.
        page_num: 1-based page number.
        bbox: Effective bounding box.
        is_merged: Whether this is a merged dual-column table.
        page_width: Full page width.
        dpi: Output image resolution.
        padding: Extra padding in PDF points.

    Returns:
        PIL.Image.Image.
    """
    if is_merged:
        return crop_merged_table_as_image(doc, page_num, bbox, page_width, dpi, padding)
    return crop_table_as_image(doc, page_num, bbox, dpi, padding)


def save_table_image(
    image: Image.Image,
    output_dir: str,
    page_num: int,
    table_idx: int,
    prefix: str = "table",
) -> str:
    """Save a table image with standardized naming.

    Args:
        image: PIL Image to save.
        output_dir: Directory to save into.
        page_num: 1-based page number.
        table_idx: Sequential table index (global).
        prefix: Filename prefix.

    Returns:
        Absolute path of the saved file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{prefix}_p{page_num}_{table_idx}.png"
    filepath = os.path.join(output_dir, filename)
    image.save(filepath, "PNG")
    return filepath


def generate_summary(tables_metadata: list, output_dir: str) -> str:
    """Generate a JSON summary of all extracted tables.

    Args:
        tables_metadata: List of table metadata dicts.
        output_dir: Directory to save the summary file.

    Returns:
        Path to the generated summary JSON file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "tables_summary.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(tables_metadata, f, ensure_ascii=False, indent=2)
    return filepath
