import pymupdf
import json
import os
import re
from collections import defaultdict
import time
import logging
from datetime import datetime

# Set up logging for debugging and performance tracking
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_keywords(persona, job_to_be_done):
    """Extract keywords from persona and job-to-be-done for relevance scoring."""
    # Combine persona and job-to-be-done, convert to lowercase, and split into words
    text = f"{persona} {job_to_be_done}".lower()
    words = re.findall(r'\b\w+\b', text)
    # Filter out common stopwords and short words
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    keywords = [word for word in words if word not in stopwords and len(word) > 3]
    # Add specific phrases from job-to-be-done (e.g., "literature review", "revenue trends")
    phrases = re.findall(r'"([^"]+)"|(\b\w+\s+\w+\b)', job_to_be_done.lower())
    phrases = [p[0] or p[1] for p in phrases if p[0] or p[1]]
    keywords.extend(phrases)
    return list(set(keywords))

def process_page(page, page_number):
    """Process a single page to extract text lines with metadata."""
    try:
        blocks = page.get_text("dict")["blocks"]
        lines_data = []
        for block in blocks:
            if block["type"] == 0:  # Text block
                for line in block["lines"]:
                    line_text = " ".join([span["text"].strip() for span in line["spans"]]).strip()
                    if not line_text:
                        continue
                    dominant_font_size = round(line["spans"][0]["size"], 2) if line["spans"] else 0.0
                    dominant_is_bold = any((span["flags"] & 2**4) != 0 for span in line["spans"]) if line["spans"] else False
                    lines_data.append({
                        "text": line_text,
                        "font_size": dominant_font_size,
                        "bbox": [round(coord, 2) for coord in line["bbox"]],
                        "page_number": page_number + 1,
                        "is_bold": dominant_is_bold,
                        "line_y0": round(line["bbox"][1], 2),
                        "line_x0": round(line["bbox"][0], 2),
                        "line_y1": round(line["bbox"][3], 2)
                    })
        return lines_data
    except Exception as e:
        logger.error(f"Error processing page {page_number + 1}: {e}")
        return []

def extract_headings_and_content(pdf_path):
    """Extract structured outline and section content from a PDF."""
    try:
        document = pymupdf.open(pdf_path)
    except Exception as e:
        logger.error(f"Failed to open PDF {pdf_path}: {e}")
        return {"title": "Untitled Document", "outline": [], "content": []}

    # Extract document title
    document_title = document.metadata.get("title", "Untitled Document")
    if not document_title or document_title.strip() == "":
        document_title = "Untitled Document"

    # Extract Table of Contents
    toc = document.get_toc(simple=False)
    toc_headings = [
        {"level": f"H{min(level, 3)}", "text": title, "page": page}
        for level, title, page in toc if page > 0 and title.strip()
    ]

    # Process pages sequentially
    all_lines_data = []
    for page_num in range(document.page_count):
        lines_data = process_page(document[page_num], page_num)
        all_lines_data.extend(lines_data)

    if not all_lines_data:
        document.close()
        logger.warning(f"No text found in {pdf_path}")
        return {"title": document_title, "outline": toc_headings, "content": []}

    # Sort lines by page and y-coordinate
    all_lines_data.sort(key=lambda x: (x["page_number"], x["line_y0"]))

    # Merge fragmented lines
    merged_lines_data = []
    current_merged_line = dict(all_lines_data[0])
    for i in range(1, len(all_lines_data)):
        next_line = all_lines_data[i]
        current_line_height = current_merged_line["line_y1"] - current_merged_line["line_y0"]
        vertical_distance = next_line["line_y0"] - current_merged_line["line_y1"]
        horizontal_overlap = max(0, min(current_merged_line["bbox"][2], next_line["bbox"][2]) -
                                max(current_merged_line["bbox"][0], next_line["bbox"][0]))
        min_overlap_width = min(current_merged_line["bbox"][2] - current_merged_line["bbox"][0],
                                next_line["bbox"][2] - next_line["bbox"][0]) * 0.25

        if (next_line["page_number"] == current_merged_line["page_number"] and
                vertical_distance < (current_line_height * 1.5) and
                abs(next_line["font_size"] - current_merged_line["font_size"]) < 1.0 and
                next_line["is_bold"] == current_merged_line["is_bold"] and
                horizontal_overlap > min_overlap_width):
            current_merged_line["text"] += " " + next_line["text"]
            current_merged_line["bbox"][3] = next_line["bbox"][3]
            current_merged_line["line_y1"] = next_line["line_y1"]
        else:
            merged_lines_data.append(current_merged_line)
            current_merged_line = dict(next_line)
    merged_lines_data.append(current_merged_line)

    # Collect font sizes for normalization
    all_font_sizes = [line["font_size"] for line in merged_lines_data if line["font_size"] > 0]
    min_font_size = min(all_font_sizes, default=0)
    max_font_size = max(all_font_sizes, default=0)
    page_font_sizes = defaultdict(list)
    for line in merged_lines_data:
        if line["font_size"] > 0:
            page_font_sizes[line["page_number"]].append(line["font_size"])

    # Identify potential headings
    potential_headings = []
    for i, line in enumerate(merged_lines_data):
        text = line["text"].strip()
        if not text or re.fullmatch(r"[\.\-_—\s]+", text):
            continue

        confidence = 0.0
        font_size = line["font_size"]
        page_num = line["page_number"]
        is_bold = line["is_bold"]
        line_height = line["line_y1"] - line["line_y0"]

        # Font size-based confidence
        if max_font_size > min_font_size and font_size > 0:
            font_size_normalized = (font_size - min_font_size) / (max_font_size - min_font_size)
            confidence += font_size_normalized * 0.4
        elif font_size >= 11:
            confidence += 0.2

        # Page-specific font size prominence
        if page_font_sizes[page_num]:
            max_page_font_size = max(page_font_sizes[page_num])
            if font_size >= max_page_font_size * 0.9:
                confidence += 0.2

        # Boldness
        if is_bold:
            confidence += 0.3

        # Spacing analysis
        space_after = 0
        if i + 1 < len(merged_lines_data) and merged_lines_data[i+1]["page_number"] == page_num:
            space_after = merged_lines_data[i+1]["line_y0"] - line["line_y1"]
            if space_after > line_height * 1.5:
                confidence += 0.2

        # Structural cues
        if line["line_x0"] < 100:
            confidence += 0.1
        if text.isupper() and len(text.split()) > 1:
            confidence += 0.1
        if re.match(r"^\s*(\d+(\.\d+)*|[A-Z]\.?|[IVXLCDM]+\.)\s+.*", text, re.IGNORECASE):
            confidence += 0.15
        if re.search(r"^(chapter|section|appendix|introduction|conclusion|references)\s+.*", text, re.IGNORECASE):
            confidence += 0.15

        # Penalties for unlikely headings
        if len(text.split()) > 15 or len(text) < 3:
            confidence *= 0.5
        if font_size < 8:
            confidence *= 0.1

        # Title detection for page 1
        if document_title == "Untitled Document" and page_num == 1 and font_size >= max_font_size * 0.9:
            document_title = text
            confidence = 1.0

        if confidence > 0.65:
            potential_headings.append({
                "text": text,
                "font_size": font_size,
                "page": page_num,
                "is_bold": is_bold,
                "confidence": confidence
            })

    # Cluster font sizes for heading levels
    unique_font_sizes = sorted(set(h["font_size"] for h in potential_headings), reverse=True)
    font_size_clusters = []
    if unique_font_sizes:
        current_cluster = [unique_font_sizes[0]]
        for i in range(1, len(unique_font_sizes)):
            if abs(unique_font_sizes[i] - current_cluster[-1]) < 1.0:
                current_cluster.append(unique_font_sizes[i])
            else:
                font_size_clusters.append(current_cluster)
                current_cluster = [unique_font_sizes[i]]
        font_size_clusters.append(current_cluster)

    font_size_clusters.sort(key=lambda c: sum(c) / len(c), reverse=True)
    heading_level_ranges = {}
    for i, cluster in enumerate(font_size_clusters[:3]):
        level = f"H{i+1}"
        heading_level_ranges[level] = (min(cluster), max(cluster))

    # Assign heading levels and collect section content
    final_headings = []
    section_content = []
    current_section = None
    current_content = []
    for i, line in enumerate(merged_lines_data):
        text = line["text"].strip()
        font_size = line["font_size"]
        page_num = line["page_number"]
        assigned_level = None
        confidence = 0.0

        # Check if line is a heading
        for heading in potential_headings:
            if heading["text"] == text and heading["page"] == page_num:
                confidence = heading["confidence"]
                for level, (min_size, max_size) in heading_level_ranges.items():
                    if min_size <= font_size <= max_size:
                        assigned_level = level
                        break
                if not assigned_level and confidence > 0.3:
                    assigned_level = "H3"
                break

        if assigned_level:
            if current_section:
                section_content.append({
                    "document": os.path.basename(pdf_path),
                    "section_title": current_section["text"],
                    "page": current_section["page"],
                    "content": " ".join(current_content)
                })
                current_content = []
            final_headings.append({
                "level": assigned_level,
                "text": text,
                "page": page_num
            })
            current_section = {"text": text, "page": page_num}
        elif current_section:
            current_content.append(text)

    # Append the last section
    if current_section and current_content:
        section_content.append({
            "document": os.path.basename(pdf_path),
            "section_title": current_section["text"],
            "page": current_section["page"],
            "content": " ".join(current_content)
        })

    # Merge with TOC if available
    if toc_headings:
        final_headings.extend(toc_headings)
        seen = set()
        unique_headings = []
        for h in final_headings:
            key = (h["level"], h["text"], h["page"])
            if key not in seen:
                unique_headings.append(h)
                seen.add(key)
        final_headings = unique_headings

    # Sort headings by page and level
    final_headings.sort(key=lambda x: (x["page"],
                                      0 if x["level"] == "H1" else
                                      1 if x["level"] == "H2" else
                                      2 if x["level"] == "H3" else 3))

    document.close()
    logger.info(f"Processed {pdf_path} in {time.time() - start_time:.2f} seconds")
    return {"title": document_title, "outline": final_headings, "content": section_content}

def rank_sections(sections, keywords):
    """Rank sections and subsections by relevance to keywords."""
    ranked_sections = []
    subsection_analysis = []
    for section in sections:
        text = (section["section_title"] + " " + section["content"]).lower()
        score = 0
        for keyword in keywords:
            # Weight title matches higher
            if keyword in section["section_title"].lower():
                score += 3
            if keyword in section["content"].lower():
                score += 1
        ranked_sections.append({
            "document": section["document"],
            "page_number": section["page"],
            "section_title": section["section_title"],
            "importance_rank": score
        })

        # Extract key sentences for subsection analysis
        sentences = re.split(r'[.!?]\s+', section["content"])
        key_sentences = [
            s for s in sentences if any(keyword in s.lower() for keyword in keywords)
        ][:3]  # Limit to top 3 relevant sentences
        for sentence in key_sentences:
            subsection_analysis.append({
                "document": section["document"],
                "refined_text": sentence.strip(),
                "page_number": section["page"]
            })

    # Sort sections by importance rank
    ranked_sections.sort(key=lambda x: x["importance_rank"], reverse=True)
    # Assign ranks (1-based)
    for i, section in enumerate(ranked_sections, 1):
        section["importance_rank"] = i

    return ranked_sections, subsection_analysis

def main():
    """Process PDFs and generate ranked output based on persona and job-to-be-done."""
    input_dir = "input"
    output_dir = "output"
    config_file = "input/config.json"
    os.makedirs(output_dir, exist_ok=True)

    # Read persona and job-to-be-done from config
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        persona = config.get("persona", "")
        job_to_be_done = config.get("job_to_be_done", "")
    except Exception as e:
        logger.error(f"Failed to read config.json: {e}")
        return

    # Extract keywords
    keywords = extract_keywords(persona, job_to_be_done)
    logger.info(f"Extracted keywords: {keywords}")

    # Process all PDFs
    all_sections = []
    input_documents = []
    for filename in os.listdir(input_dir):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(input_dir, filename)
            input_documents.append(filename)
            logger.info(f"Processing {pdf_path}...")
            try:
                result = extract_headings_and_content(pdf_path)
                all_sections.extend(result["content"])
            except Exception as e:
                logger.error(f"Failed to process {pdf_path}: {e}")

    # Rank sections and subsections
    ranked_sections, subsection_analysis = rank_sections(all_sections, keywords)

    # Prepare output
    output = {
        "metadata": {
            "input_documents": input_documents,
            "persona": persona,
            "job_to_be_done": job_to_be_done,
            "processing_timestamp": datetime.utcnow().isoformat()
        },
        "extracted_sections": ranked_sections,
        "subsection_analysis": subsection_analysis
    }

    # Save output
    output_path = os.path.join(output_dir, "output.json")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        logger.info(f"Output saved to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save output: {e}")

if __name__ == "__main__":
    main()