import re
from collections import defaultdict

def merge_lines(all_lines_data):
    """Merge consecutive lines that belong to the same heading based on proximity and style."""
    if not all_lines_data:
        return []
    
    all_lines_data.sort(key=lambda x: (x["page_number"], x["line_y0"]))
    merged_lines_data = []
    current_merged_line = dict(all_lines_data[0])
    
    for next_line in all_lines_data[1:]:
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
            current_merged_line["line_y1"] = next_line["line_y1"]
        else:
            merged_lines_data.append(current_merged_line)
            current_merged_line = dict(next_line)
    
    merged_lines_data.append(current_merged_line)
    return merged_lines_data

def compute_heading_confidence(lines_data, document_title):
    """Compute confidence scores for potential headings based on font, spacing, and text patterns."""
    potential_headings = []
    all_font_sizes = [line["font_size"] for line in lines_data if line["font_size"] > 0]
    min_global_font_size = min(all_font_sizes) if all_font_sizes else 0
    max_global_font_size = max(all_font_sizes) if all_font_sizes else 0
    page_font_sizes = defaultdict(list)
    for line in lines_data:
        if line["font_size"] > 0:
            page_font_sizes[line["page_number"]].append(line["font_size"])
    
    for i, line in enumerate(lines_data):
        heading_confidence = 0.0
        font_size = line["font_size"]
        is_bold = line["is_bold"]
        page_num = line["page_number"]
        text = line["text"].strip()
        
        # Font size contribution
        if font_size > 0 and max_global_font_size > min_global_font_size:
            font_size_normalized = (font_size - min_global_font_size) / (max_global_font_size - min_global_font_size)
            heading_confidence += font_size_normalized * 0.35
        elif font_size >= 11:
            heading_confidence += 0.15
        
        if page_font_sizes[page_num]:
            max_page_font_size = max(page_font_sizes[page_num])
            if font_size >= max_page_font_size * 0.9:
                heading_confidence += 0.15
            elif font_size >= max_page_font_size * 0.7:
                heading_confidence += 0.05
        
        # Bold contribution
        if is_bold:
            heading_confidence += 0.3
        
        # Spacing contribution
        line_height = line["line_y1"] - line["line_y0"]
        space_to_next_line = 0
        next_is_body_text = False
        if i + 1 < len(lines_data) and lines_data[i+1]["page_number"] == page_num:
            next_line = lines_data[i+1]
            space_to_next_line = next_line["line_y0"] - line["line_y1"]
            if (not next_line["is_bold"] and
                next_line["font_size"] < font_size * 0.9 and
                next_line["font_size"] >= min_global_font_size * 0.9 and
                len(next_line["text"].split()) > 4 and
                space_to_next_line >= 3):
                next_is_body_text = True
                heading_confidence += 0.4
        
        if space_to_next_line > (line_height * 2.0):
            heading_confidence += 0.35
        elif space_to_next_line > (line_height * 1.5):
            heading_confidence += 0.2
        elif space_to_next_line > (line_height * 1.0):
            heading_confidence += 0.1
        
        if i > 0 and lines_data[i-1]["page_number"] == page_num:
            space_from_previous_line = line["line_y0"] - lines_data[i-1]["line_y1"]
            if space_from_previous_line > (line_height * 1.5):
                heading_confidence += 0.1
            elif space_from_previous_line > (line_height * 1.0):
                heading_confidence += 0.05
        
        # Positioning contribution
        if line["line_x0"] < 100:
            heading_confidence += 0.1
        
        # Text pattern contribution
        if text.isupper() and len(text.split()) > 1 and len(text) > 3:
            heading_confidence += 0.1
        if re.match(r"^\s*(\d+(\.\d+)*|[A-Z]\.?|[IVXLCDM]+\.)\s+.*", text, re.IGNORECASE):
            heading_confidence += 0.15
        if re.search(r"^(chapter|section|appendix|introduction|conclusion|references)\s+\d*(\.\d*)*", text, re.IGNORECASE):
            heading_confidence += 0.15
        
        # Penalties
        if len(text.split()) > 15:
            heading_confidence *= 0.7
        if len(text.strip()) < 3:
            heading_confidence *= 0.5
        if font_size < 8:
            heading_confidence *= 0.1
        if document_title == "Untitled Document" and page_num == 1 and font_size >= (max_global_font_size * 0.8) and heading_confidence > 0.4:
            document_title = text
            heading_confidence = 1.0
        if re.fullmatch(r"[\.\-_—\s]+", text):
            heading_confidence *= 0.05
        if sum(c.isalnum() for c in text) < 5 and len(text) > 10:
            heading_confidence *= 0.1
        
        if heading_confidence > 0.70:
            potential_headings.append({
                "text": text,
                "font_size": font_size,
                "page": page_num,
                "is_bold": is_bold,
                "x0": line["bbox"][0],
                "line_height": line_height,
                "space_after": space_to_next_line,
                "heading_confidence": heading_confidence
            })
    
    return potential_headings, document_title

def assign_heading_levels(potential_headings):
    """Assign heading levels (H1, H2, H3) based on font size clusters."""
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
        heading_level_font_ranges["H1"] = (min(font_size_clusters[0]), max(font_size_clusters[0]))
    if len(font_size_clusters) >= 2:
        heading_level_font_ranges["H2"] = (min(font_size_clusters[1]), max(font_size_clusters[1]))
    if len(font_size_clusters) >= 3:
        heading_level_font_ranges["H3"] = (min(font_size_clusters[2]), max(font_size_clusters[2]))
    
    final_headings = []
    for heading in potential_headings:
        font_size = heading["font_size"]
        assigned_level = None
        if "H1" in heading_level_font_ranges and heading_level_font_ranges["H1"][0] <= font_size <= heading_level_font_ranges["H1"][1]:
            assigned_level = "H1"
        elif "H2" in heading_level_font_ranges and heading_level_font_ranges["H2"][0] <= font_size <= heading_level_font_ranges["H2"][1]:
            assigned_level = "H2"
        elif "H3" in heading_level_font_ranges and heading_level_font_ranges["H3"][0] <= font_size <= heading_level_font_ranges["H3"][1]:
            assigned_level = "H3"
        else:
            if heading["heading_confidence"] > 0.30:
                if "H1" in heading_level_font_ranges and font_size > heading_level_font_ranges["H1"][0] * 0.8:
                    assigned_level = "H1"
                elif "H2" in heading_level_font_ranges and font_size > heading_level_font_ranges["H2"][0] * 0.8:
                    assigned_level = "H2"
                elif "H3" in heading_level_font_ranges and font_size > heading_level_font_ranges["H3"][0] * 0.8:
                    assigned_level = "H3"
                else:
                    assigned_level = "H3"  # Default to H3 for lower-confidence headings
        
        if assigned_level:
            final_headings.append({
                "level": assigned_level,
                "text": heading["text"],
                "page": heading["page"],
                "heading_confidence": heading["heading_confidence"]
            })
    
    final_headings.sort(key=lambda x: (x["page"], 
                                      0 if x["level"] == "H1" else 
                                      1 if x["level"] == "H2" else 
                                      2 if x["level"] == "H3" else 3, 
                                      x["text"]))
    
    unique_final_headings = []
    seen_keys = set()
    for heading in final_headings:
        key = (heading["level"], heading["text"], heading["page"])
        if key not in seen_keys:
            unique_final_headings.append(heading)
            seen_keys.add(key)
    
    return unique_final_headings