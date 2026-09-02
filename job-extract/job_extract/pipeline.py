"""Fetch + strip to text, then hand off to :func:`extract`."""
from __future__ import annotations

import httpx
from selectolax.parser import HTMLParser

from .extract import extract
from .llm import LLM
from .models import JobPosting

_UA = "job-extract-sample/1.0"
_DROP = ("script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside")


def clean_text(html: str) -> str:
    """HTML -> readable plain text. Pure; no network."""
    tree = HTMLParser(html)
    for sel in _DROP:
        for node in tree.css(sel):
            node.decompose()
    body = tree.body or tree.root
    text = body.text(separator="\n") if body else ""
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    blanks = 0
    for ln in lines:
        if ln:
            out.append(ln)
            blanks = 0
        else:
            blanks += 1
            if blanks <= 1:
                out.append("")
    return "\n".join(out).strip()


def from_html(html: str, llm: LLM, *, max_retries: int = 2) -> JobPosting:
    return extract(clean_text(html), llm, max_retries=max_retries)


def from_url(url: str, llm: LLM, *, timeout: float = 20.0, max_retries: int = 2) -> JobPosting:
    resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return from_html(resp.text, llm, max_retries=max_retries)
