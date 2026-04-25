# Section/Chapter Heading Patterns

## Chinese Patterns

| Pattern | Description | Example |
|---------|-------------|---------|
| `第[一二三四五六七八九十百千\d]+章\s*.*` | Chapter heading | 第三章 数据结构 |
| `第[一二三四五六七八九十百千\d]+节\s*.*` | Section heading | 第二节 算法分析 |
| `第[一二三四五六七八九十百千\d]+篇\s*.*` | Part heading | 第一篇 概述 |
| `第[一二三四五六七八九十百千\d]+部分\s*.*` | Part heading | 第一部分 基础知识 |
| `\d+[\.\、]\s*\S+.*` | Numbered sections | 3.2 排序算法 |

## English Patterns

| Pattern | Description | Example |
|---------|-------------|---------|
| `(?i)^chapter\s+\d+[\.:]?\s*.*` | Chapter heading | Chapter 3: Methods |
| `(?i)^section\s+\d+[\.:]?\s*.*` | Section heading | Section 3.2 Analysis |
| `(?i)^part\s+[IVXLCDM\d]+[\.:]?\s*.*` | Part heading | Part II: Results |
| `^\d+[\.\)]\s+[A-Z].*` | Numbered heading | 3. Introduction |
| `^\d+\.\d+\s+[A-Z].*` | Sub-section | 3.2.1 Data Collection |

## Matching Logic

1. Extract text from each page using pdfplumber
2. Check first 10 lines (headings typically appear near the top)
3. Lines must be non-empty and under 100 characters (avoid matching body text)
4. First pattern match on a page wins
5. Keywords support fuzzy Chinese number matching (e.g., "第3章" matches "第三章")

## Keyword Fuzzy Matching

The `section_locator.py` normalizes Chinese numerals for comparison:

| Input | Normalized |
|-------|-----------|
| 第3章 | 第3章 |
| 第三章 | 第3章 |
| 第十二节 | 第12节 |
| Chapter 3 | chapter 3 |

This allows users to type either Arabic or Chinese numerals.
