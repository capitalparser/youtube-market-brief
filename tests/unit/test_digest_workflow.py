from pathlib import Path


def test_digest_workflow_does_not_swallow_daily_run_failures():
    workflow = Path(".github/workflows/digest.yml").read_text(encoding="utf-8")

    assert 'uv run ymb run --date "$TARGET" --no-brief || true' not in workflow
    assert 'uv run ymb run --date "$TARGET" --no-brief' in workflow
    assert '--include "${TARGET}__*.analysis.json"' in workflow
