# ADR-0001 — Module Structure

- 일자: 2026-05-07
- 상태: 채택
- 컨텍스트: Phase 0 스캐폴드

## 결정

다음 단일 책임 모듈 구조를 채택한다. 외부 의존은 `_clients/`로 격리하고, 도메인 로직은 client-free 순수 함수로 둔다.

```
src/youtube_market_brief/
├── __init__.py, __main__.py
├── cli.py                  # argparse entrypoint
├── orchestrator.py         # 파이프라인 조립 + 실패 격리 + RunReport
├── config.py               # AppConfig (env + yaml)
├── logging_setup.py
├── domain/
│   ├── types.py            # frozen dataclass: VideoMeta, Transcript, ...
│   ├── slugify.py          # channel_slug, video_slug
│   ├── watchlist.py        # WatchlistMatcher
│   ├── markdown.py         # frontmatter + body 직렬화
│   ├── daily_brief.py      # ticker_rollup 합성
│   └── telegram_format.py  # 4096B 분할
├── pipeline/
│   ├── discover.py         # channels → list[VideoMeta]
│   ├── transcribe.py       # VideoMeta → Transcript | TranscriptSkip
│   ├── analyze.py          # Transcript → VideoAnalysis (claude CLI)
│   ├── write_video.py      # VideoAnalysis → MD path
│   ├── aggregate.py        # list[VideoAnalysis] → DailyBrief + MD
│   └── notify.py           # → Telegram
├── state/store.py          # JSON IdempotencyStore (atomic write)
└── _clients/
    ├── youtube_data.py     # Protocol + impl (googleapiclient)
    ├── transcript.py       # Protocol + impl (youtube-transcript-api)
    ├── llm.py              # Protocol + impl (claude CLI subprocess)
    └── telegram.py         # Protocol + impl (Bot API)
```

## 원칙

1. **Protocol 인터페이스**: `_clients/*`는 모두 `typing.Protocol` 노출. 구현 클래스는 동일 파일.
2. **DI**: `pipeline/*`은 client를 인자로 받음. 전역 싱글턴 금지.
3. **Pure domain**: `domain/*`은 client-free, deterministic. snapshot 테스트 가능.
4. **External prompt files**: `prompts/*.md`는 코드 외부. prompt cache 단위(파일 경계) 명시.

## 대안

- **Flat 구조** (`src/*.py` 전부 평면): 단순하지만 책임 모호. 9+ 모듈에서 가독성 저하. 기각.
- **Layered** (controllers/services/repositories): Java/Spring 스타일. Python 도메인 어플리케이션에 과함. 기각.
- **하이브리드 (현 결정)**: `domain/` (pure) + `pipeline/` (orchestration) + `_clients/` (external) + `state/` (persistence). 책임 경계 명확. 채택.

## 결과

- 모듈별 단위테스트와 통합테스트 분리 명료
- 외부 의존 모킹 용이 (Protocol → in-memory fake)
- Codex가 모듈별로 독립적으로 작업 가능
