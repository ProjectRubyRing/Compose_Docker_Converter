"""sample-shop の API サーバー (標準ライブラリのみ)。

GET /        … 設定と、db / cache へ届くかどうかを JSON で返す
GET /healthz … ヘルスチェック用 (常に 200 ok)
"""

import configparser
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer


def tcp_ok(host, port, payload=None):
    try:
        with socket.create_connection((host, int(port)), timeout=2) as conn:
            if payload:
                conn.sendall(payload)
                return conn.recv(64).decode("ascii", "replace").strip()
            return "ok"
    except OSError as exc:
        return "error: %s" % exc


def read_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self._send(200, {"status": "ok"})
            return
        settings = configparser.ConfigParser()
        settings.read(os.environ.get("SETTINGS_FILE", "/etc/shop/settings.ini"))
        self._send(200, {
            "shop": os.environ.get("SHOP_NAME"),
            "version": os.environ.get("APP_VERSION"),
            "greeting": os.environ.get("GREETING"),
            "currency": settings.get("shop", "currency", fallback=None),
            "db": tcp_ok(os.environ.get("DB_HOST", "db"), os.environ.get("DB_PORT", "5432")),
            "cache": tcp_ok(os.environ.get("CACHE_HOST", "cache"), 6379, b"PING\r\n"),
            "warm": read_text("/var/cache/shop/warm.txt"),
            "started_at": read_text("/tmp/started-at"),
        })

    def log_message(self, fmt, *args):
        if os.environ.get("LOG_LEVEL") == "debug":
            super().log_message(fmt, *args)


if __name__ == "__main__":
    print("sample-shop app %s listening on :8000" % os.environ.get("APP_VERSION"), flush=True)
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
