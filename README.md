# trending-repos

A small command-line tool that shows trending GitHub repositories for a time range
(day, week, month or year), sorted by star count.

```
$ trending-repos --duration month --limit 3
Top 3 trending repositories of the past month (created since 2026-09-11)
========================================================================

1. owner/some-project
   Stars: 12,345  |  Language: Python
   A short description of the project, wrapped to fit the terminal.
   https://github.com/owner/some-project
...
```

## How "trending" is determined

GitHub's REST API has no official trending endpoint. This tool uses the
[Search Repositories API](https://docs.github.com/en/rest/search/search#search-repositories)
to find repositories **created** within the selected window and ranks them by
star count, which surfaces the projects that gained the most attention in that period.

| `--duration` | Window searched |
|--------------|-----------------|
| `day`        | last 1 day      |
| `week`       | last 7 days     |
| `month`      | last 30 days    |
| `year`       | last 365 days   |

## Requirements

- Python 3.9 or newer
- No third-party dependencies (standard library only)

## Installation

From the project directory:

```bash
pip install .
```

This puts a `trending-repos` command on your `PATH`. For an isolated install you
can use [pipx](https://pipx.pypa.io/): `pipx install .`

To run it without installing:

```bash
# macOS / Linux
PYTHONPATH=src python -m trending_repos --duration day

# Windows PowerShell
$env:PYTHONPATH = "src"; python -m trending_repos --duration day
```

## Usage

```
trending-repos [--duration {day,week,month,year}] [--limit N]
```

| Option       | Description                                          | Default |
|--------------|------------------------------------------------------|---------|
| `--duration` | Time range: `day`, `week`, `month` or `year`         | `week`  |
| `--limit`    | Number of repositories to show (1-100)               | `10`    |
| `--version`  | Print the version and exit                           |         |
| `-h, --help` | Show help and exit                                   |         |

Examples:

```bash
trending-repos                              # top 10 of the past week
trending-repos --duration day               # top 10 of the past day
trending-repos --duration month --limit 20  # top 20 of the past month
trending-repos --duration year --limit 50   # top 50 of the past year
```

Each result shows the repository name, star count, primary language,
description and URL.

## Authentication (optional)

No authentication is needed. Unauthenticated requests to the Search API are
limited by GitHub to about 10 per minute. If you hit that limit, set a
[personal access token](https://github.com/settings/tokens) (no scopes needed)
in the `GITHUB_TOKEN` environment variable and the tool will use it:

```bash
export GITHUB_TOKEN=ghp_yourtoken          # macOS / Linux
$env:GITHUB_TOKEN = "ghp_yourtoken"        # Windows PowerShell
```

## Errors and exit codes

| Exit code | Meaning                                                             |
|-----------|---------------------------------------------------------------------|
| `0`       | Success                                                             |
| `1`       | API or network error (rate limit, timeout, GitHub outage, bad JSON) |
| `2`       | Invalid command-line input (e.g. `--duration decade`, `--limit 0`)  |

Error messages are printed to stderr, for example:

```
Error: GitHub API rate limit exceeded. Try again after 14:05:12 UTC. Set the GITHUB_TOKEN environment variable to raise the limit.
```

## Running the tests

```bash
# macOS / Linux
PYTHONPATH=src python -m unittest discover -s tests -v

# Windows PowerShell
$env:PYTHONPATH = "src"; python -m unittest discover -s tests -v
```

The tests mock all network calls, so they run offline.
