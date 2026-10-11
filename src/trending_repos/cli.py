"""Command-line interface for listing trending GitHub repositories.

GitHub has no official "trending" endpoint, so trending is approximated with
the Search API: repositories created within the selected time window, sorted
by star count.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from . import __version__

API_URL = "https://api.github.com/search/repositories"
DURATIONS = {"day": 1, "week": 7, "month": 30, "year": 365}
DEFAULT_DURATION = "week"
DEFAULT_LIMIT = 10
MAX_LIMIT = 100  # GitHub's maximum page size for search results
TIMEOUT_SECONDS = 15


class GitHubAPIError(Exception):
    """Raised when the GitHub API request fails or returns unusable data."""


def positive_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be an integer, got {value!r}")
    if not 1 <= limit <= MAX_LIMIT:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_LIMIT}, got {limit}")
    return limit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trending-repos",
        description="Show the most-starred GitHub repositories created in a recent time range.",
    )
    parser.add_argument(
        "--duration",
        type=str.lower,
        choices=list(DURATIONS),
        default=DEFAULT_DURATION,
        help=f"time range to look back over (default: {DEFAULT_DURATION})",
    )
    parser.add_argument(
        "--limit",
        type=positive_limit,
        default=DEFAULT_LIMIT,
        help=f"number of repositories to show, 1-{MAX_LIMIT} (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def since_date(duration: str, today: date | None = None) -> date:
    today = today or datetime.now(timezone.utc).date()
    return today - timedelta(days=DURATIONS[duration])


def build_url(since: date, limit: int) -> str:
    params = {
        "q": f"created:>={since.isoformat()}",
        "sort": "stars",
        "order": "desc",
        "per_page": str(limit),
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def _http_error_message(err: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(err.read().decode("utf-8")).get("message", "")
    except (ValueError, AttributeError, OSError):
        detail = ""

    remaining = err.headers.get("X-RateLimit-Remaining") if err.headers else None
    if err.code in (403, 429) and (remaining == "0" or "rate limit" in detail.lower()):
        reset = err.headers.get("X-RateLimit-Reset")
        when = ""
        if reset and reset.isdigit():
            reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            when = f" Try again after {reset_at:%H:%M:%S} UTC."
        return (
            "GitHub API rate limit exceeded." + when
            + " Set the GITHUB_TOKEN environment variable to raise the limit."
        )
    if err.code == 401:
        return "GitHub rejected the credentials in GITHUB_TOKEN (401 Unauthorized)."
    if err.code == 422:
        return f"GitHub rejected the search query (422): {detail or 'validation failed'}"
    if err.code >= 500:
        return f"GitHub API is having problems ({err.code}). Please try again later."
    return f"GitHub API request failed ({err.code} {err.reason}){': ' + detail if detail else ''}"


def fetch_repositories(url: str, token: str | None = None) -> list[dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"trending-repos/{__version__}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        raise GitHubAPIError(_http_error_message(err)) from err
    except (TimeoutError, socket.timeout) as err:
        raise GitHubAPIError(f"Request to GitHub timed out after {TIMEOUT_SECONDS}s.") from err
    except urllib.error.URLError as err:
        raise GitHubAPIError(f"Could not reach GitHub: {err.reason}") from err

    try:
        data = json.loads(body)
    except ValueError as err:
        raise GitHubAPIError("GitHub returned a response that is not valid JSON.") from err

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise GitHubAPIError("Unexpected response from GitHub: missing 'items' list.")
    return items


def parse_repositories(items: list[dict]) -> list[dict]:
    repos = []
    for item in items:
        if not isinstance(item, dict):
            continue
        repos.append(
            {
                "name": item.get("full_name") or item.get("name") or "<unknown>",
                "description": (item.get("description") or "").strip() or "No description provided.",
                "stars": int(item.get("stargazers_count") or 0),
                "language": item.get("language") or "Unknown",
                "url": item.get("html_url") or "",
            }
        )
    repos.sort(key=lambda repo: repo["stars"], reverse=True)
    return repos


def format_repositories(repos: list[dict], duration: str, since: date) -> str:
    header = f"Top {len(repos)} trending repositories of the past {duration} (created since {since.isoformat()})"
    lines = [header, "=" * len(header)]
    if not repos:
        lines.append("No repositories found for this time range.")
        return "\n".join(lines)

    width = len(str(len(repos)))
    indent = " " * (width + 2)
    for rank, repo in enumerate(repos, start=1):
        lines.append("")
        lines.append(f"{rank:>{width}}. {repo['name']}")
        lines.append(f"{indent}Stars: {repo['stars']:,}  |  Language: {repo['language']}")
        lines.extend(
            textwrap.wrap(repo["description"], width=88, initial_indent=indent, subsequent_indent=indent)
        )
        if repo["url"]:
            lines.append(f"{indent}{repo['url']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # Descriptions often contain emoji; don't crash on consoles that can't encode them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = build_parser().parse_args(argv)
    since = since_date(args.duration)
    url = build_url(since, args.limit)

    try:
        items = fetch_repositories(url, token=os.environ.get("GITHUB_TOKEN"))
    except GitHubAPIError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    repos = parse_repositories(items)[: args.limit]
    print(format_repositories(repos, args.duration, since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
