"""Preview sample leaderboard widgets at http://127.0.0.1:8765/."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.bot.leaderboard_widget import global_rank_widget_html, leaderboard_widget_html
from app.services.leaderboard_service import FighterPage, LeaderboardEntry

_SAMPLE_UPDATED_AT = datetime.now(UTC)


def sample_html(mode: str) -> str:
    names = (
        ("آرمان", "arman"),
        ("مهسا", "mahsa"),
        ("کیان", "kian"),
        ("نیکا", None),
        ("پارسا", None),
        ("سارا", "sara"),
        ("آوا", None),
        ("پویا", "pouya"),
        ("درسا", None),
        ("نیما", "nima"),
    )
    entries = tuple(
        LeaderboardEntry(rank, rank, name, username, 2010 - rank * 93, 20 - rank)
        for rank, (name, username) in enumerate(names, 1)
    )
    if mode == "global":
        return global_rank_widget_html(
            FighterPage(entries, 1, 3, 27, _SAMPLE_UPDATED_AT), entries[6]
        )
    if mode == "student":
        return leaderboard_widget_html(
            "student", entries, entries[6], "weekly", _SAMPLE_UPDATED_AT
        )
    return leaderboard_widget_html(
        "commander", entries, entries[6], "weekly", _SAMPLE_UPDATED_AT
    )


class PreviewHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        mode = self.path.strip("/")
        if mode not in {"commander", "student", "global"}:
            mode = "commander"
        widget = sample_html(mode)
        widget_attribute = escape(widget, quote=True)
        page = f"""<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8">
<title>پیش‌نمایش لیدربرد</title>
<style>body{{background:#101827;color:#e9f0ff;font:15px system-ui;margin:30px auto;max-width:800px;padding:0 16px}}
a{{color:#80baff;margin:0 8px}}iframe{{display:block;width:390px;max-width:100%;height:600px;border:0;margin:22px 0;border-radius:22px}}
small{{color:#9dadc6}}</style>
<h1>پیش‌نمایش ویجت لیدربرد</h1>
<nav><a href="/commander">فرمانده</a><a href="/student">دانش‌آموز</a><a href="/global">رنک سراسری</a></nav>
<iframe title="Telegram widget" srcdoc="{widget_attribute}"></iframe>
<small>این صفحه ظاهر HTML را نشان می‌دهد؛ اجرای واقعی داخل تلگرام به Bot API 10.4 beta و کلاینت پشتیبان ویجت نیاز دارد.</small>
</html>"""
        content = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == "__main__":
    print("Leaderboard preview: http://127.0.0.1:8765/")
    HTTPServer(("127.0.0.1", 8765), PreviewHandler).serve_forever()
