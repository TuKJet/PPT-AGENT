# IMG Size And Skill Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the PPT workflow skill with guardrails learned from this run and change the image renderer client to default to a 16:9 `960x540` image size.

**Architecture:** Keep the changes narrow. Treat the skill update as documentation behavior hardening, and treat the image-size change as a small config/client change with tests that lock in the default, env surface, and SDK arguments.

**Tech Stack:** Python, unittest, Markdown skill docs, uv

---

### Task 1: Lock In Failing Tests

**Files:**
- Modify: `D:/work/PPT-AGENT/tests/test_img_renderer.py`

- [ ] **Step 1: Add tests that describe the new expected behavior**

Add assertions for:
- `KRILL_IMAGE_DEFAULT_SIZE == "960x540"`
- `generate_image()` and `edit_image()` send `size="960x540"` by default
- `.env.example` exposes `KRILL_IMAGE_SIZE`
- `ppt-deck-workflow` mentions archiving renderer outputs before compare reruns and mentions `HTML_USE_MIGRATED_CORE=false`

- [ ] **Step 2: Run the focused test file and confirm the new assertions fail**

Run: `uv run python -m unittest tests.test_img_renderer -v`

Expected: failures pointing to the old `1024x1024` default and missing skill/env text.

### Task 2: Implement The Smallest Production Changes

**Files:**
- Modify: `D:/work/PPT-AGENT/krill_image_client.py`
- Modify: `D:/work/PPT-AGENT/config.py`
- Modify: `D:/work/PPT-AGENT/.env.example`
- Modify: `D:/work/PPT-AGENT/.codex/skills/ppt-deck-workflow/SKILL.md`

- [ ] **Step 1: Add a configurable 16:9 default size**

Introduce `KRILL_IMAGE_SIZE` in config with a default of `960x540`, and route the client default size constant through it.

- [ ] **Step 2: Keep generate/edit behavior consistent**

Ensure both `generate_image()` and `edit_image()` use the same configured size value.

- [ ] **Step 3: Add the new workflow guardrails to the skill**

Document:
- archive previous renderer outputs before compare reruns
- prefer `HTML_USE_MIGRATED_CORE=false` on first HTML retry when style guidance was encoded
- if Playwright Chromium is missing, install it before blaming content
- if HTML render fails on the current provider/model gateway, retry the same chain without silently changing provider/model or hand-building slides

### Task 3: Verify

**Files:**
- Test: `D:/work/PPT-AGENT/tests/test_img_renderer.py`

- [ ] **Step 1: Re-run the focused tests**

Run: `uv run python -m unittest tests.test_img_renderer -v`

Expected: PASS

- [ ] **Step 2: Sanity-check the changed files**

Run: `git diff -- D:/work/PPT-AGENT/.codex/skills/ppt-deck-workflow/SKILL.md D:/work/PPT-AGENT/config.py D:/work/PPT-AGENT/krill_image_client.py D:/work/PPT-AGENT/.env.example D:/work/PPT-AGENT/tests/test_img_renderer.py`

Expected: only the planned guardrails and size/config/test changes appear.
