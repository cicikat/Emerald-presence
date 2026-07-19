"""
Guard: reality-side loaders must not reference dream-domain paths.

Scanned set:
  core/memory/*.py  (all Python files)
  core/pipeline.py
  core/prompt_builder.py

Domain markers (any occurrence in non-comment source lines fails):
  "dreams/"           — data-directory path prefix
  "impression_loader" — loader module name
  "afterglow"         — dream artifact type
  "dream_summary"     — dream artifact type
  "dreams/archive"    — explicit archive path (belt-and-suspenders)

ALLOWLIST (file_rel_path, marker) — currently one entry:
  ("core/pipeline.py", "impression_loader")
    pipeline.py is the sole authorised consumer of impression_loader;
    it receives pre-loaded text for prompt injection and never writes dream data.

Positive sample:
  core/dream/impression_loader.py must contain "dreams/" in a non-comment line —
  proves the scan mechanism is live, not silently vacuous (anti-false-green).
"""

from pathlib import Path

_ROOT = Path(__file__).parent.parent

_MARKERS = [
    "dreams/",
    "impression_loader",
    "afterglow",
    "dream_summary",
    "dreams/archive",
]

# Only one permitted exception: pipeline.py importing impression_loader.
# Any additional reference in any other file → add here explicitly and document why.
#
# Phase 5 (2026-06-03): AfterglowResidueInput and integrate_afterglow() are
# the approved one-way Dream → Reality writeback path.  The three files below
# are the Reality-side integrator + schema + store — they legitimately contain
# "afterglow" by design.  Dream modules (core/dream/*.py) still hold no write
# authority; DREAM_DIRECT_WRITABLE remains frozenset().
_ALLOWLIST: set[tuple[str, str]] = {
    ("core/pipeline.py", "impression_loader"),
    ("core/memory/user_hidden_state.py", "afterglow"),
    ("core/memory/user_hidden_state_integrator.py", "afterglow"),
    ("core/memory/user_hidden_state_store.py", "afterglow"),
    # Phase 7: prompt_builder reads afterglow residue (read-only) to inject layer 6f.
    # No write path; _format_afterglow_soft_hint() is explicitly fail-closed.
    ("core/prompt_builder.py", "afterglow"),
    # path_resolver resolves afterglow_residue → user_memory_root() (reality path).
    # Approved: afterglow_residue is a reality-scoped artifact (P5 Dream→Reality writeback).
    ("core/memory/path_resolver.py", "afterglow"),
    # user_facts.py enumerates known reality-scoped artifact names including afterglow_residue.
    ("core/memory/user_facts.py", "afterglow"),
    # Brief 42 (coplay): core/coplay/afterglow.py is an unrelated, independent module —
    # a plain TTL text residue for "just finished playing a game", not the Dream→Reality
    # writeback machinery this guard otherwise protects. No dream data crosses here;
    # "afterglow" is reused only as a generic English word for the concept.
    ("core/pipeline.py", "afterglow"),
}


def _reality_files() -> list[Path]:
    memory_dir = _ROOT / "core" / "memory"
    return [
        *sorted(memory_dir.glob("*.py")),
        _ROOT / "core" / "pipeline.py",
        _ROOT / "core" / "prompt_builder.py",
    ]


def _rel(path: Path) -> str:
    return str(path.relative_to(_ROOT)).replace("\\", "/")


def _scan_violations(
    files: list[Path],
    markers: list[str],
    allowlist: set[tuple[str, str]],
) -> list[str]:
    violations: list[str] = []
    for fpath in files:
        if not fpath.exists():
            violations.append(f"MISSING FILE: {_rel(fpath)}")
            continue
        rel = _rel(fpath)
        for lineno, line in enumerate(fpath.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            for marker in markers:
                if marker in line and (rel, marker) not in allowlist:
                    violations.append(
                        f"{rel}:{lineno}: forbidden {marker!r}  →  {line.rstrip()}"
                    )
    return violations


def test_reality_loaders_do_not_reference_dream_paths() -> None:
    violations = _scan_violations(_reality_files(), _MARKERS, _ALLOWLIST)
    assert not violations, (
        f"{len(violations)} violation(s) — reality-side code must not reference dream paths:\n"
        + "\n".join(violations)
    )


def test_positive_sample_impression_loader_references_dream_path() -> None:
    """Confirms scan is non-vacuous: impression_loader.py contains 'dreams/'."""
    loader = _ROOT / "core" / "dream" / "impression_loader.py"
    assert loader.exists(), f"positive-sample file not found: {loader}"
    src = loader.read_text(encoding="utf-8")
    found = any(
        "dreams/" in line
        for line in src.splitlines()
        if not line.strip().startswith("#")
    )
    assert found, (
        "positive-sample check failed: core/dream/impression_loader.py has no 'dreams/' "
        "marker in non-comment lines — if the file moved, fix this test to match"
    )


# ── Brief 100 §4: reverse-direction scan for Dream Stage (group dream) ───────
#
# Mirror of the guard above, direction flipped: these are DREAM-side files and
# must never reference REALITY writeback entry points. "Zero reflow" (Brief
# 100 §0) is a design contract enforced by "not wired in", not by filtering —
# this test is the automated tripwire for that contract.

_GROUP_DREAM_FILES: list[Path] = [
    _ROOT / "core" / "stage" / "dream_runtime.py",
    _ROOT / "core" / "stage" / "dream_views.py",
]

_GROUP_DREAM_FORBIDDEN_MARKERS = [
    # Precise reality writeback entry points — not the bare word "projection",
    # which also appears in legitimate dream-domain vocabulary (body_projection /
    # project_body_for_yexuan, the her-body physics module used by group dreams
    # too) and would otherwise false-positive on every generation call site.
    "core.stage.projection",
    "enqueue_reality_projection",
    "summarize_to_midterm",
    "impression_loader",
    "afterglow",
    "hidden_state",
]


def test_dream_stage_runtime_does_not_reference_reality_writers() -> None:
    violations = _scan_violations(_GROUP_DREAM_FILES, _GROUP_DREAM_FORBIDDEN_MARKERS, allowlist=set())
    assert not violations, (
        f"{len(violations)} violation(s) — Dream Stage code must not reference "
        "reality memory writeback entry points (zero reflow, Brief 100 §0):\n"
        + "\n".join(violations)
    )


def test_positive_sample_reality_stage_runtime_references_projection() -> None:
    """Confirms the reverse scan is non-vacuous: reality's core/stage/runtime.py
    genuinely enqueues a reality projection — proving the scan mechanism would
    actually catch a Dream Stage file that accidentally grew the same import."""
    runtime = _ROOT / "core" / "stage" / "runtime.py"
    assert runtime.exists(), f"positive-sample file not found: {runtime}"
    src = runtime.read_text(encoding="utf-8")
    found = any(
        "projection" in line
        for line in src.splitlines()
        if not line.strip().startswith("#")
    )
    assert found, (
        "positive-sample check failed: core/stage/runtime.py has no 'projection' "
        "marker in non-comment lines — if it moved, fix this test to match"
    )
