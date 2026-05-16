"""Bridge yMB daily sidecars into PAS entity propagation proposals."""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PropagationResult:
    ok: bool
    skipped: bool = False
    proposal_path: str | None = None
    message: str = ""


RunCmd = Callable[..., subprocess.CompletedProcess[str]]


def create_daily_propagation_proposal(
    *,
    sidecar_path: Path,
    vault_root: Path,
    run_cmd: RunCmd = subprocess.run,
) -> PropagationResult:
    """Create a proposal from a daily `.analysis.json` sidecar.

    This is intentionally proposal-only. The PAS helper writes review artifacts
    under Harness/sessions/entity_propagation and never mutates Market_Insights.
    """
    helper = (
        vault_root
        / "01_Projects"
        / "00_personal_agent_system"
        / "scripts"
        / "entity_propagation_lite.py"
    )
    if not helper.exists():
        message = f"helper missing: {helper}"
        log.warning("daily propagation skipped: %s", message)
        return PropagationResult(ok=False, skipped=True, message=message)
    if not sidecar_path.exists():
        message = f"sidecar missing: {sidecar_path}"
        log.warning("daily propagation skipped: %s", message)
        return PropagationResult(ok=False, skipped=True, message=message)

    cmd = [
        sys.executable,
        str(helper),
        "--source",
        str(sidecar_path),
        "--target-scope",
        str(vault_root / "02_Areas" / "Market_Insights"),
        "--mode",
        "propose",
    ]
    proc = run_cmd(
        cmd,
        cwd=vault_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()
        log.error("daily propagation proposal failed: %s", message)
        return PropagationResult(ok=False, message=message)

    proposal_path = _last_nonempty_line(proc.stdout)
    log.info("daily propagation proposal written: %s", proposal_path)
    return PropagationResult(ok=True, proposal_path=proposal_path, message="created")


def _last_nonempty_line(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return None
