"""Sync a GitHub user's public repositories to a local JSON file.

A work sample for the most common API-integration job: talk to a paginated,
rate-limited, token-authenticated REST API and land the data locally, without
losing rows to a 500 or a rate-limit window.
"""
from .models import Repo
from .client import GitHubClient, GitHubError, RateLimited

__all__ = ["Repo", "GitHubClient", "GitHubError", "RateLimited"]
