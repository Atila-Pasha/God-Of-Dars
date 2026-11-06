import zlib
from datetime import UTC, datetime

from app.bot.leaderboard_widget import (
    global_rank_widget_html,
    leaderboard_widget_html,
    validate_widget_size,
)
from app.services.leaderboard_service import FighterPage, LeaderboardEntry


def test_widget_escapes_names_and_fits_telegram_limits() -> None:
    entries = tuple(
        LeaderboardEntry(rank, rank, '<script>"نام" & دوست', None, 1000 - rank, 20)
        for rank in range(1, 11)
    )
    html = leaderboard_widget_html("student", entries, entries[6], "weekly")

    assert '<script>"نام"' not in html
    assert "&lt;script&gt;" in html
    assert "جایگاه تو" in html
    assert "صحیح" in html
    validate_widget_size(html)
    assert len(zlib.compress(html.encode("utf-8"), 9)) <= 4096


def test_global_widget_shows_page_and_viewer_tier() -> None:
    entry = LeaderboardEntry(11, 7, "آرمان", "arman", 1801, 3)
    page = FighterPage(
        entries=(entry,),
        page=2,
        pages=3,
        total=23,
        updated_at=datetime(2026, 11, 6, 10, 0, tzinfo=UTC),
    )
    html = global_rank_widget_html(page, entry)

    assert "صفحه 2/3" in html
    assert "دیاموندی" in html
    assert "@arman" in html
    assert "data:image/webp;base64," in html
    assert 'class="tier t5"' in html
    assert "آخرین به‌روزرسانی: 2026/11/06، 13:30" in html
    validate_widget_size(html)
