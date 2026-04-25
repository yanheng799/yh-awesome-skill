"""PDF Table Screenshot - Extract and crop table images from specified PDF sections.

Usage:
    python pdf_table_screenshot.py "document.pdf" --section "第3章" -o ./output/
    python pdf_table_screenshot.py "document.pdf" --pages 10-25 -o ./output/
    python pdf_table_screenshot.py "document.pdf" --list-sections
    python pdf_table_screenshot.py "document.pdf" --list-tables --pages 10-25
    python pdf_table_screenshot.py "document.pdf" --pages 5-10 --layout double -o ./output/
"""

import argparse
import io
import os
import sys


# Fix Windows GBK encoding issue
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Allow imports from sibling scripts
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz  # PyMuPDF
import pdfplumber

import section_locator
import table_detector
import table_renderer


def list_sections(pdf_path: str):
    """List all detectable sections in the PDF."""
    print(f"=== PDF 章节结构: {pdf_path} ===\n")

    # Try outlines first
    outlines = section_locator.get_outlines(pdf_path)
    if outlines:
        print("[书签/大纲]")
        for entry in outlines:
            indent = "  " * entry["level"]
            print(f"  {indent}P{entry['page']:>4d}  {entry['title']}")

    # Also scan for text-based headings
    print("\n[文本扫描检测到的标题]")
    heading_patterns = [
        __import__("re").compile(r"第[一二三四五六七八九十百千\d]+[章节篇部分]\s*.*"),
        __import__("re").compile(r"(?i)^chapter\s+\d+[\.:]?\s*.*"),
        __import__("re").compile(r"(?i)^section\s+\d+[\.:]?\s*.*"),
        __import__("re").compile(r"(?i)^part\s+[IVXLCDM\d]+[\.:]?\s*.*"),
        __import__("re").compile(r"^\d+[\.\、]\s*\S+.*"),
    ]

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = text.split("\n")
            for line in lines[:10]:
                line_stripped = line.strip()
                if not line_stripped or len(line_stripped) > 100:
                    continue
                for pat in heading_patterns:
                    if pat.match(line_stripped):
                        print(f"  P{i + 1:>4d}  {line_stripped}")
                        break
                else:
                    continue
                break


def list_tables(pdf_path: str, page_range, layout: str = "auto"):
    """List all tables detected in the given page range."""
    print(f"\n=== 表格列表 (页码范围: {page_range}, 布局: {layout}) ===\n")
    found = False

    with pdfplumber.open(pdf_path) as pdf:
        for page_num in page_range:
            page = pdf.pages[page_num - 1]

            # Detect layout if auto
            if layout == "auto":
                page_layout = table_detector.detect_page_layout(page)
            else:
                page_layout = layout

            tables_info = table_detector.find_tables_on_page(page, page_layout)
            tables_info = table_detector.filter_tables(tables_info, min_cols=1, min_rows=1)

            if tables_info:
                layout_tag = f" [{page_layout}列]" if page_layout == "double" else ""
                print(f"  第{page_num}页{layout_tag}:")

            for item in tables_info:
                found = True
                table = item[0]
                is_merged = item[1]
                bbox = item[2]

                meta = table_detector.get_table_metadata(item, page_num, 0)
                merged_tag = " [已合并]" if is_merged else ""
                print(f"    表格: {meta['rows']}行 x {meta['cols']}列{merged_tag}  "
                      f"位置({bbox[0]:.0f}, {bbox[1]:.0f}) - "
                      f"({bbox[2]:.0f}, {bbox[3]:.0f})")
                print(f"      预览: {meta['preview']}")
                print()

    if not found:
        print("  未检测到表格。")


def process_tables(
    pdf_path: str,
    page_range: list,
    output_dir: str,
    layout: str = "auto",
    dpi: int = 200,
    padding: float = 8,
    min_cols: int = 2,
    min_rows: int = 2,
    verbose: bool = False,
):
    """Detect and crop tables from the specified page range."""
    all_metadata = []
    table_counter = 0

    pdf_plumber = pdfplumber.open(pdf_path)
    doc_fitz = fitz.open(pdf_path)

    try:
        for page_num in page_range:
            page_plumber = pdf_plumber.pages[page_num - 1]
            page_width = page_plumber.width

            # Determine layout for this page
            if layout == "auto":
                page_layout = table_detector.detect_page_layout(page_plumber)
            else:
                page_layout = layout

            tables_info = table_detector.find_tables_on_page(page_plumber, page_layout)
            tables_info = table_detector.filter_tables(tables_info, min_cols, min_rows)

            if not tables_info:
                if verbose:
                    print(f"  第{page_num}页 [{page_layout}列]: 未检测到符合条件的表格")
                continue

            for item in tables_info:
                table_counter += 1
                is_merged = item[1]
                bbox = item[2]

                # Smart crop: full width for merged tables, bbox crop otherwise
                image = table_renderer.crop_table_smart(
                    doc_fitz, page_num, bbox, is_merged, page_width, dpi, padding
                )

                # Save image
                filepath = table_renderer.save_table_image(
                    image, output_dir, page_num, table_counter
                )

                # Record metadata
                meta = table_detector.get_table_metadata(item, page_num, table_counter)
                meta["filepath"] = filepath
                meta["dpi"] = dpi
                all_metadata.append(meta)

                merged_tag = " [已合并]" if is_merged else ""
                if verbose:
                    print(f"  第{page_num}页 [{page_layout}列] 表格{table_counter}{merged_tag}: "
                          f"{meta['rows']}行 x {meta['cols']}列 -> {filepath}")
    finally:
        pdf_plumber.close()
        doc_fitz.close()

    # Generate summary JSON
    summary_path = None
    if all_metadata:
        summary = {
            "pdf_path": os.path.basename(pdf_path),
            "page_range": page_range,
            "layout": layout,
            "total_tables": len(all_metadata),
            "dpi": dpi,
            "tables": all_metadata,
        }
        summary_path = table_renderer.generate_summary(summary, output_dir)

    return all_metadata, summary_path


def main():
    parser = argparse.ArgumentParser(
        description="从PDF指定章节/页面中检测表格并截图保存为PNG图片"
    )
    parser.add_argument("pdf_path", help="PDF文件路径")
    parser.add_argument("--section", help="章节/节标题关键词（如'第3章'、'Chapter 3'、'3.2'）")
    parser.add_argument("--pages", help="页面范围（如'10-25'、'5,8,12'）")
    parser.add_argument("--layout", choices=["auto", "single", "double"], default="auto",
                        help="页面布局：auto（自动检测）、single（单列）、double（双列）(默认: auto)")
    parser.add_argument("--list-sections", action="store_true", help="列出PDF中所有可检测的章节")
    parser.add_argument("--list-tables", action="store_true", help="列出指定范围内的表格位置")
    parser.add_argument("-o", "--output-dir", default="./pdf_tables_output", help="输出目录（默认: ./pdf_tables_output）")
    parser.add_argument("--dpi", type=int, default=200, help="输出图片DPI（默认: 200）")
    parser.add_argument("--padding", type=float, default=8, help="裁剪边距/points（默认: 8）")
    parser.add_argument("--min-cols", type=int, default=2, help="最少列数过滤（默认: 2）")
    parser.add_argument("--min-rows", type=int, default=2, help="最少行数过滤（默认: 2）")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    # Validate PDF exists
    if not os.path.isfile(args.pdf_path):
        print(f"错误: PDF文件不存在: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    # List sections mode
    if args.list_sections:
        list_sections(args.pdf_path)
        return

    # Determine page range
    page_range = None
    if args.section:
        try:
            start, end = section_locator.locate_section(args.pdf_path, args.section)
            page_range = list(range(start, end + 1))
            if args.verbose:
                print(f"章节 '{args.section}' 定位到第{start}页 - 第{end}页")
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            print("提示: 使用 --list-sections 查看可用章节", file=sys.stderr)
            sys.exit(1)
    elif args.pages:
        try:
            reader = __import__("pypdf").PdfReader(args.pdf_path)
            total_pages = len(reader.pages)
            page_range = section_locator.parse_page_range(args.pages, total_pages)
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("错误: 请指定 --section 或 --pages", file=sys.stderr)
        sys.exit(1)

    # List tables mode
    if args.list_tables:
        list_tables(args.pdf_path, page_range, args.layout)
        return

    # Process tables
    print(f"正在处理: {args.pdf_path}")
    print(f"页面范围: {page_range[0]}-{page_range[-1]} ({len(page_range)}页)")
    print(f"布局模式: {args.layout}")
    print(f"输出目录: {os.path.abspath(args.output_dir)}")
    print()

    all_metadata, summary_path = process_tables(
        pdf_path=args.pdf_path,
        page_range=page_range,
        output_dir=args.output_dir,
        layout=args.layout,
        dpi=args.dpi,
        padding=args.padding,
        min_cols=args.min_cols,
        min_rows=args.min_rows,
        verbose=args.verbose,
    )

    # Report results
    if all_metadata:
        print(f"\n完成! 共截取 {len(all_metadata)} 个表格:")
        for meta in all_metadata:
            merged_tag = " [已合并]" if meta.get("merged") else ""
            print(f"  第{meta['page']}页 表格{meta['index']}{merged_tag}: "
                  f"{meta['rows']}行 x {meta['cols']}列 -> {meta['filepath']}")
        if summary_path:
            print(f"\n摘要文件: {summary_path}")
    else:
        print("\n未检测到符合条件的表格。")
        print("提示: 尝试降低 --min-cols 或 --min-rows 的值，或使用 --layout double 强制双列模式")


if __name__ == "__main__":
    main()
