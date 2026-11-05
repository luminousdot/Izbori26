"""Vercel entry point for /stanje ("Ko šta radi"), cached for 2 minutes like the Izbori page."""
import os, sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import stanje  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        items, failed = stanje.collect()
        body = stanje.render(items, failed).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "public, s-maxage=120, stale-while-revalidate=600")
        self.end_headers()
        self.wfile.write(body)
