import pymupdf
from collections import defaultdict

def load_pdf(pdf_path):
    """Load a PDF file and return the document object."""
    return pymupdf.open(pdf_path)

def get_document_title(document):
    """Extract the document title from metadata, defaulting to 'Untitled Document'."""
    title = document.metadata.get("title", "Untitled Document")
    return title if title and title.strip() else "Untitled Document"

def extract_text_blocks(document):
    """Extract text blocks from all pages of the document."""
    all_lines_data = []
    
    for page_number, page in enumerate(document):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:  # Text block
                for line in block["lines"]:
                    line_text = " ".join([span["text"].strip() for span in line["spans"]]).strip()
                    if not line_text:
                        continue
                    
                    dominant_font_size = round(line["spans"][0]["size"], 2) if line["spans"] else 0.0
                    dominant_is_bold = any((span["flags"] & 2**4) != 0 for span in line["spans"]) if line["spans"] else False
                    
                    all_lines_data.append({
                        "text": line_text,
                        "font_size": dominant_font_size,
                        "bbox": [round(coord, 2) for coord in line["bbox"]],
                        "page_number": page_number + 1,
                        "is_bold": dominant_is_bold,
                        "line_y0": round(line["bbox"][1], 2),
                        "line_x0": round(line["bbox"][0], 2),
                        "line_y1": round(line["bbox"][3], 2)
                    })
    
    return all_lines_data

def close_document(document):
    """Close the PDF document to free resources."""
    document.close()