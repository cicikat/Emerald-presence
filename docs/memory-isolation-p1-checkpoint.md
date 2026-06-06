# Memory Isolation P1 Freeze Checkpoint

> **Audience**: next-window coding agent or reviewer picking up multi-character memory isolation work.
> **Status date**: 2026-06-06
> **Keyword for search**: `P1 freeze checkpoint`

---

## 1. Current State Overview

All P0–P1 isolation work is **complete and passing** (1707 collected tests, all green at time of freeze).

| Phase | Scope | Status |
|-------|-------|--------|
| **P0** | Pipeline + slow_queue char_id透传; mood/impression/dream/hidden_state/afterglow isolation | ✅ Done |
| **P1-0** | Small bypass patches (tool reply reader, probe reader, short_term, post_process, episodic_sweep, admin/users, garden, hidden_state_decay, runtime yexuan fallback audit, prompt_builder period) | ✅ Done |
| **P1-1** | `MemoryScope` frozen dataclass (`core/memory/scope.py`) | ✅ Done |
| **P1-2** | `path_resolver.py` + all per-store migrations (see §2) + remaining path audit + artifact/domain guard | ✅ Done |
| **T-14A** | `require_character_id` fail-loud guard wired into all 8 migrated scoped stores | ✅ Done |
| **T-14B** | `test_memory_direct_path_lint.py` — direct-path lint guard with 3 known violations pinned (see §5) | ✅ Done |

---

## 2. Migrated Artifacts (path_resolver REALITY_USER_ARTIFACTS)

All ten of the following artifacts resolve through `resolve_path(scope, artifact)` in
`core/memory/path_resolver.py`. Each has a matching integration test under `tests/`.

| Artifact key | Store / module | Integration test |
|---|---|---|
| `history` | `core/memory/short_term.py` | `test_short_term_resolver_integration.py` |
| `event_log` | `core/memory/event_log.py` | `test_event_log_resolver_integration.py` |
| `mid_term` | `core/memory/mid_term.py` | `test_mid_term_resolver_integration.py` |
| `episodic` | `core/memory/episodic_memory.py` | `test_episodic_resolver_integration.py` |
| `memory_index` | `core/memory/episodic_memory.py` | `test_episodic_resolver_integration.py` |
| `fixation_state` | `core/memory/fixation_state.py` | `test_fixation_state_resolver_integration.py` |
| `profile` | `core/memory/user_profile.py` | `test_user_profile_resolver_integration.py` |
| `identity` | `core/memory/user_identity.py` | `test_identity_resolver_integration.py` |
| `hidden_state` | `core/memory/user_hidden_state_store.py` | `test_hidden_state_store_resolver_integration.py` |
| `afterglow_residue` | `core/memory/user_hidden_state_store.py` | `test_hidden_state_store_resolver_integration.py` |

**Additional resolver artifact sets** (not per-user, already correct before P1-2):

- `REALITY_CHARACTER_ARTIFACTS`: `mood_state`, `trait_state`, `author_note_state`, `observations`, `garden_plants`, `garden_storage`
- `GLOBAL_USER_ARTIFACTS`: `user_facts` *(path defined in resolver but store not migrated — see §4)*
- `DREAM_ARTIFACTS`: `dream_state`

---

## 3. Existing Guards

### 3.1 MemoryScope domain guard (`core/memory/scope.py`)

`MemoryScope.__post_init__` enforces:
- `global` scope: `character_id` and `world_id` must be `None`.
- `reality` scope: `character_id` must be a non-empty `str`; `world_id` must be `None`.
- `dream` scope: both `character_id` and `world_id` must be non-empty `str`.

Tests: `tests/test_memory_scope.py` (34 tests)

### 3.2 path_resolver artifact/domain allowlist (`core/memory/path_resolver.py`)

`resolve_path()` raises `ValueError` for:
- Unknown artifact keys (not in any allowlist frozenset).
- Scope domain mismatch (e.g., passing `global` scope for a `reality` artifact).

Tests: `tests/test_memory_path_resolver_guard.py` (37 tests)

### 3.3 `require_character_id` fail-loud guard (`core/memory/scope.py`)

Raises `ValueError` immediately if `char_id` is `None`, `""`, or non-`str`.
Wired into all 8 migrated scoped-store path helpers.

Tests: `tests/test_scoped_store_char_id_guard.py` (58 tests)

### 3.4 Direct-path lint guard

`tests/test_memory_direct_path_lint.py` scans source for calls to
`user_memory_root(` or `_p("` **without** a `char_id=` keyword argument, and asserts that
only the 3 known violations remain (pinned by file + line range). Any new direct-path
call will fail the lint test.

Tests: `tests/test_memory_direct_path_lint.py` (25 tests)

---

## 4. Legacy / Unmigrated Items

### 4.1 `character_growth` — character_growth legacy/dead registered tool

`character_growth` is in `LEGACY_ARTIFACTS` in `path_resolver.py`. Its path still
resolves for audit/compat, but:
- It is a dead registered tool — no active production write path.
- **Do not migrate to `REALITY_USER_ARTIFACTS`.**
- **Do not add a scoped store or integration test for it.**

### 4.2 DLQ payload missing char_id — legacy compatibility

When a slow_queue payload lacks `char_id`, the handler falls back to `"yexuan"` with a
`WARN` log. This is a legacy compat shim. It is intentional and must remain `WARN` (not
silent). Do not remove the fallback; it will be superseded by P1-3A scope-payload work.

### 4.3 API default `char_id="yexuan"`

Several admin/pipeline entry points default `char_id` to `"yexuan"` when not supplied.
This is the single-character compatibility default. **Do not delete these defaults** until
P1-3/T-14 follow-up work explicitly replaces them with scope payload propagation.

### 4.4 `user_facts` — not yet migrated

`user_facts` path is defined in `GLOBAL_USER_ARTIFACTS` in the resolver, but the store
itself is not migrated. This is tracked as **P1-4** work. Do not migrate it in this
phase.

---

## 5. Known Violations (pinned in T-14B lint)

These three call sites pass no `char_id=` to `user_memory_root()`. They are pinned in
the direct-path lint test and **must not be "fixed" ad hoc**. Each requires upstream
scope propagation before it can be properly wired.

| # | File | Line(s) | Reason not fixed here |
|---|------|---------|----------------------|
| 1 | `admin/routers/chat_log.py` | ~31 | Needs route-level scope (char_id comes from request context, not available at read site) |
| 2 | `core/scheduler/loop.py` | ~295 | Needs scheduler scope payload; `_has_event_today()` has no char context |
| 3 | `core/scheduler/last_mentioned.py` | ~387 | Same: reads event_log by uid only; char context not threaded through scheduler callers |

**Do not fix these in the current window.** Fix target: P1-3C (after scope payload and
scheduler/admin scope propagation are in place).

---

## 6. Next Phase Recommendations

Work the phases in order. Each phase is independently deliverable.

### P1-3A — Scope payload in slow_queue

Thread `MemoryScope` (serialized via `to_payload()` / `from_payload()`) through the
slow_queue enqueue/dispatch path. Store APIs are unchanged at this stage; just replace
the raw `char_id` + `uid` dict entries with a serialized `MemoryScope`. Retire the
`"yexuan"` DLQ fallback once all callers are confirmed to send a valid scope.

### P1-3B — Pipeline constructs MemoryScope internally

Pipeline `fetch_context()` and `build_prompt()` construct a `MemoryScope` from the
resolved `char_id` + `uid` at entry. Pass the scope object down to store calls instead
of bare strings. Store APIs still accept `char_id` strings at this stage — no API break.

### P1-3C — Fix scheduler/admin event_log known violations

After P1-3A/B thread scope through scheduler and admin routes, replace the three pinned
violations (§5) with proper resolver calls. Remove their exemptions from the lint test.

### P1-4 — user_facts global split

Migrate `user_facts` store to `GLOBAL_USER_ARTIFACTS` path via resolver. Decide whether
per-character fact isolation is needed or whether global is correct.

### P2 — Legacy data migration

Rename on-disk files from old uid-only paths to the new `{char_id}/{uid}/` layout for
any users who have data under the legacy tree. Provide a migration script; test with
dry-run mode.

---

## 7. Prohibited Actions (do not do in any follow-up PR)

- **Do not migrate `character_growth`** — it is a legacy/dead tool.
- **Do not delete `char_id` API defaults** before scope payload propagation is in place.
- **Do not wire the full scope chain end-to-end in one PR** — phase it as P1-3A → B → C.
- **Do not migrate existing on-disk data** outside of a dedicated P2 migration script.
- **Do not alter the Dream session structure** — dream scope is frozen; char_id + world_id
  are already enforced by `MemoryScope`.
- **Do not migrate `user_facts`** before P1-4 design is agreed.
- **Do not silently swallow the DLQ `"yexuan"` fallback** — it must remain a `WARN` log.

---

## 8. Recommended Regression Commands

Run all four suites before and after any isolation-related change:

```bash
# MemoryScope + path_resolver + guards
pytest tests/test_memory_scope.py tests/test_memory_path_resolver.py \
       tests/test_memory_path_resolver_guard.py tests/test_scoped_store_char_id_guard.py \
       tests/test_memory_direct_path_lint.py -v

# All migrated store integration tests
pytest tests/test_hidden_state_store_resolver_integration.py \
       tests/test_user_profile_resolver_integration.py \
       tests/test_identity_resolver_integration.py \
       tests/test_mid_term_resolver_integration.py \
       tests/test_episodic_resolver_integration.py \
       tests/test_short_term_resolver_integration.py \
       tests/test_event_log_resolver_integration.py \
       tests/test_fixation_state_resolver_integration.py \
       tests/test_memory_resolver_remaining_paths_audit.py -v

# Memory isolation final gate (P0 + P1-0 scope tests)
pytest tests/test_memory_isolation_p0_final.py \
       tests/test_memory_isolation_no_runtime_yexuan_fallback.py \
       tests/test_pipeline_read_scope.py tests/test_pipeline_write_scope.py \
       tests/test_slow_queue_char_scope.py -v

# Direct path lint
pytest tests/test_memory_direct_path_lint.py -v
```

Full suite: `pytest` (currently 1707 tests).

---

## 9. Key Files Reference

| File | Purpose |
|------|---------|
| `core/memory/scope.py` | `MemoryScope` dataclass + `require_character_id` |
| `core/memory/path_resolver.py` | Artifact allowlists + `resolve_path()` |
| `tests/test_memory_scope.py` | 34 MemoryScope tests |
| `tests/test_memory_path_resolver.py` | path_resolver basic tests |
| `tests/test_memory_path_resolver_guard.py` | 37 allowlist/domain guard tests |
| `tests/test_scoped_store_char_id_guard.py` | 58 char_id fail-loud tests (T-14A) |
| `tests/test_memory_direct_path_lint.py` | 25 direct-path lint tests (T-14B) |
| `tests/test_memory_isolation_p0_final.py` | P0 final gate |
| `docs/memory.md` | General memory architecture |
| `docs/memory-isolation-p1-checkpoint.md` | **This file** |
