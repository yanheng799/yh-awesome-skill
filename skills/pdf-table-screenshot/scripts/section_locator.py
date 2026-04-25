"""Chapter/section page range detection via PDF outlines and text pattern matching."""

import re
from typing import List, Tuple

import pdfplumber
from pypdf import PdfReader


def get_outlines(pdf_path: str) -> List[dict]:
    """Extract PDF outline/bookmark structure using pypdf.

    Returns:
        List of dicts: [{"title": str, "page": int (1-based), "level": int}, ...]
    """
    reader = PdfReader(pdf_path)
    if reader.outline is None:
        return []

    result = []

    def walk(items, level=0):
        for item in items:
            if isinstance(item, list):
                walk(item, level + 1)
            else:
                try:
                    page_num = reader.get_destination_page_number(item)
                    if page_num is not None:
                        result.append(
                            {
                                "title": str(item.title or ""),
                                "page": page_num + 1,  # Convert to 1-based
                                "level": level,
                            }
                        )
                except Exception:
                    pass

    walk(reader.outline)
    return result


def _normalize_chinese_numbers(s: str) -> str:
    """Convert Chinese numeral characters to Arabic digits for fuzzy matching."""
    cn_map = {
        "零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
        "十": "10", "百": "100", "千": "1000",
    }
    result = ""
    for ch in s:
        result += cn_map.get(ch, ch)
    return result


def _keywords_match(title: str, keyword: str) -> bool:
    """Check if a title matches the keyword with fuzzy Chinese number support."""
    keyword_lower = keyword.lower()
    title_lower = title.lower()

    # Direct substring match
    if keyword_lower in title_lower:
        return True

    # Normalize Chinese numbers and retry
    norm_keyword = _normalize_chinese_numbers(keyword_lower)
    norm_title = _normalize_chinese_numbers(title_lower)
    if norm_keyword and norm_keyword in norm_title:
        return True

    # Strip common suffixes and retry (e.g. "第3章" vs "第三章 数据结构")
    keyword_stripped = re.sub(r"[\s:：\-—.]+.*$", "", keyword_lower)
    if keyword_stripped and keyword_stripped in title_lower:
        return True

    return False


def find_section_by_keyword(
    outlines: List[dict], keyword: str, total_pages: int
) -> Tuple[int, int]:
    """Match keyword against outline titles to find a section's page range.

    Args:
        outlines: List of outline dicts from get_outlines().
        keyword: Section keyword to match (e.g. "第3章", "Chapter 3").
        total_pages: Total pages in the PDF (for end boundary).

    Returns:
        (start_page, end_page), both 1-based inclusive.

    Raises:
        ValueError if no matching section is found.
    """
    matches = []
    for entry in outlines:
        if _keywords_match(entry["title"], keyword):
            matches.append(entry)

    if not matches:
        raise ValueError(f"No outline entry matches keyword: {keyword}")

    # Use the first (best) match
    matched = matches[0]
    start_page = matched["page"]

    # End page: next outline entry at same or shallower level, or end of document
    matched_level = matched["level"]
    end_page = total_pages

    for entry in outlines:
        if entry["page"] > start_page and entry["level"] <= matched_level:
            end_page = entry["page"] - 1
            break

    return (start_page, end_page)


def find_section_by_text_scan(
    pdf_path: str, keyword: str, total_pages: int
) -> Tuple[int, int]:
    """Scan all pages for chapter heading text matching the keyword.

    Uses regex patterns for common chapter/section heading formats.

    Returns:
        (start_page, end_page), both 1-based inclusive.

    Raises:
        ValueError if no matching heading is found.
    """
    # Patterns for detecting chapter/section headings
    heading_patterns = [
        re.compile(r"第[一二三四五六七八九十百千\d]+[章节篇部分]\s*.*"),
        re.compile(r"(?i)^chapter\s+\d+[\.:]?\s*.*"),
        re.compile(r"(?i)^section\s+\d+[\.:]?\s*.*"),
        re.compile(r"(?i)^part\s+[IVXLCDM\d]+[\.:]?\s*.*"),
        re.compile(r"^\d+[\.\、]\s*\S+.*"),
    ]

    # Also build a pattern from the keyword itself
    keyword_pattern = re.compile(re.escape(keyword), re.IGNORECASE)

    headings = []  # (page_num, title)

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = text.split("\n")
            # Check first 10 lines (headings are typically near the top)
            for line in lines[:10]:
                line_stripped = line.strip()
                if not line_stripped or len(line_stripped) > 100:
                    continue
                # Check against keyword pattern
                if keyword_pattern.search(line_stripped):
                    headings.append((i + 1, line_stripped))
                    break
                # Check against heading patterns
                for pat in heading_patterns:
                    if pat.match(line_stripped):
                        headings.append((i + 1, line_stripped))
                        break
                else:
                    continue
                break  # Found a heading on this page, move to next page

    # Find the heading that best matches the keyword
    best_match = None
    for page_num, title in headings:
        if _keywords_match(title, keyword):
            best_match = (page_num, title)
            break

    if best_match is None:
        raise ValueError(
            f"No heading matching '{keyword}' found in PDF text. "
            f"Use --list-sections to see available headings."
        )

    start_page = best_match[0]

    # End page: next detected heading or end of document
    end_page = total_pages
    for page_num, _ in headings:
        if page_num > start_page:
            end_page = page_num - 1
            break

    return (start_page, end_page)


def parse_page_range(range_str: str, total_pages: int) -> List[int]:
    """Parse a page range string into a sorted list of 1-based page numbers.

    Supports formats:
        "10-25"          -> pages 10 through 25
        "5,8,12"         -> pages 5, 8, 12
        "10-25,30,35-40" -> combined ranges

    Args:
        range_str: Page range specification string.
        total_pages: Total pages in the PDF for validation.

    Returns:
        Sorted list of 1-based page numbers.

    Raises:
        ValueError if the range string is invalid.
    """
    pages = set()
    for part in range_str.split(","):
        part = part.strip()
        if "-" in part:
            segments = part.split("-")
            if len(segments) != 2:
                raise ValueError(f"Invalid page range segment: {part}")
            try:
                start = int(segments[0].strip())
                end = int(segments[1].strip())
            except ValueError:
                raise ValueError(f"Non-numeric page range: {part}")
            if start < 1 or end > total_pages or start > end:
                raise ValueError(
                    f"Page range {start}-{end} out of bounds (1-{total_pages})"
                )
            pages.update(range(start, end + 1))
        else:
            try:
                p = int(part)
            except ValueError:
                raise ValueError(f"Non-numeric page number: {part}")
            if p < 1 or p > total_pages:
                raise ValueError(f"Page {p} out of bounds (1-{total_pages})")
            pages.add(p)

    return sorted(pages)


def locate_section(pdf_path: str, section: str) -> Tuple[int, int]:
    """Locate a section's page range using outlines first, text scan as fallback.

    Args:
        pdf_path: Path to the PDF file.
        section: Section keyword (e.g. "第3章", "Chapter 3", "3.2").

    Returns:
        (start_page, end_page), both 1-based inclusive.

    Raises:
        ValueError if the section cannot be found.
    """
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    # Try outline-based lookup first
    outlines = get_outlines(pdf_path)
    if outlines:
        try:
            return find_section_by_keyword(outlines, section, total_pages)
        except ValueError:
            pass  # Fall through to text scan

    # Fall back to text pattern scanning
    return find_section_by_text_scan(pdf_path, section, total_pages)
