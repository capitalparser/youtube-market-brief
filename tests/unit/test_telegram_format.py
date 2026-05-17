from datetime import UTC, date, datetime

from youtube_market_brief.domain.telegram_format import (
    SOFT_CAP,
    decorate_chunks,
    format_daily_brief,
    format_per_video,
    split_message,
)
from youtube_market_brief.domain.types import (
    DailyBrief,
    KeyInsight,
    LLMMeta,
    RedTeamItem,
    TickerMention,
    TranscriptSummary,
    VideoAnalysis,
    VideoMeta,
)


def test_split_short_message_returns_one():
    assert split_message("hello") == ["hello"]


def test_split_long_message_breaks_at_paragraphs():
    long = ("문장 " * 300 + "\n\n") * 5
    chunks = split_message(long)
    assert len(chunks) >= 2
    assert all(len(c) <= SOFT_CAP + 32 for c in chunks)


def test_split_appends_pagination_suffix():
    long = ("문장 " * 300 + "\n\n") * 5
    chunks = split_message(long)
    if len(chunks) > 1:
        assert "(1/" in chunks[0]
        assert f"({len(chunks)}/{len(chunks)})" in chunks[-1]


def test_split_extreme_single_long_line():
    long = "x" * (SOFT_CAP * 2 + 100)
    chunks = split_message(long)
    assert len(chunks) >= 2


def test_decorate_wraps_first_nonempty_line_in_blockquote_bold():
    out = decorate_chunks(["📺 채널 — 제목\n본문 첫 줄\n본문 둘째 줄"])
    assert out == ["<blockquote><b>📺 채널 — 제목</b></blockquote>\n본문 첫 줄\n본문 둘째 줄"]


def test_decorate_skips_leading_blank_lines():
    out = decorate_chunks(["\n\n📅 첫 줄\n뒤"])
    assert out[0].startswith("\n\n<blockquote><b>📅 첫 줄</b></blockquote>")


def test_decorate_applies_to_every_chunk():
    chunks = ["첫 메시지 헤더\n내용", "둘째 메시지 헤더\n내용\n\n(2/2)"]
    out = decorate_chunks(chunks)
    assert out[0].startswith("<blockquote><b>첫 메시지 헤더</b></blockquote>")
    assert out[1].startswith("<blockquote><b>둘째 메시지 헤더</b></blockquote>")
    # Pagination suffix stays outside the decoration.
    assert out[1].endswith("(2/2)")


def test_decorate_empty_chunk_is_unchanged():
    assert decorate_chunks([""]) == [""]


def _llm_meta() -> LLMMeta:
    return LLMMeta(model="claude-test", duration_ms=0)


def test_format_per_video_escapes_html_special_chars():
    video = VideoMeta(
        video_id="abc",
        channel_id="cid",
        channel_name="A & B <Channel>",
        channel_slug="ab",
        title="제목 <script>",
        published_at_utc=datetime(2026, 5, 1, tzinfo=UTC),
        url="https://example.com/?a=1&b=2",
    )
    summary = TranscriptSummary(
        headline_3line=("h1", "h2", "h3"),
        key_insights=(KeyInsight(text="위험 < 기회"),),
        red_team=(RedTeamItem(text="Tom & Jerry"),),
        chars_used=0,
        was_truncated=False,
    )
    ticker = TickerMention(
        symbol="000660",
        display="SK <하이닉스>",
        in_watchlist=True,
        sector_tag=None,
        direction="긍정적",
        reasoning="capex & demand",
        quotes=(),
        confidence="high",
    )
    analysis = VideoAnalysis(
        video=video,
        transcript_summary=summary,
        tickers=(ticker,),
        watchlist_hits=("000660",),
        tier="deep",
        tags=(),
        llm_meta=_llm_meta(),
        generated_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    out = format_per_video(analysis, vault_md_path_relative="path/with&amp.md")
    # Raw `<`, `>`, `&` in dynamic content must be escaped.
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert "A &amp; B &lt;Channel&gt;" in out
    assert "?a=1&amp;b=2" in out
    assert "위험 &lt; 기회" in out
    assert "Tom &amp; Jerry" in out
    assert "SK &lt;하이닉스&gt;" in out
    assert "capex &amp; demand" in out


def test_format_daily_brief_escapes_html_special_chars():
    brief = DailyBrief(
        date=date(2026, 5, 1),
        market_read="risk < reward & momentum",
        key_insights=(KeyInsight(text="a < b"),),
        red_team=(RedTeamItem(text="c & d"),),
        ticker_rollup=(),
        videos=(),
        llm_meta=_llm_meta(),
    )
    out = format_daily_brief(brief)
    # format_* emits no HTML tags; tags are added only by decorate_chunks.
    assert "<" not in out
    assert "risk &lt; reward &amp; momentum" in out
    assert "a &lt; b" in out
    assert "c &amp; d" in out


def test_format_per_video_extracts_text_from_key_insight_objects():
    """Telegram message renders KeyInsight.text only — sector_tags not exposed to user."""
    video = VideoMeta(
        video_id="vid1",
        channel_id="cid",
        channel_name="테스트채널",
        channel_slug="test",
        title="테스트 영상",
        published_at_utc=datetime(2026, 5, 1, tzinfo=UTC),
        url="https://example.com/v=1",
    )
    summary = TranscriptSummary(
        headline_3line=("h1", "h2", "h3"),
        key_insights=(
            KeyInsight(text="반도체 수요 회복", sector_tags=("semiconductors",), theme_tags=()),
        ),
        red_team=(
            RedTeamItem(text="공급 과잉 우려", sector_tags=("semiconductors",), theme_tags=()),
        ),
        chars_used=0,
        was_truncated=False,
    )
    analysis = VideoAnalysis(
        video=video,
        transcript_summary=summary,
        tickers=(),
        watchlist_hits=(),
        tier="light",
        tags=(),
        llm_meta=_llm_meta(),
        generated_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    out = format_per_video(analysis, vault_md_path_relative="some/path.md")
    # KeyInsight.text is rendered.
    assert "반도체 수요 회복" in out
    assert "공급 과잉 우려" in out
    # sector_tags are NOT exposed in the Telegram message.
    assert "semiconductors" not in out
