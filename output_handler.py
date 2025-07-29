import json
import os

def save_outline_to_json(title, outline, output_path):
    """Save the extracted title and outline to a JSON file."""
    output_data = {
        "title": title,
        "outline": [{"level": h["level"], "text": h["text"], "page": h["page"]} for h in outline]
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=4, ensure_ascii=False)