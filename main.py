import os
import json
from datetime import datetime
from pdf_processor import load_pdf, get_document_title, extract_text_blocks, close_document
from heading_detector import merge_lines, compute_heading_confidence, assign_heading_levels
from output_handler import save_outline_to_json
from semantic_analyzer import extract_keywords, extract_sections_and_subsections
from sentence_transformers import SentenceTransformer


def process_pdf(pdf_path, output_dir, job_description, model):
    """Process a single PDF to extract and rank sections/subsections."""
    document = load_pdf(pdf_path)
    title = get_document_title(document)
    text_blocks = extract_text_blocks(document)
    merged_lines = merge_lines(text_blocks)
    potential_headings, updated_title = compute_heading_confidence(merged_lines, title)
    final_headings = assign_heading_levels(potential_headings)

    # Add line_y0 for section extraction
    for heading, line in zip(final_headings, merged_lines):
        if heading["text"] == line["text"] and heading["page"] == line["page_number"]:
            heading["line_y0"] = line["line_y0"]

    sections, subsections = extract_sections_and_subsections(pdf_path, final_headings, document, job_description, model)
    close_document(document)

    # Save Round 1A output for reference
    output_json_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".json"
    save_outline_to_json(updated_title, final_headings, os.path.join(output_dir, output_json_filename))

    return os.path.basename(pdf_path), sections, subsections


def main():
    """Process all PDFs in the input directory and generate Round 1B output."""
    input_dir = "/app/input"
    output_dir = "/app/output"
    os.makedirs(output_dir, exist_ok=True)

    # Load persona and job-to-be-done from config.json
    config_path = os.path.join(input_dir, "config.json")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    persona = config["persona"]
    job = config["job_to_be_done"]

    # Load lightweight model
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Process all PDFs
    output = {
        "metadata": {
            "input_documents": [],
            "persona": persona,
            "job_to_be_done": job,
            "processing_timestamp": datetime.utcnow().isoformat() + "Z"
        },
        "extracted_sections": [],
        "sub_section_analysis": []
    }

    for filename in os.listdir(input_dir):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(input_dir, filename)
            print(f"Processing {pdf_path}...")
            doc_name, sections, subsections = process_pdf(pdf_path, output_dir, job, model)
            output["metadata"]["input_documents"].append(doc_name)
            output["extracted_sections"].extend(sections)
            output["sub_section_analysis"].extend(subsections)

    # Save Round 1B output
    output_path = os.path.join(output_dir, "output.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    print(f"Round 1B output saved to: {output_path}")


if __name__ == "__main__":
    main()