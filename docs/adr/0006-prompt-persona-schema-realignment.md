# ADR-0006: Prompt persona 4-role composite + output schema realignment

- 상태: Accepted
- 날짜: 2026-05-11
- Supersedes: 없음 (ADR-0001~0005와 직교)

## 배경

ymb 출력 schema(`key_insights: list[str]`, `red_team: list[str]`)와 다운스트림 `02_Areas/Market_Insights/{sectors,themes}/*.md` 카드의 frontmatter schema(`type, stance, confidence, related_tickers, related_cards`)가 misaligned되어 매일 41/49 raws의 *수동 propagation*이 work item이 됨 (commit history 인용). ymb는 funnel 상단을 자동화했으나 *카드 통합*이라는 가장 큰 work가 사용자 손에 남아 있음.

또 단일 "한국 회계감사인을 위한 시장 분석가" 페르소나는 사용자 실제 직무 vantage(인차지/감사인/AX Node 매니저/K-IFRS·재무·전략·GTM)의 부분집합이라 분석이 *single-vantage*적이 됨.

## 결정

1. **페르소나 4-role composite**: "감사인이자 재무 정보 전문가이자 투자자이자 시장 분석가인 1인의 분석가"로 재정의. 각 시각의 focus를 명시(red flag/cash flow quality/risk-reward/narrative). 4 시각 합성된 단일 출력 schema 유지 (role 분리 출력 안 함).

2. **key_insights / red_team schema 변경**: `string` → object `{text: str, sector_tags: list[str], theme_tags: list[str]}`. propagation 결정론 확보.

3. **ticker `sector_tag` 추가**: watchlist hit ticker는 `WatchlistEntry.sector` 후처리로 채움(watchlist 우선). 자동 발견 ticker는 LLM 출력.

4. **stance/confidence/time_horizon 자동 출력 거절**: 카드 owner(사용자) 판단 영역. propagation은 *변화 이벤트 row 추가*까지만 자동, stance 결정은 인간.

5. **enum noun**: `domain/taxonomy.py`에 `SECTOR_SLUGS`, `THEME_SLUGS` tuple 정의. prompts에 인라인 노출, `ymb config validate`에 vault MD slug와 drift 비교.

6. **JSON sidecar**: 영상 MD와 daily brief MD 옆에 `.analysis.json`(영상 단위) / `{date}_brief.analysis.json`(일일 단위) 작성. P2 propagation 자동화의 source of truth.

7. **Migration non-retroactive**: 기존 vault MD는 그대로. 적용 시점부터 새 schema. old MD는 사용자 이미 41/49 통합 중이라 그대로 정합.

## 대안

- A. 페르소나는 유지하고 schema만: 사용자 vantage 손실. 거절.
- B. 4-role을 *별도 섹션*으로 출력(audit_view, financial_view ...): schema bloat + token 비용 ↑. 거절.
- C. stance/confidence/time_horizon까지 LLM 출력: 카드 owner 권한 침범 + LLM trust 부담 ↑. 거절.

## 결과

- Schema 변경으로 영향: types/analyze/markdown/telegram_format/daily_brief/aggregate (6 파일).
- Migration 부담: 기존 vault MD 35+건 그대로 둠. 재처리 비용 0.
- 후속: P2 propagation 자동화는 `.analysis.json` sidecar 파싱으로 deterministic.

## 추후 고려

- P2 후 sidecar parser가 안정되면 sidecar를 *유일한* propagation source로 굳히고 frontmatter union은 deprecated 가능.
- old MD retroactive 재처리 스크립트(`ymb reprocess --since YYYY-MM-DD`)는 P2 진입 후 필요 시 추가.
