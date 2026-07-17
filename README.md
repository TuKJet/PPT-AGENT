# PPT Deck Workflow Agent

Codex-facing PPT generation workflow with explicit outline, content, slide-plan approval checkpoints and HTML/SVG/IMG renderer branches.

This branch is skill-first. Codex generates deck content inside the Codex conversation; repository code only handles deterministic artifact bookkeeping, render cleanup, screenshots, and PPTX export.

## Repository Surface

The executable surface is intentionally small:

- `.codex/skills/ppt-deck-workflow/`: workflow instructions, contracts, and the state/export helper
- `.codex/skills/ppt-deck-workflow/scripts/install_global_skill.py`: builds a self-contained global skill with a bundled runtime
- `.codex/skills/ppt-deck-workflow/scripts/update_global_skill.py`: checks, upgrades, and rolls back the installed Skill from its recorded GitHub branch
- `html_pipeline/html_builder.py`: deterministic 1280x720 HTML screenshot and image-PPTX export
- `pptx_builder.py`: deterministic SVG image-PPTX export and native-SVG PPTX export
- `vendor_presentation_core/export/`: retained DOM editable export and bundled browser runtime
- `playwright_runtime.py`, `filename_utils.py`: shared deterministic utilities

There is no repository model client, provider configuration, generation pipeline, or runner. HTML/SVG source files are authored by Codex and exporters do not silently rewrite them.

## Install For An Agent

An Agent can use this repository in either of two modes:

- Repository-local mode: clone this project and run the skill from `.codex/skills/ppt-deck-workflow/`.
- Global skill mode: install a self-contained copy under `$CODEX_HOME/skills/ppt-deck-workflow`; the original repository can then be moved or deleted.

Both modes require:

- `uv` on `PATH`.
- Python 3.11 or newer, which `uv` can provision automatically.
- Network access during the first dependency and Chromium installation.
- Git for GitHub branch checks and upgrades of a globally installed Skill.
- Microsoft PowerPoint only for optional Office readback validation; PPTX generation itself does not require Office.

### Repository-Local Agent Installation

From the repository root, an Agent should run:

```bash
uv sync
uv run playwright install --only-shell chromium
uv run python -B -u .codex/skills/ppt-deck-workflow/scripts/workflow.py --help
uv run python -B -m unittest discover -s tests -p "test_*.py"
```

Windows PowerShell uses the same commands:

```powershell
uv sync
uv run playwright install --only-shell chromium
uv run python -B -u .codex\skills\ppt-deck-workflow\scripts\workflow.py --help
uv run python -B -m unittest discover -s tests -p "test_*.py"
```

Installation is ready when:

- `workflow.py --help` lists `choose-img-svg`, `complete-img-svg`, and `export-img-svg`.
- The test suite ends with `OK`.
- The Playwright Chromium headless shell is installed without an error.

### Self-Contained Global Skill Installation

The repository includes a standard-library-only installer:

```text
.codex/skills/ppt-deck-workflow/scripts/install_global_skill.py
```

Default installation target:

```text
$CODEX_HOME/skills/ppt-deck-workflow
```

If `CODEX_HOME` is not set, the target is:

```text
~/.codex/skills/ppt-deck-workflow
```

Windows PowerShell:

```powershell
py -3 .codex\skills\ppt-deck-workflow\scripts\install_global_skill.py `
  --bootstrap `
  --install-browser
```

macOS/Linux:

```bash
python3 .codex/skills/ppt-deck-workflow/scripts/install_global_skill.py \
  --bootstrap \
  --install-browser
```

The installer:

1. Copies `SKILL.md`, `agents/`, `references/`, and `scripts/`.
2. Bundles the deterministic runtime into the installed skill:
   - `filename_utils.py`
   - `playwright_runtime.py`
   - `pptx_builder.py`
   - `html_pipeline/`
   - `vendor_presentation_core/`
3. Creates `runtime/pyproject.toml`.
4. Runs `uv sync --project <installed-skill>/runtime` with `--bootstrap`.
5. Records the GitHub repository, branch, commit, and managed file hashes in `.install-state.json`.
6. Installs only the Playwright Chromium headless shell with `--install-browser` and uses the shared OS browser cache.
7. Runs the installed `workflow.py --help` as a final verification.

The global skill is therefore independent of the original repository directory. Its Python environment remains under `runtime/.venv`; Playwright browser binaries are shared through the OS cache instead of being duplicated per repository or Skill.

Installed layout:

```text
~/.codex/skills/ppt-deck-workflow/
├── .install-state.json
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
├── scripts/
│   ├── workflow.py
│   ├── embed_img_crops.py
│   ├── install_global_skill.py
│   └── update_global_skill.py
└── runtime/
    ├── pyproject.toml
    ├── filename_utils.py
    ├── playwright_runtime.py
    ├── pptx_builder.py
    ├── html_pipeline/
    └── vendor_presentation_core/
```

### Verify The Global Installation

Windows PowerShell:

```powershell
$CodexHome = if ($env:CODEX_HOME) {
  $env:CODEX_HOME
} else {
  Join-Path $HOME ".codex"
}
$PptSkill = Join-Path $CodexHome "skills\ppt-deck-workflow"

uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\workflow.py" --help
```

macOS/Linux:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PPT_SKILL="$CODEX_HOME/skills/ppt-deck-workflow"

uv run --project "$PPT_SKILL/runtime" \
  python -B -u "$PPT_SKILL/scripts/workflow.py" --help
```

For a write-path smoke test, create or enter any workspace and initialize a run:

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Path "D:\work\ppt-agent-smoke" -Force | Out-Null
Set-Location "D:\work\ppt-agent-smoke"

uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\workflow.py" `
  init --topic "PPT Agent Smoke Test" --audience "Internal" --pages "3"

Test-Path ".\output\PPT_Agent_Smoke_Test\workflow-state.json"
```

In global mode, the current directory is the default workspace and the skill writes to that directory's `output/`. To override it:

```powershell
$env:PPT_AGENT_WORKSPACE = "D:\work\my-ppt-workspace"
```

Or set an explicit output root:

```powershell
$env:OUTPUT_DIR = "D:\work\my-ppt-workspace\output"
```

### Upgrade The Global Skill

The installation records its source repository and branch. The defaults are:

```text
https://github.com/TuKJet/PPT-AGENT.git
codex/all-logic-in-skills
```

Resolve the installed path as shown above, then inspect local status without network access:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" status
```

Check the recorded GitHub branch without changing the installation:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" check
```

Upgrade after the user explicitly requests it:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" upgrade
```

The updater performs a depth-one clone of the recorded branch in a temporary directory, builds and validates a candidate, backs up the current managed files, preserves `runtime/.venv`, `runtime/.uv-cache`, local `runtime/uv.lock`, and the shared Playwright cache, then runs `uv sync`, installs the matching headless shell when required, and verifies `workflow.py --help`.

Roll back to the newest retained backup:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" rollback
```

Managed-file hash mismatches stop an upgrade by default. Backups are stored outside the Skill discovery tree under `$CODEX_HOME/skill-state/ppt-deck-workflow/backups`. A successful upgrade or rollback applies to newly loaded Skill instructions on the next Agent turn.

Use `install_global_skill.py --force` only for intentional full replacement, not routine updates; it removes the target directory and its local runtime environment.

### Uninstall The Global Skill

Windows PowerShell:

```powershell
$CodexHome = if ($env:CODEX_HOME) {
  $env:CODEX_HOME
} else {
  Join-Path $HOME ".codex"
}
$Target = Join-Path $CodexHome "skills\ppt-deck-workflow"
$Resolved = Resolve-Path -LiteralPath $Target
$ExpectedParent = [System.IO.Path]::GetFullPath((Join-Path $CodexHome "skills"))

if ([System.IO.Path]::GetFullPath($Resolved.Path).StartsWith($ExpectedParent)) {
  Remove-Item -LiteralPath $Resolved.Path -Recurse -Force
}
```

Uninstalling the skill does not delete any deck workspace or `output/` directory.

## Workflow

Use the local skill at `.codex/skills/ppt-deck-workflow/SKILL.md`.

The helper command is:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...
```

Every deck run must live under `output/<project>/`. Keep all intermediate JSON/Markdown artifacts, renderer files, review files, and exported PPTX files inside that single project folder. If you pass `--run-dir deck-a`, the helper now normalizes it to `output/deck-a`; paths outside `output/` are not allowed.

Typical helper calls:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py init --topic "..." --audience "..." --pages "12"
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-renderer --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-review --run-dir output/... --mode off
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

Codex writes `outline.json`, `contents.json`, `slide-plans.json`, and the final `html/`, `svg/`, or `img/` renderer files. The helper does not call model APIs.

For `html` and `svg`, renderer choice is followed by an explicit render-review preference:

- `off`: default and recommended unless the user wants an extra review/repair pass
- `on`: Codex runs a screenshot review subflow before export, then records completion with `complete-review`

For `img`, the first `export` creates the original full-image PPTX and deliberately stops at `img_svg_choice_pending`. Only then must Codex show that PPTX to the user and ask whether to run the IMG-to-SVG post-process. The helper rejects an early choice.

```bash
# after the IMG PPTX exists and the user answers in chat
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode off

# or, to create one direct-image model job per page
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

With `on`, every `render-jobs/img-svg/slide-xx.json` contains a `source_image_path` that must be passed directly to a vision-capable model. Create one final 1280x720 SVG per page under `img-svg/`: rebuild text and simple geometry as vectors, crop incompatible logo/icon regions directly from the source IMG with Pillow, and embed those crops as Base64 PNG `<image>` nodes. Do not create `v1`, `v2`, overlay, image-elements, or clean SVG variants. The final `<topic>-img-svg.pptx` embeds native SVG media rather than rasterizing the reconstructed page.

The deterministic crop helper is:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/embed_img_crops.py --manifest output/.../render-jobs/img-svg/slide-01-crops.json
```

It converts normalized 1280x720 crop boxes to the source IMG resolution and writes the cropped PNG data directly into the final SVG without temporary image files. Playwright remains the final SVG rendering and QA surface.

For multi-renderer comparison, keep everything in the same run directory under `output/<project>/`. Compare outputs by subdirectory and renderer-specific export filenames instead of forking separate `-html` / `-img` project folders.

For long HTML or SVG decks, prefer `prepare-render-jobs` and let subagents generate one page each while the main agent stays focused on consistency review and export coordination.

## Notes

- Generated decks are written to `output/`.
- Content research should use Codex-native research/web capability directly, not repository AI provider code.
- HTML and SVG export require Playwright Chromium.
- Native IMG-to-SVG PPT export also requires Playwright Chromium because the bundled exporter creates PowerPoint's native SVG media plus its PNG preview and renders final-page QA screenshots.
- HTML export creates an image PPTX and attempts a DOM-based editable PPTX.
- The former `ppt_workflow.runner`, provider client, generation pipeline, prompt/template runtime, and `.env.example` are intentionally removed from this branch.
