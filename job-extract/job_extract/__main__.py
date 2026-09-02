"""python -m job_extract <url-or-file>   (needs GOOGLE_API_KEY for the real run)"""
from __future__ import annotations

import sys
from pathlib import Path

from .llm import GeminiLLM
from .pipeline import from_html, from_url


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m job_extract <url | path-to-html>", file=sys.stderr)
        return 2

    target = args[0]
    llm = GeminiLLM()
    if target.startswith(("http://", "https://")):
        job = from_url(target, llm)
    else:
        job = from_html(Path(target).read_text(encoding="utf-8"), llm)

    print(job.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
