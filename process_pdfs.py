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
            if block["type"] == 0:
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

    merged_lines_data = []
    if all_lines_data:
        current_merged_line = all_lines_data[0]
        for i in range(1, len(all_lines_data)):
            next_line = all_lines_data[i]

            vertical_distance = next_line["line_y0"] - current_merged_line["line_y1"]
            line_height_threshold = current_merged_line["line_y1"] - current_merged_line["line_y0"]

            if (next_line["page_number"] == current_merged_line["page_number"] and
                vertical_distance < (line_height_threshold * 0.75) and
                abs(next_line["font_size"] - current_merged_line["font_size"]) < 0.5 and
                next_line["is_bold"] == current_merged_line["is_bold"] and
                abs(next_line["line_x0"] - current_merged_line["line_x0"]) < 5):

                current_merged_line["text"] += " " + next_line["text"]
                current_merged_line["bbox"][3] = next_line["bbox"][3]
                current_merged_line["line_y1"] = next_line["line_y1"]
            else:
                merged_lines_data.append(current_merged_line)
                current_merged_line = next_line
        merged_lines_data.append(current_merged_line)

    all_lines_data = merged_lines_data

    potential_headings = []
    
    all_font_sizes = [line["font_size"] for line in all_lines_data if line["font_size"] > 0]
    min_global_font_size = min(all_font_sizes) if all_font_sizes else 0
    max_global_font_size = max(all_font_sizes) if all_font_sizes else 0

    for i, current_line in enumerate(all_lines_data):
        combined_text = current_line["text"]
        dominant_font_size = current_line["font_size"]
        dominant_is_bold = current_line["is_bold"]
        page_num = current_line["page_number"]

        heading_confidence = 0.0

        if dominant_font_size > 0:
            if max_global_font_size > min_global_font_size:
                font_size_normalized = (dominant_font_size - min_global_font_size) / (max_global_font_size - min_global_font_size)
                heading_confidence += font_size_normalized * 0.3
            elif dominant_font_size >= 12:
                 heading_confidence += 0.15

        if dominant_is_bold:
            heading_confidence += 0.3

        line_height = current_line["line_y1"] - current_line["line_y0"]
        space_to_next_line = 0
        if i + 1 < len(all_lines_data) and all_lines_data[i+1]["page_number"] == page_num:
            next_line = all_lines_data[i+1]
            space_to_next_line = next_line["line_y0"] - current_line["line_y1"]

        if space_to_next_line > (line_height * 1.5):
            heading_confidence += 0.15
        elif space_to_next_line > (line_height * 0.75):
            heading_confidence += 0.05

        if current_line["line_x0"] < 80:
            heading_confidence += 0.1

        if combined_text.isupper() and len(combined_text.split()) > 1 and len(combined_text) > 5:
            heading_confidence += 0.1

        is_numbered_heading = bool(re.match(r"^\s*([0-9]+\.?(\d+\.?)*|[A-Za-z]\.?|[IVXLCDM]+\.)\s+.*", combined_text))
        if is_numbered_heading:
            heading_confidence += 0.15

        if len(combined_text.strip()) < 5:
            heading_confidence *= 0.1

        if dominant_font_size < 9:
            heading_confidence *= 0.2

        if document_title == "Untitled Document" and page_num == 1 and dominant_font_size > (max_global_font_size * 0.8) and heading_confidence > 0.5:
            document_title = combined_text
            heading_confidence = 1.0

        if heading_confidence > 0.35:
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

    potential_headings.sort(key=lambda x: (x["page"], x["heading_confidence"], x["font_size"]), reverse=True)

    unique_heading_font_sizes = sorted(list(set(h["font_size"] for h in potential_headings)), reverse=True)

    font_size_clusters = []
    if unique_heading_font_sizes:
        current_cluster = [unique_heading_font_sizes[0]]
        for i in range(1, len(unique_heading_font_sizes)):
            if abs(unique_heading_font_sizes[i] - current_cluster[-1]) < 1.5:
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
        
        if assigned_level:
            final_headings.append({
                "level": assigned_level,
                "text": heading["text"],
                "page": heading["page"],
                'heading_confidence': heading['heading_confidence']
            })

    final_headings.sort(key=lambda x: (x["page"], x["text"]))

    unique_final_headings = []
    seen_keys = set()
    for heading in final_headings:
        key = (heading["level"], heading["text"], heading["page"])
        if key not in seen_keys:
            unique_final_headings.append(heading)
            seen_keys.add(key)
    
    unique_final_headings.sort(key=lambda x: (x["page"],
                                                0 if x["level"] == "H1" else \
                                                1 if x["level"] == "H2" else \
                                                2 if x["level"] == "H3" else 3,
                                                x["text"]))

    document.close()
    return {"title": document_title, "outline": unique_final_headings}

if __name__ == "__main__":
    input_dir = "input"
    output_dir = "output"
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

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