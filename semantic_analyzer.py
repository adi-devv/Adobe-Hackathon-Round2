from sentence_transformers import SentenceTransformer
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import nltk
import re

# Download required NLTK data during Docker build
nltk.download('punkt', quiet=True)

def extract_keywords(job_description, top_n=10):
    """Extract top keywords from the job description using TF-IDF."""
    words = nltk.word_tokenize(job_description.lower())
    words = [w for w in words if w.isalnum() and len(w) > 2]
    freq = nltk.FreqDist(words)
    total = sum(freq.values())
    tf_scores = {word: count / total for word, count in freq.items()}
    return sorted(tf_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

def compute_relevance(text, job_description, model):
    """Compute relevance score of text to job description using embeddings."""
    embeddings = model.encode([text, job_description])
    return cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]

def summarize_text(text, sentences_count=2):
    """Summarize text to a specified number of sentences using LSA."""
    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LsaSummarizer()
    summary = summarizer(parser.document, sentences_count)
    return " ".join([str(sentence) for sentence in summary])

def extract_sections_and_subsections(pdf_path, outline, document, job_description, model):
    """Extract and rank sections and subsections based on relevance."""
    sections = []
    subsections = []
    
    for i, heading in enumerate(outline):
        # Extract section text
        page = document[heading["page"] - 1]
        next_page = document[outline[i + 1]["page"] - 1] if i + 1 < len(outline) else None
        text = ""
        if next_page and outline[i + 1]["page"] == heading["page"]:
            rect = [0, heading["line_y0"], page.rect.width, outline[i + 1]["line_y0"]]
        else:
            rect = [0, heading["line_y0"], page.rect.width, page.rect.height]
        text = page.get_text("text", clip=rect).strip()
        
        # Compute relevance
        relevance_score = compute_relevance(text, job_description, model)
        
        # Add section
        sections.append({
            "document": pdf_path,
            "page_number": heading["page"],
            "section_title": heading["text"],
            "importance_rank": 0,  # To be updated after sorting
            "relevance_score": relevance_score
        })
        
        # Extract subsections (split by paragraphs or subheadings)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for j, para in enumerate(paragraphs):
            if len(para.split()) > 10:  # Ignore very short paragraphs
                relevance_score = compute_relevance(para, job_description, model)
                refined_text = summarize_text(para, sentences_count=1)
                subsections.append({
                    "document": pdf_path,
                    "page_number": heading["page"],
                    "refined_text": refined_text,
                    "importance_rank": 0,  # To be updated after sorting
                    "relevance_score": relevance_score
                })
    
    # Rank sections and subsections
    sections.sort(key=lambda x: x["relevance_score"], reverse=True)
    for i, section in enumerate(sections, 1):
        section["importance_rank"] = i
    
    subsections.sort(key=lambda x: x["relevance_score"], reverse=True)
    for i, subsection in enumerate(subsections, 1):
        subsection["importance_rank"] = i
    
    return sections, subsections