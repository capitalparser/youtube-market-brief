from pathlib import Path
from subprocess import CompletedProcess

from youtube_market_brief.pipeline.propagation import create_daily_propagation_proposal


def test_create_daily_propagation_proposal_runs_pas_helper(tmp_path):
    vault_root = tmp_path / "vault"
    script = vault_root / "01_Projects" / "00_personal_agent_system" / "scripts" / "entity_propagation_lite.py"
    script.parent.mkdir(parents=True)
    script.write_text("# helper", encoding="utf-8")
    sidecar = vault_root / "00_Wiki" / "youtube" / "_daily" / "2026-05-16_brief.analysis.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("{}", encoding="utf-8")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return CompletedProcess(cmd, 0, stdout="noise\nHarness/sessions/entity_propagation/2026-05-16/x.proposal.md\n", stderr="")

    result = create_daily_propagation_proposal(
        sidecar_path=sidecar,
        vault_root=vault_root,
        run_cmd=fake_run,
    )

    assert result.ok is True
    assert result.proposal_path == "Harness/sessions/entity_propagation/2026-05-16/x.proposal.md"
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd[1] == str(script)
    assert cmd[2:4] == ["--source", str(sidecar)]
    assert "--mode" in cmd
    assert kwargs["cwd"] == vault_root
    assert kwargs["capture_output"] is True


def test_create_daily_propagation_proposal_skips_when_pas_helper_missing(tmp_path):
    sidecar = tmp_path / "vault" / "00_Wiki" / "youtube" / "_daily" / "2026-05-16_brief.analysis.json"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text("{}", encoding="utf-8")

    def fail_if_called(cmd, **kwargs):
        raise AssertionError("run_cmd should not be called")

    result = create_daily_propagation_proposal(
        sidecar_path=sidecar,
        vault_root=tmp_path / "vault",
        run_cmd=fail_if_called,
    )

    assert result.ok is False
    assert result.skipped is True
    assert "helper missing" in result.message
