"""Small text helpers shared by providers and the verification engine."""

import re

STOPWORDS = {
    "the", "a", "an", "is", "it", "that", "this", "for", "ones", "one",
    "size", "same", "are", "was", "were", "runs", "at", "on", "in", "of",
    "to", "and", "or", "but", "we", "you", "they", "there", "here",
    "just", "only", "also", "per", "each", "with", "from", "by", "be",
    "those", "these",
    "been", "has", "have", "had", "do", "does", "did", "can", "could",
    "will", "would", "if", "so", "as", "any", "all", "our", "your",
    "their", "its", "them", "us", "me", "my",
    # generic commerce nouns that never identify a product
    "fee", "price", "cost", "charge", "rate", "kind", "type", "brand",
    "model", "item", "product", "thing", "option", "version",
}


def norm(s) -> str:
    return " ".join(str(s).lower().split())


def split_sentences(text: str) -> list[str]:
    """Split a transcript into sentences, line by line."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if part:
                out.append(part)
    return out


def seller_sentences(transcript: str) -> list[str]:
    """Sentences spoken by the seller. The seller is the source of truth:
    the agent's questions are context, never evidence."""
    return [sentence for sentence, _ in seller_units(transcript)]


# A transcript line may carry a timestamp prefix: "[00:12] Seller: ...".
TIMESTAMPED_LINE_RX = re.compile(r"^\[(\d{1,2}:\d{2})\]\s*([A-Za-z]+):\s*(.*)$")
SPEAKER_LINE_RX = re.compile(r"^(Seller|Agent):\s*(.*)$")


def seller_units(transcript: str) -> list[tuple[str, str]]:
    """(sentence, evidence) pairs for everything the seller said.

    The evidence for a sentence is the sentence itself, except in
    timestamped transcripts (the campaign format), where the evidence
    is the full line: the span then carries its speaker and timestamp
    with it, which is the proof the campaign annotations record.
    """
    out = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        evidence_line = None
        m = TIMESTAMPED_LINE_RX.match(line)
        if m:
            if m.group(2) != "Seller":
                continue
            spoken = m.group(3)
            evidence_line = line
        else:
            m = SPEAKER_LINE_RX.match(line)
            if m:
                if m.group(1) != "Seller":
                    continue
                spoken = m.group(2)
            else:
                spoken = line
        for part in re.split(r"(?<=[.!?])\s+", spoken):
            part = part.strip()
            if part:
                out.append((part, evidence_line or part))
    return out


def proof_for_span(span, transcript: str):
    """(speaker, timestamp) for an evidence span, or (None, None).

    Looks at the span itself first (a full timestamped line), then at
    the transcript line that contains it.
    """
    if not span:
        return None, None
    m = TIMESTAMPED_LINE_RX.match(span.strip())
    if m:
        return m.group(2), m.group(1)
    target = norm(span)
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        m = TIMESTAMPED_LINE_RX.match(line)
        if m and target and target in norm(line):
            return m.group(2), m.group(1)
    return None, None


def stem(token: str) -> str:
    """Crude singular stem: emergencies -> emergency, tyres -> tyre."""
    t = token.lower()
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def content_tokens(text: str) -> list[str]:
    """Meaningful tokens of a sentence: no stopwords, no bare numbers."""
    tokens = []
    for raw in re.findall(r"[a-z0-9][a-z0-9\-']*", str(text).lower()):
        if raw in STOPWORDS or raw.replace("-", "").isdigit():
            continue
        tokens.append(raw)
    return tokens


def span_in_transcript(span, transcript: str) -> bool:
    return bool(span) and norm(span) in norm(transcript)
