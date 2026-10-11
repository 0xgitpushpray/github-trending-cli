import io
import json
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from email.message import Message
from unittest import mock

from trending_repos import cli


def fake_response(payload):
    response = mock.MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__.return_value = response
    return response


def http_error(code, message="", headers=None):
    msg = Message()
    for key, value in (headers or {}).items():
        msg[key] = value
    body = io.BytesIO(json.dumps({"message": message}).encode("utf-8"))
    return urllib.error.HTTPError(cli.API_URL, code, "Error", msg, body)


SAMPLE_ITEMS = [
    {"full_name": "a/low", "description": "Low", "stargazers_count": 5, "language": "Go", "html_url": "https://github.com/a/low"},
    {"full_name": "b/high", "description": None, "stargazers_count": 900, "language": None, "html_url": "https://github.com/b/high"},
    {"full_name": "c/mid", "description": "Mid", "stargazers_count": 1200, "language": "Rust", "html_url": "https://github.com/c/mid"},
]


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class ArgumentTests(unittest.TestCase):
    def test_defaults(self):
        args = cli.build_parser().parse_args([])
        self.assertEqual(args.duration, "week")
        self.assertEqual(args.limit, 10)

    def test_duration_is_case_insensitive(self):
        self.assertEqual(cli.build_parser().parse_args(["--duration", "MONTH"]).duration, "month")

    def test_invalid_duration_rejected(self):
        code, _, err = run(["--duration", "decade"])
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)

    def test_invalid_limits_rejected(self):
        for bad in ("0", "-3", "101", "ten"):
            with self.subTest(limit=bad):
                code, _, err = run(["--limit", bad])
                self.assertEqual(code, 2)
                self.assertIn("--limit", err)


class QueryTests(unittest.TestCase):
    def test_since_date(self):
        today = date(2026, 10, 11)
        self.assertEqual(cli.since_date("day", today), date(2026, 10, 10))
        self.assertEqual(cli.since_date("week", today), date(2026, 10, 4))
        self.assertEqual(cli.since_date("month", today), date(2026, 9, 11))
        self.assertEqual(cli.since_date("year", today), date(2025, 10, 11))

    def test_build_url(self):
        url = cli.build_url(date(2026, 10, 4), 20)
        self.assertIn("q=created%3A%3E%3D2026-10-04", url)
        self.assertIn("sort=stars", url)
        self.assertIn("order=desc", url)
        self.assertIn("per_page=20", url)


class ParseAndFormatTests(unittest.TestCase):
    def test_sorted_by_stars_with_fallbacks(self):
        repos = cli.parse_repositories(SAMPLE_ITEMS)
        self.assertEqual([r["name"] for r in repos], ["c/mid", "b/high", "a/low"])
        self.assertEqual(repos[1]["description"], "No description provided.")
        self.assertEqual(repos[1]["language"], "Unknown")

    def test_format_output(self):
        text = cli.format_repositories(cli.parse_repositories(SAMPLE_ITEMS), "week", date(2026, 10, 4))
        self.assertIn("Top 3 trending repositories of the past week", text)
        self.assertIn("1. c/mid", text)
        self.assertIn("Stars: 1,200  |  Language: Rust", text)

    def test_format_empty(self):
        text = cli.format_repositories([], "day", date(2026, 10, 10))
        self.assertIn("No repositories found", text)


class FetchTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_success_end_to_end(self, urlopen):
        urlopen.return_value = fake_response({"items": SAMPLE_ITEMS})
        code, out, err = run(["--duration", "month", "--limit", "2"])
        self.assertEqual(code, 0, err)
        self.assertIn("1. c/mid", out)
        self.assertIn("2. b/high", out)
        self.assertNotIn("a/low", out)

    @mock.patch.dict("os.environ", {"GITHUB_TOKEN": "secret"})
    @mock.patch("urllib.request.urlopen")
    def test_token_sent_when_set(self, urlopen):
        urlopen.return_value = fake_response({"items": []})
        run([])
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")

    def assert_error(self, side_effect, expected):
        with mock.patch("urllib.request.urlopen", side_effect=side_effect):
            code, out, err = run([])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn(expected, err)

    def test_rate_limit(self):
        err = http_error(403, "API rate limit exceeded", {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1760000000"})
        self.assert_error(err, "rate limit exceeded")

    def test_server_error(self):
        self.assert_error(http_error(503), "having problems (503)")

    def test_validation_error(self):
        self.assert_error(http_error(422, "Validation Failed"), "Validation Failed")

    def test_network_error(self):
        self.assert_error(urllib.error.URLError("Name or service not known"), "Could not reach GitHub")

    def test_timeout(self):
        self.assert_error(TimeoutError(), "timed out")

    @mock.patch("urllib.request.urlopen")
    def test_invalid_json(self, urlopen):
        response = fake_response(None)
        response.read.return_value = b"<html>oops</html>"
        urlopen.return_value = response
        code, _, err = run([])
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", err)

    @mock.patch("urllib.request.urlopen")
    def test_missing_items(self, urlopen):
        urlopen.return_value = fake_response({"message": "weird"})
        code, _, err = run([])
        self.assertEqual(code, 1)
        self.assertIn("missing 'items'", err)


if __name__ == "__main__":
    unittest.main()
