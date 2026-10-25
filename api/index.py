"""Vercel entry point: builds the Izbori page on each request (cached for 2 minutes)."""
import os, sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import izbori  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = parse_qs(urlparse(self.path).query, keep_blank_values=True)
        items, failed = izbori.collect("all" in q)
        body = izbori.render(items, failed, "all" in q).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # Vercel's CDN serves the same page for 2 minutes, so the outlets see few requests.
        self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(body)
