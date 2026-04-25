"""Table detection and filtering using pdfplumber."""

import pdfplumber


def detect_page_layout(page) -> str:
    """Detect page layout: 'single' or 'double' column.

    Analyzes the horizontal distribution of text characters to determine
    whether the page uses a single-column or double-column layout.

    Returns:
        'single' or 'double'.
    """
    page_width = page.width
    if page_width <= 0:
        return "single"

    # Collect x0 positions of all characters
    chars = page.chars
    if not chars or len(chars) < 50:
        return "single"

    # Build a horizontal density histogram (100 bins across page width)
    num_bins = 100
    bin_width = page_width / num_bins
    histogram = [0] * num_bins

    for ch in chars:
        x0 = ch.get("x0", 0)
        bin_idx = int(x0 / bin_width)
        bin_idx = max(0, min(num_bins - 1, bin_idx))
        histogram[bin_idx] += 1

    # Check middle region (bins 40-59) for a gap
    middle_bins = histogram[40:60]
    middle_avg = sum(middle_bins) / len(middle_bins) if middle_bins else 0

    # Check left region (bins 5-40) and right region (bins 60-95)
    left_bins = histogram[5:40]
    right_bins = histogram[60:95]
    left_avg = sum(left_bins) / len(left_bins) if left_bins else 0
    right_avg = sum(right_bins) / len(right_bins) if right_bins else 0

    # Overall average for reference
    overall_avg = sum(histogram) / num_bins

    # Double column conditions:
    # 1. Both left and right regions have significant text (> 30% of overall avg)
    # 2. Middle region has a clear gap (< 50% of overall avg)
    # 3. The gap is narrower than the text regions
    if (
        left_avg > overall_avg * 0.3
        and right_avg > overall_avg * 0.3
        and middle_avg < overall_avg * 0.5
        and middle_avg < left_avg * 0.6
        and middle_avg < right_avg * 0.6
    ):
        return "double"

    return "single"


def merge_dual_column_tables(tables, page_width) -> list:
    """Merge tables that were split across dual columns.

    When pdfplumber detects a table that spans both columns as two separate
    half-width tables, this function merges them back into one.

    Args:
        tables: List of pdfplumber Table objects.
        page_width: Width of the page in PDF points.

    Returns:
        List of (table_or_pair, is_merged, merged_bbox) tuples.
        - For merged tables: (left_table, True, merged_bbox)
          right_table.extract() data is appended to left_table's rows.
        - For unmerged tables: (table, False, table.bbox)
    """
    if len(tables) < 2:
        return [(t, False, t.bbox) for t in tables]

    # Sort tables by x0 position
    sorted_tables = sorted(tables, key=lambda t: t.bbox[0])

    used = set()
    result = []

    for i, t1 in enumerate(sorted_tables):
        if i in used:
            continue

        bbox1 = t1.bbox
        mid = page_width / 2

        # Check if this table is in the left half
        if bbox1[2] < mid * 1.1:  # x1 of left table
            # Look for a matching right-half table
            for j in range(i + 1, len(sorted_tables)):
                if j in used:
                    continue

                t2 = sorted_tables[j]
                bbox2 = t2.bbox

                # Right table should start in the right half
                if bbox2[0] > mid * 0.9:  # x0 of right table
                    # Check vertical overlap (> 50% of the shorter table)
                    overlap_top = max(bbox1[1], bbox2[1])
                    overlap_bottom = min(bbox1[3], bbox2[3])
                    overlap = overlap_bottom - overlap_top

                    h1 = bbox1[3] - bbox1[1]
                    h2 = bbox2[3] - bbox2[1]
                    min_height = min(h1, h2)

                    if min_height > 0 and overlap / min_height > 0.5:
                        # Merge: combine bboxes
                        merged_bbox = (
                            min(bbox1[0], bbox2[0]),
                            min(bbox1[1], bbox2[1]),
                            max(bbox1[2], bbox2[2]),
                            max(bbox1[3], bbox2[3]),
                        )
                        result.append((t1, True, merged_bbox, t2))
                        used.add(i)
                        used.add(j)
                        break

        if i not in used:
            result.append((t1, False, t1.bbox, None))

    return result


def find_tables_on_page(page, layout="auto") -> list:
    """Detect tables on a page with optional dual-column merging.

    Args:
        page: pdfplumber Page object.
        layout: 'auto' (detect), 'single', or 'double'.

    Returns:
        List of (table, is_merged, effective_bbox, right_table_or_None) tuples.
    """
    tables = page.find_tables()
    if not tables:
        return []

    if layout == "auto":
        layout = detect_page_layout(page)

    if layout == "double":
        return merge_dual_column_tables(tables, page.width)

    return [(t, False, t.bbox, None) for t in tables]


def filter_tables(tables_info: list, min_cols: int = 2, min_rows: int = 2) -> list:
    """Filter tables by minimum column and row counts.

    Args:
        tables_info: List of (table, is_merged, bbox, right_table) tuples.
        min_cols: Minimum number of columns required.
        min_rows: Minimum number of rows required.

    Returns:
        Filtered list preserving the same tuple structure.
    """
    result = []
    for item in tables_info:
        table = item[0]
        is_merged = item[1]
        right_table = item[3]

        extracted = table.extract()
        if is_merged and right_table:
            right_extracted = right_table.extract()
            # For merged tables, check combined row count
            num_rows = len(extracted) + len(right_extracted) if right_extracted else len(extracted)
            num_cols = max(
                max(len(r) for r in extracted) if extracted else 0,
                max(len(r) for r in right_extracted) if right_extracted else 0,
            )
        else:
            num_rows = len(extracted) if extracted else 0
            num_cols = max(len(r) for r in extracted) if extracted else 0

        if num_cols >= min_cols and num_rows >= min_rows:
            result.append(item)

    return result


def get_table_metadata(item, page_num: int, table_idx: int) -> dict:
    """Extract metadata from a table entry.

    Args:
        item: (table, is_merged, bbox, right_table) tuple.
        page_num: 1-based page number.
        table_idx: Sequential table index (global).

    Returns:
        Dict with page, index, bbox, rows, cols, preview, merged.
    """
    table = item[0]
    is_merged = item[1]
    bbox = item[2]
    right_table = item[3]

    extracted = table.extract()
    if not extracted:
        return None

    if is_merged and right_table:
        right_extracted = right_table.extract()
        num_rows = len(extracted) + (len(right_extracted) if right_extracted else 0)
        num_cols = max(
            max(len(r) for r in extracted) if extracted else 0,
            max(len(r) for r in right_extracted) if right_extracted else 0,
        )
        all_rows = (extracted or []) + (right_extracted or [])
    else:
        num_rows = len(extracted)
        num_cols = max(len(r) for r in extracted) if extracted else 0
        all_rows = extracted

    # Text preview: first 3 rows
    preview_rows = all_rows[:3]
    preview = " | ".join(
        " ".join(str(c or "") for c in row) for row in preview_rows
    )

    return {
        "page": page_num,
        "index": table_idx,
        "merged": is_merged,
        "bbox": {
            "x0": bbox[0],
            "top": bbox[1],
            "x1": bbox[2],
            "bottom": bbox[3],
        },
        "rows": num_rows,
        "cols": num_cols,
        "preview": preview[:200],
    }
