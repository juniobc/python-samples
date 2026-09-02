"""Land the repos in a local JSON file, and report what changed.

``merge_snapshots`` is pure: given the previous list and the freshly fetched
list, it works out added / removed / updated without touching the disk or the
network, so the interesting part is unit-tested. ``run`` is the only I/O.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .client import GitHubClient
from .models import Repo


@dataclass
class Diff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.updated)


def merge_snapshots(old: list[Repo], new: list[Repo]) -> tuple[list[Repo], Diff]:
    """Newest wins. Diff keys on repo id; 'updated' compares ``pushed_at``."""
    old_by_id = {r.id: r for r in old}
    new_by_id = {r.id: r for r in new}

    diff = Diff()
    for rid, repo in new_by_id.items():
        if rid not in old_by_id:
            diff.added.append(repo.full_name)
        elif repo.pushed_at != old_by_id[rid].pushed_at:
            diff.updated.append(repo.full_name)
    for rid, repo in old_by_id.items():
        if rid not in new_by_id:
            diff.removed.append(repo.full_name)

    merged = sorted(new_by_id.values(), key=lambda r: (r.pushed_at is None, r.pushed_at), reverse=True)
    return merged, diff


def _load(path: Path) -> list[Repo]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Repo.model_validate(item) for item in data]


def _dump(path: Path, repos: list[Repo]) -> None:
    path.write_text(
        json.dumps([r.model_dump(mode="json") for r in repos], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run(username: str, out: Path, *, token: str | None = None) -> Diff:
    previous = _load(out)
    with GitHubClient(token=token) as gh:
        fresh = gh.list_user_repos(username)
    merged, diff = merge_snapshots(previous, fresh)
    _dump(out, merged)
    return diff


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sync a GitHub user's public repos to a JSON file.")
    ap.add_argument("username")
    ap.add_argument("-o", "--out", type=Path, default=Path("repos.json"))
    ap.add_argument("--token", default=None, help="GitHub token (or set GITHUB_TOKEN)")
    args = ap.parse_args(argv)

    import os

    token = args.token or os.environ.get("GITHUB_TOKEN")
    diff = run(args.username, args.out, token=token)

    if not diff.changed:
        print(f"{args.out}: up to date")
    else:
        for name in diff.added:
            print(f"  + {name}")
        for name in diff.updated:
            print(f"  ~ {name}")
        for name in diff.removed:
            print(f"  - {name}")
        print(f"{args.out}: +{len(diff.added)} ~{len(diff.updated)} -{len(diff.removed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
