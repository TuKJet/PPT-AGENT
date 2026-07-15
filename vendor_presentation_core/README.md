# Retained PPTX Export Runtime

This directory contains only deterministic browser/PPTX export code still used by the local `ppt-deck-workflow` skill.

Retained files:

- `export/dom_pptx_exporter.py`: converts Codex-authored HTML DOM elements into an editable PPTX
- `export/dom-to-pptx.bundle.js`: bundled browser exporter, also used for native SVG embedding
- `export/powerpoint_preview_renderer.py`: deterministic PowerPoint preview helper

The former repository-side model client, design/image engines, prompt library, and HTML templates were generation-pipeline components. They are intentionally absent in the pure Skill workflow.
