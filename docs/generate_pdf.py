#!/usr/bin/env python
"""Convert userguide.md to PDF."""

import markdown2
from weasyprint import HTML, CSS
from pathlib import Path

# Paths
docs_dir = Path(__file__).parent
md_path = docs_dir / "userguide.md"
pdf_path = docs_dir / "userguide.pdf"
css_path = docs_dir / "pdf_style.css"

# Read markdown
with open(md_path, "r", encoding="utf-8") as f:
    md_content = f.read()

# Convert to HTML
html_content = markdown2.markdown(
    md_content,
    extras=["tables", "fenced-code-blocks", "toc", "code-friendly"]
)

# Wrap in full HTML document
full_html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Yat - Руководство пользователя</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{
            font-family: "Segoe UI", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        h1 {{
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 0.5em;
        }}
        h2 {{
            color: #764ba2;
            margin-top: 1.5em;
        }}
        h3 {{
            color: #555;
        }}
        code {{
            background: #f4f4f4;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: "Consolas", "Courier New", monospace;
        }}
        pre {{
            background: #f4f4f4;
            padding: 1em;
            border-radius: 5px;
            overflow-x: auto;
        }}
        blockquote {{
            border-left: 4px solid #667eea;
            margin: 1em 0;
            padding-left: 1em;
            color: #666;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 0.5em 1em;
            text-align: left;
        }}
        th {{
            background: #667eea;
            color: white;
        }}
        tr:nth-child(even) {{
            background: #f9f9f9;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 1em auto;
        }}
        ul, ol {{
            margin: 0.5em 0;
            padding-left: 2em;
        }}
        a {{
            color: #667eea;
            text-decoration: none;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>
"""

# Generate PDF
print(f"Converting {md_path.name} to PDF...")
html_doc = HTML(string=full_html, base_url=str(docs_dir))
html_doc.write_pdf(str(pdf_path))

print(f"[OK] PDF created: {pdf_path}")
