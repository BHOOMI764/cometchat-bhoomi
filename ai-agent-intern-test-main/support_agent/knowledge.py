from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


STOP_WORDS = {
    "a", "about", "after", "all", "also", "am", "an", "and", "any", "are", "as", "at", "be",
    "because", "been", "before", "being", "between", "by", "can", "could", "do", "does",
    "doing", "during", "for", "from", "have", "having", "how", "if", "in", "into", "is", "it",
    "its", "just", "me", "my", "not", "of", "on", "or", "our", "out", "over", "should", "so",
    "some", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "us", "very", "was",
    "we", "were", "what", "when", "where", "which", "who", "why", "will", "with", "would",
    "you", "your"
}


@dataclass
class KnowledgeChunk:
    file_name: str
    title: str
    heading: str
    content: str
    metadata: dict
    section_path: str
    score: float = 0.0


def _parse_front_matter(text: str):
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            block = text[4:end]
            data = {}
            for line in block.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    data[key.strip()] = value.strip()
            return data, text[end + 5 :]
    return {}, text


def _tokenize(text: str):
    return [token for token in re.findall(r"[a-zA-Z0-9]+", text.lower()) if token not in STOP_WORDS]


def load_knowledge_base(base_dir: Path):
    chunks = []
    for path in sorted(base_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_front_matter(text)
        lines = body.splitlines()
        title = metadata.get("title") or path.stem
        current_heading = title
        current_lines = []
        for line in lines:
            heading_match = re.match(r"^(#+)\s+(.*)$", line)
            if heading_match:
                if current_lines:
                    section = " / ".join([part for part in [title, current_heading] if part])
                    chunk = KnowledgeChunk(
                        file_name=path.name,
                        title=title,
                        heading=current_heading,
                        content="\n".join(current_lines).strip(),
                        metadata=metadata,
                        section_path=section,
                    )
                    chunks.append(chunk)
                current_heading = heading_match.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            section = " / ".join([part for part in [title, current_heading] if part])
            chunk = KnowledgeChunk(
                file_name=path.name,
                title=title,
                heading=current_heading,
                content="\n".join(current_lines).strip(),
                metadata=metadata,
                section_path=section,
            )
            chunks.append(chunk)
    return chunks


def _score_chunk(query: str, chunk: KnowledgeChunk):
    q_tokens = set(_tokenize(query))
    primary = " ".join([chunk.title, chunk.heading, chunk.content]).lower()
    score = 0.0
    for token in q_tokens:
        if token in primary:
            score += 2.0
    if any(token in primary for token in q_tokens):
        score += 1.0
    if chunk.metadata.get("status") == "active":
        score += 4.0
    if chunk.metadata.get("policy_authority") == "official":
        score += 5.0
    if chunk.metadata.get("status") == "superseded":
        score -= 8.0
    if chunk.metadata.get("customer_answering") is False:
        score -= 20.0
    if chunk.metadata.get("policy_authority") == "none":
        score -= 15.0
    if any(word in query.lower() for word in ["return", "refund", "cancel"]):
        if "returns" in chunk.title.lower() or "return" in chunk.heading.lower():
            score += 4.0
    if any(word in query.lower() for word in ["ship", "shipping", "canada", "international", "germany"]):
        if "shipping" in chunk.title.lower() or "shipping" in chunk.heading.lower():
            score += 4.0
    return score


def retrieve_relevant_chunks(query: str, chunks: Iterable[KnowledgeChunk], limit: int = 4):
    ranked = []
    for chunk in chunks:
        score = _score_chunk(query, chunk)
        if score <= 0:
            continue
        chunk.score = score
        ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    results = []
    seen_files = set()
    for _, chunk in ranked[:limit]:
        if chunk.file_name not in seen_files:
            results.append(chunk)
            seen_files.add(chunk.file_name)
        if len(results) >= limit:
            break
    return results
