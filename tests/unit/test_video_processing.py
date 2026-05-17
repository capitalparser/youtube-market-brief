import json
from datetime import UTC, datetime

from tests.fakes.fake_llm import FakeLLMClient
from tests.fakes.fake_telegram import FakeTelegramClient
from tests.fakes.fake_transcript import FakeTranscriptClient
from youtube_market_brief.domain.types import Segment, Transcript, VideoMeta, Watchlist
from youtube_market_brief.pipeline.video_processing import process_video
from youtube_market_brief.state.store import IdempotencyStore


def test_process_video_writes_md_notifies_and_marks_state(tmp_path):
    video = VideoMeta(
        video_id="v1",
        channel_id="UC1",
        channel_name="Channel",
        channel_slug="channel",
        title="Video",
        published_at_utc=datetime(2026, 5, 11, tzinfo=UTC),
        url="https://youtu.be/v1",
    )
    transcript = Transcript(
        video_id="v1",
        language="en",
        is_auto_generated=True,
        segments=(Segment(start=0, duration=1, text="hello"),),
        full_text="hello",
        char_count=5,
        fetched_at=datetime(2026, 5, 11, tzinfo=UTC),
    )
    llm = FakeLLMClient(
        responder=lambda _system, _user: "```json\n"
        + json.dumps(
            {
                "headline_3line": ["a", "b", "c"],
                "key_insights": [
                    {"text": "i1", "sector_tags": [], "theme_tags": []},
                    {"text": "i2", "sector_tags": [], "theme_tags": []},
                    {"text": "i3", "sector_tags": [], "theme_tags": []},
                ],
                "red_team": [
                    {"text": "r1", "sector_tags": [], "theme_tags": []},
                    {"text": "r2", "sector_tags": [], "theme_tags": []},
                ],
                "tickers": [],
                "watchlist_hits": [],
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    prompt = tmp_path / "system.md"
    prompt.write_text("system", encoding="utf-8")
    store = IdempotencyStore(tmp_path / "state.json")

    result = process_video(
        video=video,
        transcript_client=FakeTranscriptClient({"v1": transcript}),
        watchlist=Watchlist(),
        llm=llm,
        telegram=FakeTelegramClient(),
        store=store,
        vault_root=tmp_path,
        vault_youtube_root=tmp_path / "00_Wiki" / "youtube",
        system_prompt_path=prompt,
        captured_at=datetime(2026, 5, 11, tzinfo=UTC),
        date_kst_iso="2026-05-11",
        transcript_max_chars=80_000,
        timeout_sec=30,
        notify=True,
    )

    assert result.analysis is not None
    assert result.md_relative is not None
    assert store.is_done("v1")
    assert (tmp_path / result.md_relative).exists()
