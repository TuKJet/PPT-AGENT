# Krill IMG Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third-party Krill-backed `img` renderer path that generates one full-slide image per page and exports those images into a PPTX.

**Architecture:** Keep text-model generation and image generation separate. Add one focused image client, one focused `img` renderer orchestration module, and wire the runner plus PPT export to support the new branch without changing the existing `html/svg` flows.

**Tech Stack:** Python 3.11, `httpx`, `python-pptx`, existing workflow state/artifact helpers, `unittest`.

---

### Task 1: Add configuration surface

**Files:**
- Modify: `D:/work/PPT-AGENT/config.py`
- Modify: `D:/work/PPT-AGENT/.env.example`

- [ ] Add env-backed Krill image API configuration with explicit required and optional fields.
- [ ] Add a helper or constants for validating whether `img` rendering is configured.
- [ ] Document the new env variables in `.env.example` with brief usage notes.

### Task 2: Implement the third-party image client

**Files:**
- Create: `D:/work/PPT-AGENT/krill_image_client.py`

- [ ] Add a small HTTP client for the configured image endpoint.
- [ ] Support bearer-style auth plus customizable request keys where practical.
- [ ] Normalize common response shapes into one image result contract.
- [ ] Produce actionable errors for missing fields, HTTP failures, and malformed responses.

### Task 3: Implement img rendering orchestration

**Files:**
- Create: `D:/work/PPT-AGENT/img_renderer.py`
- Modify: `D:/work/PPT-AGENT/pptx_builder.py`

- [ ] Add prompt compilation from `slide-plans.json` that preserves visible copy and strips placeholder text.
- [ ] Render one slide at a time into `output/.../img/`.
- [ ] Save per-slide status entries and final artifacts in workflow state.
- [ ] Add PPTX export from a directory of slide images.

### Task 4: Wire the workflow runner

**Files:**
- Modify: `D:/work/PPT-AGENT/ppt_workflow/runner.py`
- Modify: `D:/work/PPT-AGENT/README.md`
- Modify: `D:/work/PPT-AGENT/AGENT_INIT.md`

- [ ] Allow `choose-renderer --renderer img`.
- [ ] Allow `render --renderer img`.
- [ ] Extend `status` output to report image render artifacts.
- [ ] Document the new `img` branch setup and failure mode when env is missing.

### Task 5: Add regression tests

**Files:**
- Create: `D:/work/PPT-AGENT/tests/test_img_renderer.py`

- [ ] Cover missing-config errors.
- [ ] Cover prompt compilation rules for placeholders vs visible text.
- [ ] Cover end-to-end `img` branch orchestration with stubs for image generation and PPT export.

### Task 6: Verify locally

**Files:**
- Test: `D:/work/PPT-AGENT/tests/test_img_renderer.py`

- [ ] Run targeted tests for the new renderer path.
- [ ] Fix any failing assertions.
- [ ] Confirm no existing runner contracts were broken by the new `img` option.
