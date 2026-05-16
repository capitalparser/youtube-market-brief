import json
from datetime import date

from youtube_market_brief.pipeline.daily_inputs import load_video_analyses_for_date


def test_load_video_analyses_for_date_uses_video_sidecars(tmp_path):
    channel = tmp_path / "channel"
    channel.mkdir()
    sidecar = channel / "2026-05-11__video.analysis.json"
    sidecar.write_text(
        json.dumps(
            {
                "video": {
                    "video_id": "v1",
                    "channel_id": "UC1",
                    "channel_name": "Channel",
                    "channel_slug": "channel",
                    "title": "Video",
                    "url": "https://youtu.be/v1",
                    "published_at_utc": "2026-05-11T00:00:00+00:00",
                },
                "generated_at": "2026-05-11T01:00:00+00:00",
                "headline_3line": ["a", "b", "c"],
                "key_insights": [
                    {"text": "Insight", "sector_tags": ["semiconductors"], "theme_tags": []}
                ],
                "red_team": [
                    {"text": "Risk", "sector_tags": [], "theme_tags": ["ai_meltup_bubble"]}
                ],
                "tickers": [
                    {
                        "symbol": "NVDA",
                        "display": "NVIDIA",
                        "in_watchlist": True,
                        "sector_tag": "semiconductors",
                        "direction": "긍정적",
                        "reasoning": "AI capex",
                        "quotes": ["quote"],
                        "confidence": "high",
                    }
                ],
                "watchlist_hits": ["NVDA"],
                "tier": "deep",
                "tags": ["youtube", "NVDA"],
                "transcript_meta": {"chars_used": 100, "was_truncated": False},
                "llm_meta": {"model": "gpt-4.1", "duration_ms": 10, "was_retry": False},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    analyses = load_video_analyses_for_date(
        vault_youtube_root=tmp_path,
        target_date=date(2026, 5, 11),
    )

    assert len(analyses) == 1
    assert analyses[0].video.video_id == "v1"
    assert analyses[0].tickers[0].sector_tag == "semiconductors"
