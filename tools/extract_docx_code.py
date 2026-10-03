from pathlib import Path

from docx import Document


SOURCE = Path(r"D:\桌面\page代碼.docx")
OUTPUT = Path(r"D:\ethnic_dance_project\page_from_doc.tsx")


document = Document(SOURCE)
code = "\n".join(paragraph.text for paragraph in document.paragraphs)
OUTPUT.write_text(code, encoding="utf-8")
print(f"Extracted {len(code)} characters to {OUTPUT}")
