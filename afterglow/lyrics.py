"""Bounded lyric parsers. Estimated timing is never labeled word-synced."""

from bisect import bisect_right
from dataclasses import dataclass
import math
import re
import xml.etree.ElementTree as ET

MAX_TEXT = 2 * 1024 * 1024
STAMP = r'(\d{1,3}):(\d{2}(?:\.\d+)?)'


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Line:
    text: str
    start: float
    end: float
    words: tuple[Word, ...] = ()


@dataclass(frozen=True)
class LyricDocument:
    lines: tuple[Line, ...] = ()
    quality: str = 'missing'
    source: str = ''


def check_text(text):
    if len(text.encode('utf-8')) > MAX_TEXT or text.count('\n') > 20000:
        raise ValueError('Lyrics file is too large')


def seconds(minutes, rest):
    return int(minutes) * 60 + float(rest)


def estimated_words(text, start, end):
    tokens = text.split()
    total = sum(max(1, len(t)) for t in tokens)
    cursor = start
    result = []
    for token in tokens:
        stop = cursor + (end - start) * max(1, len(token)) / total
        result.append(Word(token, cursor, stop))
        cursor = stop
    return tuple(result)


def parse_lrc(text: str, duration: float = 0) -> LyricDocument:
    check_text(text)
    offset_match = re.search(r'\[offset:([+-]?\d+)\]', text, re.I)
    offset = int(offset_match[1]) / 1000 if offset_match else 0
    entries = {}
    for raw in text.splitlines():
        stamps = list(re.finditer(r'\[' + STAMP + r'\]', raw))
        if not stamps:
            continue
        body = raw[stamps[-1].end():].strip()
        if not re.sub(r'<' + STAMP + r'>', '', body).strip():
            continue
        for stamp in stamps:
            start = max(0, seconds(*stamp.groups()) + offset)
            entries.setdefault(start, body)
            if len(entries) > 20000:
                raise ValueError('Too many lyric lines')
    if not entries:
        plain = '\n'.join(l for l in text.splitlines() if not re.fullmatch(r'\[[a-z]+:.*\]', l.strip(), re.I)).strip()
        return LyricDocument((Line(plain, 0, 0),), 'unsynced', 'LRC') if plain else LyricDocument()
    starts = sorted(entries)
    lines, exact = [], []
    for i, start in enumerate(starts):
        # shortcut: line timestamps lack vocal ends; cap inferred phrases at 7s until word data is available.
        end = min(starts[i + 1] if i + 1 < len(starts) else (duration if duration > start else start + 5), start + 7)
        body = entries[start]
        tags = list(re.finditer(r'<' + STAMP + r'>', body))
        words = []
        for j, tag in enumerate(tags):
            token = body[tag.end():tags[j + 1].start() if j + 1 < len(tags) else len(body)].strip()
            a = max(start, seconds(*tag.groups()) + offset)
            b = seconds(*tags[j + 1].groups()) + offset if j + 1 < len(tags) else end
            if token and b > a:
                words.append(Word(token, a, min(b, end)))
        clean = re.sub(r'<' + STAMP + r'>', '', body).strip()
        exact.append(bool(words))
        if words:
            end = min(end, words[-1].end)
        lines.append(Line(clean, start, end, tuple(words) if words else estimated_words(clean, start, end)))
    return LyricDocument(tuple(lines), 'word' if all(exact) else 'estimated', 'LRC')


def xml_time(value):
    try:
        if value.endswith('ms'):
            result = float(value[:-2]) / 1000
        elif value.endswith('s'):
            result = float(value[:-1])
        else:
            parts = value.split(':')
            result = sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))
        if not math.isfinite(result) or result < 0:
            raise ValueError
        return result
    except (ValueError, AttributeError):
        raise ValueError('Invalid lyric timestamp') from None


def parse_ttml(text: str) -> LyricDocument:
    check_text(text)
    if re.search(r'<!\s*(DOCTYPE|ENTITY)', text, re.I):
        raise ValueError('XML declarations are not allowed')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError('Malformed TTML') from error
    lines, precise = [], True
    for p in root.iter():
        if p.tag.rsplit('}', 1)[-1] != 'p' or 'begin' not in p.attrib:
            continue
        start, end = xml_time(p.get('begin')), xml_time(p.get('end'))
        if end <= start:
            continue
        words, pending = [], None
        for span in p:
            if 'begin' not in span.attrib or 'end' not in span.attrib:
                continue
            token = ''.join(span.itertext())
            a, b = max(start, xml_time(span.get('begin'))), min(end, xml_time(span.get('end')))
            if b <= a or not token.strip():
                continue
            if pending and not pending[3] and not token.startswith(' '):
                pending = (pending[0] + token, pending[1], b, bool((span.tail or '').strip() == '' and span.tail))
            else:
                if pending:
                    words.append(Word(pending[0].strip(), pending[1], pending[2]))
                pending = (token, a, b, bool(span.tail and span.tail.isspace()))
        if pending:
            words.append(Word(pending[0].strip(), pending[1], pending[2]))
        content = ''.join(p.itertext()).strip()
        if content:
            precise = precise and bool(words)
            lines.append(Line(content, start, end, tuple(words) if words else estimated_words(content, start, end)))
        if len(lines) > 20000:
            raise ValueError('Too many lyric lines')
    lines.sort(key=lambda l: l.start)
    return LyricDocument(tuple(lines), ('word' if precise else 'estimated') if lines else 'missing', 'AMLL TTML')


def locate(document: LyricDocument, position: float) -> tuple[int, int, float]:
    if document.quality in ('missing', 'instrumental', 'unsynced') or not document.lines:
        return -1, -1, 0
    i = bisect_right(document.lines, position, key=lambda line: line.start) - 1
    if i < 0 or position >= document.lines[i].end:
        return -1, -1, 0
    for j, word in enumerate(document.lines[i].words):
        if word.start <= position < word.end:
            return i, j, (position - word.start) / max(.001, word.end - word.start)
    return i, -1, 0
