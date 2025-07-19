
import pymupdf
import json
import os

def extract_headings_and_title(pdf_path):
    document = pymupdf.open(pdf_path)
    headings = []
    document_title = "Untitled" # Default title

    all_spans_with_pages = []
    max_overall_font_size = 0.0

    # First pass: Collect all spans and determine overall max font size
    for page_number, page in enumerate(document):
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:  # Text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                            all_spans_with_pages.append({
                                "text": text,
                                "font_size": round(span["size"], 2),
                                "font_name": span["font"],
                                "bbox": [round(coord, 2) for coord in span["bbox"]],
                                "page_number": page_number + 1
                            })
                            if span["size"] > max_overall_font_size:
                                max_overall_font_size = span["size"]

    # Identify the document title (heuristic: largest text on first few pages)
    if all_spans_with_pages:
        sorted_spans = sorted(all_spans_with_pages, key=lambda x: x["font_size"], reverse=True)
        for span_data in sorted_spans:
            if span_data["page_number"] <= 3 and span_data["font_size"] >= max_overall_font_size * 0.9:
                document_title = span_data["text"]
                break

    # Determine heading font sizes based on distribution
    unique_font_sizes = sorted(list(set([s['font_size'] for s in all_spans_with_pages])), reverse=True)
    
    # Heuristic for H1, H2, H3: Take the top distinct font sizes.
    # This might need manual adjustment or more sophisticated clustering for diverse PDFs.
    h1_size = unique_font_sizes[0] if len(unique_font_sizes) > 0 else 0
    h2_size = unique_font_sizes[1] if len(unique_font_sizes) > 1 else 0
    h3_size = unique_font_sizes[2] if len(unique_font_sizes) > 2 else 0

    # Adjust thresholds based on actual observed font sizes for better accuracy
    # For example, if H1 is 24pt, H2 is 18pt, H3 is 14pt.
    # We can try to identify these prominent sizes.

    # Second pass: Process lines to identify and combine headings
    current_page_number = -1
    current_line_text = ""
    current_line_font_size = 0.0
    current_line_level = None
    
    # Group spans by line (using approximate y-coordinate) and then identify headings
    lines_on_page = {}
    for span_data in all_spans_with_pages:
        page_num = span_data["page_number"]
        y0 = span_data["bbox"][1] # Top-left y-coordinate
        
        if page_num not in lines_on_page:
            lines_on_page[page_num] = []
            
        # Try to group spans that are on the same visual line
        # A small tolerance for y-coordinate difference is used.
        line_found = False
        for i, line_group in enumerate(lines_on_page[page_num]):
            # If the span's y0 is close to an existing line's y0, add it to that line
            if abs(y0 - line_group["y0"]) < 3: # Tolerance for "same line"
                line_group["spans"].append(span_data)
                line_group["spans"].sort(key=lambda x: x["bbox"][0]) # Sort by x-coordinate
                line_found = True
                break
        if not line_found:
            lines_on_page[page_num].append({"y0": y0, "spans": [span_data]})
            
    for page_num in sorted(lines_on_page.keys()):
        # Sort lines by their y-coordinate to process them in reading order
        sorted_lines = sorted(lines_on_page[page_num], key=lambda x: x["y0"])
        
        for line_group in sorted_lines:
            combined_text = " ".join([span["text"] for span in line_group["spans"]]).strip()
            # Determine the predominant font size for this line
            # This can be the largest font size within the line or the most frequent.
            # For simplicity, let's take the font size of the first span.
            if line_group["spans"]:
                dominant_font_size = line_group["spans"][0]["font_size"]
                
                level = None
                # Refined categorization based on prominent font sizes
                if abs(dominant_font_size - h1_size) < 2.0 and h1_size > 0:
                    level = "H1"
                elif abs(dominant_font_size - h2_size) < 2.0 and h2_size > 0:
                    level = "H2"
                elif abs(dominant_font_size - h3_size) < 2.0 and h3_size > 0:
                    level = "H3"
                
                # Further heuristic: Check for common heading patterns (e.g., starts with number and period)
                # and if it's visually distinct (e.g., bold or significantly larger than surrounding text).
                # For this specific case, the image shows a large, bold "3. Overview..." which is a strong H1 candidate.
                # Let's prioritize font size and then simple heuristics.
                
                # If a line is identified as a heading, add it.
                if level and combined_text:
                    # Filter out short, non-descriptive texts that might accidentally get a heading font size
                    # (e.g., page numbers in a large font in headers/footers, unless they are actual headings)
                    if len(combined_text) > 3 or (combined_text.strip().isdigit() and combined_text.strip() == str(page_num)):
                        headings.append({
                            "level": level,
                            "text": combined_text,
                            "page": page_num
                        })

    # Deduplicate and sort
    unique_headings = []
    seen_headings = set()
    for heading in headings:
        key = (heading["level"], heading["text"], heading["page"])
        if key not in seen_headings:
            unique_headings.append(heading)
            seen_headings.add(key)
    
    unique_headings.sort(key=lambda x: (x["page"], x["text"])) # Sort by page then text for consistent ordering

    document.close()
    return {"title": document_title, "outline": unique_headings}

if __name__ == "__main__":
    input_dir = "input"
    output_dir = "output"
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # Example: Process all PDFs in the input directory
    for filename in os.listdir(input_dir):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(input_dir, filename)
            print(f"Processing {pdf_path}...")
            
            # Extract title and headings
            extracted_outline = extract_headings_and_title(pdf_path)

            # Define output JSON path
            output_json_filename = os.path.splitext(filename)[0] + ".json"
            output_json_path = os.path.join(output_dir, output_json_filename)

            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_outline, f, indent=4, ensure_ascii=False)

            print(f"Extracted outline saved to: {output_json_path}")
            print("\nSample of extracted outline:")
            print(json.dumps(extracted_outline, indent=4, ensure_ascii=False))
            print("-" * 50)
