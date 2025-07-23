import pymupdf
import json
import os
import re
from collections import defaultdict

def extract_headings_and_title(pdf_path):
    document = pymupdf.open(pdf_path)

    document_title = document.metadata.get("title", "Untitled Document")
    if not document_title or document_title.strip() == "":
        document_title = "Untitled Document"

    all_lines_data = []

    for page_number, page in enumerate(document):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:  # Text block
                for line_idx, line in enumerate(block["lines"]):
                    line_text = " ".join([span["text"].strip() for span in line["spans"]]).strip()
                    if not line_text:
                        continue

                    dominant_font_size = 0.0
                    dominant_is_bold = False
                    if line["spans"]:
                        dominant_font_size = round(line["spans"][0]["size"], 2)
                        dominant_is_bold = any((span["flags"] & 2**4) != 0 for span in line["spans"])

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

    all_lines_data.sort(key=lambda x: (x["page_number"], x["line_y0"]))

    # --- AGGRESSIVE MERGING LOGIC ---
    merged_lines_data = []
    if all_lines_data:
        current_merged_line = dict(all_lines_data[0])
        for i in range(1, len(all_lines_data)):
            next_line = all_lines_data[i]

            current_line_height = current_merged_line["line_y1"] - current_merged_line["line_y0"]
            avg_line_height = (current_line_height + (next_line["line_y1"] - next_line["line_y0"])) / 2
            
            vertical_distance = next_line["line_y0"] - current_merged_line["line_y1"]

            horizontal_overlap = max(0, min(current_merged_line["bbox"][2], next_line["bbox"][2]) - 
                                     max(current_merged_line["bbox"][0], next_line["bbox"][0]))
            
            min_overlap_width = min(current_merged_line["bbox"][2] - current_merged_line["bbox"][0],
                                    next_line["bbox"][2] - next_line["bbox"][0]) * 0.25

            is_short_continuation = (len(next_line["text"].split()) <= 3 and 
                                     vertical_distance < (current_line_height * 1.0) and 
                                     abs(next_line["line_x0"] - current_merged_line["line_x0"]) < 50)

            if (next_line["page_number"] == current_merged_line["page_number"] and
                vertical_distance < (avg_line_height * 2.5) and  
                abs(next_line["font_size"] - current_merged_line["font_size"]) < 2.0 and 
                next_line["is_bold"] == current_merged_line["is_bold"] and
                (horizontal_overlap > min_overlap_width or is_short_continuation)):
                
                current_merged_line["text"] += " " + next_line["text"]
                current_merged_line["bbox"][3] = next_line["bbox"][3]
                current_merged_line["line_y1"] = next_line["line_y1"] # Fixed variable name here
            else:
                merged_lines_data.append(current_merged_line)
                current_merged_line = dict(next_line)
        merged_lines_data.append(current_merged_line)

    all_lines_data = merged_lines_data

    potential_headings = []
    
    all_font_sizes = [line["font_size"] for line in all_lines_data if line["font_size"] > 0]
    min_global_font_size = min(all_font_sizes) if all_font_sizes else 0
    max_global_font_size = max(all_font_sizes) if all_font_sizes else 0

    page_font_sizes = defaultdict(list)
    for line in all_lines_data:
        if line["font_size"] > 0:
            page_font_sizes[line["page_number"]].append(line["font_size"])

    for i, current_line in enumerate(all_lines_data):
        combined_text = current_line["text"].strip()
        dominant_font_size = current_line["font_size"]
        dominant_is_bold = current_line["is_bold"]
        page_num = current_line["page_number"]

        heading_confidence = 0.0

        # --- Font Size Analysis ---
        if dominant_font_size > 0:
            if max_global_font_size > min_global_font_size:
                font_size_normalized = (dominant_font_size - min_global_font_size) / (max_global_font_size - min_global_font_size)
                heading_confidence += font_size_normalized * 0.35 
            elif dominant_font_size >= 11:
                heading_confidence += 0.15

            if page_font_sizes[page_num]:
                max_page_font_size = max(page_font_sizes[page_num])
                if dominant_font_size >= max_page_font_size * 0.9: 
                    heading_confidence += 0.15
                elif dominant_font_size >= max_page_font_size * 0.7:
                    heading_confidence += 0.05
        
        # --- Bolding ---
        if dominant_is_bold:
            heading_confidence += 0.3 

        # --- Spacing Analysis (as previously enhanced) ---
        line_height = current_line["line_y1"] - current_line["line_y0"]
        space_to_next_line = 0
        next_is_body_text = False # New flag to check for body text below

        if i + 1 < len(all_lines_data) and all_lines_data[i+1]["page_number"] == page_num:
            next_line = all_lines_data[i+1]
            space_to_next_line = next_line["line_y0"] - current_line["line_y1"]

            # --- CHECK FOR BODY TEXT BELOW ---
            # Criteria for body text: not bold, smaller font than current line, reasonable length
            if (not next_line["is_bold"] and
                next_line["font_size"] < dominant_font_size * 0.9 and # Next line font is significantly smaller
                next_line["font_size"] >= min_global_font_size * 0.9 and # But not too small (e.g., footers)
                len(next_line["text"].split()) > 4 and # Likely a paragraph, not a short label
                space_to_next_line >= 3 # Some space, but not necessarily huge
               ):
                next_is_body_text = True
                heading_confidence += 0.4 # Significantly increased weight

        if combined_text == '4.2 Documents and Web Sites':
            print(f"Current Line (Heading): {current_line}")
            if i + 1 < len(all_lines_data) and all_lines_data[i+1]["page_number"] == page_num:
                print(f"Next Line (Potential Body Text): {all_lines_data[i+1]}")
            else:
                print("No next line on the same page or end of document.")
            print(f"next_is_body_text: {next_is_body_text}")
        if space_to_next_line > (line_height * 2.0):
            heading_confidence += 0.35
        elif space_to_next_line > (line_height * 1.5):
            heading_confidence += 0.2
        elif space_to_next_line > (line_height * 1.0):
            heading_confidence += 0.1
        
        space_from_previous_line = 0
        if i > 0 and all_lines_data[i-1]["page_number"] == page_num:
            previous_line = all_lines_data[i-1]
            space_from_previous_line = current_line["line_y0"] - previous_line["line_y1"]
            if space_from_previous_line > (line_height * 1.5):
                heading_confidence += 0.1
            elif space_from_previous_line > (line_height * 1.0):
                heading_confidence += 0.05

        # --- Positional Cues ---
        if current_line["line_x0"] < 100: 
            heading_confidence += 0.1

        # --- Text Content Analysis ---
        if combined_text.isupper() and len(combined_text.split()) > 1 and len(combined_text) > 3: 
            heading_confidence += 0.1

        is_numbered_heading = bool(re.match(r"^\s*(\d+(\.\d+)*|[A-Z]\.?|[IVXLCDM]+\.)\s+.*", combined_text, re.IGNORECASE))
        if is_numbered_heading:
            heading_confidence += 0.15

        if re.search(r"^(chapter|section|appendix|introduction|conclusion|references)\s+\d*(\.\d*)*", combined_text, re.IGNORECASE):
            heading_confidence += 0.15

        # Penalties for text unlikely to be a heading
        if len(combined_text.split()) > 15: 
            heading_confidence *= 0.7
        if len(combined_text.strip()) < 3: 
            heading_confidence *= 0.5
        if dominant_font_size < 8: 
            heading_confidence *= 0.1

        # Special handling for document title if not already found
        if document_title == "Untitled Document" and page_num == 1:
            if dominant_font_size >= (max_global_font_size * 0.8) and heading_confidence > 0.4:
                document_title = combined_text
                heading_confidence = 1.0 

        if re.fullmatch(r"[\.\-_—\s]+", combined_text): 
            heading_confidence *= 0.05 

        alphanum_chars = sum(c.isalnum() for c in combined_text)
        if alphanum_chars < 5 and len(combined_text) > 10: 
            heading_confidence *= 0.1 

        # Final confidence threshold
        if heading_confidence > 0.70: 
            potential_headings.append({
                "text": combined_text,
                "font_size": dominant_font_size,
                "page": page_num,
                "is_bold": dominant_is_bold,
                "x0": current_line["bbox"][0],
                "line_height": line_height,
                "space_after": space_to_next_line,
                "heading_confidence": heading_confidence
            })

    potential_headings.sort(key=lambda x: (x["heading_confidence"], x["font_size"]), reverse=True)

    unique_heading_font_sizes = sorted(list(set(h["font_size"] for h in potential_headings)), reverse=True)

    font_size_clusters = []
    if unique_heading_font_sizes:
        current_cluster = [unique_heading_font_sizes[0]]
        for i in range(1, len(unique_heading_font_sizes)):
            if abs(unique_heading_font_sizes[i] - current_cluster[-1]) < 1.0: 
                current_cluster.append(unique_heading_font_sizes[i])
            else:
                font_size_clusters.append(current_cluster)
                current_cluster = [unique_heading_font_sizes[i]]
        font_size_clusters.append(current_cluster)

    font_size_clusters.sort(key=lambda c: sum(c) / len(c), reverse=True)

    heading_level_font_ranges = {}
    if len(font_size_clusters) >= 1:
        h1_min = min(font_size_clusters[0])
        h1_max = max(font_size_clusters[0])
        heading_level_font_ranges["H1"] = (h1_min, h1_max)
    if len(font_size_clusters) >= 2:
        h2_min = min(font_size_clusters[1])
        h2_max = max(font_size_clusters[1])
        heading_level_font_ranges["H2"] = (h2_min, h2_max)
    if len(font_size_clusters) >= 3:
        h3_min = min(font_size_clusters[2])
        h3_max = max(font_size_clusters[2])
        heading_level_font_ranges["H3"] = (h3_min, h3_max)

    final_headings = []
    
    for heading in potential_headings:
        assigned_level = None
        current_font_size = heading["font_size"]

        if "H1" in heading_level_font_ranges and \
           heading_level_font_ranges["H1"][0] <= current_font_size <= heading_level_font_ranges["H1"][1]:
            assigned_level = "H1"
        elif "H2" in heading_level_font_ranges and \
             heading_level_font_ranges["H2"][0] <= current_font_size <= heading_level_font_ranges["H2"][1]:
            assigned_level = "H2"
        elif "H3" in heading_level_font_ranges and \
             heading_level_font_ranges["H3"][0] <= current_font_size <= heading_level_font_ranges["H3"][1]:
            assigned_level = "H3"
        else:
            if heading["heading_confidence"] > 0.30: 
                if "H1" in heading_level_font_ranges and current_font_size > heading_level_font_ranges["H1"][0] * 0.8:
                    assigned_level = "H1"
                elif "H2" in heading_level_font_ranges and current_font_size > heading_level_font_ranges["H2"][0] * 0.8:
                    assigned_level = "H2"
                elif "H3" in heading_level_font_ranges and current_font_size > heading_level_font_ranges["H3"][0] * 0.8:
                    assigned_level = "H3"
                else:
                    assigned_level = "H4" 
        
        if assigned_level:
            final_headings.append({
                "level": assigned_level,
                "text": heading["text"],
                "page": heading["page"],
                'heading_confidence': heading['heading_confidence']
            })

    final_headings.sort(key=lambda x: (x["page"],
                                         0 if x["level"] == "H1" else \
                                         1 if x["level"] == "H2" else \
                                         2 if x["level"] == "H3" else 3,
                                         x["text"]))

    unique_final_headings = []
    seen_keys = set()
    for heading in final_headings:
        key = (heading["level"], heading["text"], heading["page"])
        if key not in seen_keys:
            unique_final_headings.append(heading)
            seen_keys.add(key)
    
    document.close()
    return {"title": document_title, "outline": unique_final_headings}

if __name__ == "__main__":
    input_dir = "input"
    output_dir = "output"
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # Create a dummy PDF for testing purposes (requires reportlab)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER

        def create_dummy_pdf(output_filename="test_document.pdf"):
            doc = SimpleDocTemplate(os.path.join(input_dir, output_filename), pagesize=letter)
            styles = getSampleStyleSheet()
            story = []

            # Custom styles for headings
            h1_style = ParagraphStyle('h1',
                                      parent=styles['h1'],
                                      fontSize=24,
                                      leading=28,
                                      spaceAfter=20,
                                      alignment=TA_CENTER,
                                      fontName='Helvetica-Bold')
            h2_style = ParagraphStyle('h2',
                                      parent=styles['h2'],
                                      fontSize=18,
                                      leading=22,
                                      spaceAfter=15,
                                      fontName='Helvetica-Bold')
            h3_style = ParagraphStyle('h3',
                                      parent=styles['h3'],
                                      fontSize=14,
                                      leading=18,
                                      spaceAfter=10,
                                      fontName='Helvetica-Bold')
            
            # Simulate your specific case: multi-line H1
            story.append(Paragraph("3. Overview of the Foundation Level Extension –", h1_style))
            story.append(Paragraph("Agile Tester Syllabus", h1_style)) 
            story.append(Spacer(1, 0.5 * 72))

            # Another multi-line H1 example
            story.append(Paragraph("A Comprehensive Guide to", h1_style))
            story.append(Paragraph("Software Development Life Cycle", h1_style)) 
            story.append(Spacer(1, 0.5 * 72)) 

            story.append(Paragraph("1. Introduction to Testing", h2_style))
            story.append(Paragraph("This is some body text for the introduction section. It provides an overview of the document's content and purpose.", styles['Normal'])) # <-- This is the body text
            story.append(Spacer(1, 0.2 * 72))

            story.append(Paragraph("1.1 Types of Testing", h3_style))
            story.append(Paragraph("Here we discuss different types of testing methodologies. This paragraph is also body text.", styles['Normal'])) # <-- Another body text
            story.append(Spacer(1, 0.2 * 72))

            story.append(Paragraph("2. Test Design Techniques", h2_style))
            story.append(Paragraph("This section covers various test design techniques in detail.", styles['Normal']))
            story.append(Spacer(1, 0.2 * 72))

            story.append(Paragraph("2.1 Black-Box Testing", h3_style))
            story.append(Paragraph("An overview of black-box testing methods.", styles['Normal']))
            story.append(Spacer(1, 0.2 * 72))
            
            story.append(Paragraph("2.1.1 Equivalence Partitioning", styles['Normal'] )) 
            story.append(Spacer(1, 0.2 * 72))


            doc.build(story)
            print(f"Dummy PDF '{output_filename}' created in '{input_dir}' for testing.")
        
        create_dummy_pdf()

    except ImportError:
        print("ReportLab not found. Cannot create dummy PDF. Please ensure you have PDF files in the 'input' directory to run the script.")
        print("You can install ReportLab using: pip install reportlab")
    except Exception as e:
        print(f"An error occurred while creating the dummy PDF: {e}")

    for filename in os.listdir(input_dir):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(input_dir, filename)
            print(f"Processing {pdf_path}...")

            extracted_outline = extract_headings_and_title(pdf_path)

            output_json_filename = os.path.splitext(filename)[0] + ".json"
            output_json_path = os.path.join(output_dir, output_json_filename)

            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_outline, f, indent=4, ensure_ascii=False)

            print(f"Extracted outline saved to: {output_json_path}")
            print("\nSample of extracted outline:")
            print(json.dumps(extracted_outline, indent=4, ensure_ascii=False))
            print("-" * 50)