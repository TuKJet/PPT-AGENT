# PPT Deck Workflow Agent

Codex-facing PPT generation workflow with explicit outline, content, slide-plan approval checkpoints and HTML/SVG/IMG renderer branches.

This branch is skill-first. Codex generates deck content inside the Codex conversation; repository code only handles deterministic artifact bookkeeping, render cleanup, screenshots, and PPTX export.

## Quick Use / 快速使用

安装完成后，在需要制作 PPT 的工作目录中新建一个 Codex 任务。最稳定的触发方式是在提示词开头显式写出 Skill 名称：

```text
使用 $ppt-deck-workflow 帮我制作一个中文 PPT。

主题：公司内部 AI 工具使用指南
受众：普通同事
页数：6 页
风格：简洁、专业、图文结合

请按 Skill 的审批流程执行，先只生成大纲。
```

也可以直接说“帮我做一个 PPT”让 Codex 自动匹配；需要确保触发时，优先使用 `$ppt-deck-workflow` 显式点名。

正常流程是：

```text
大纲预览 → 用户批准 → 内容预览 → 用户批准 → 页面规划预览 → 用户批准
         → 选择 IMG（推荐）/ HTML / SVG → 渲染并导出 PPTX
```

在每个预览阶段回复 `批准` 即可继续，也可以直接提出修改，例如“合并第 3、4 页并压缩到 5 页”。渲染方式的常见选择：

- `IMG`（默认推荐）：生成视觉完成度更高的整页图片；原始 IMG PPTX 导出后，Skill 会再单独询问是否生成 SVG 版本。
- `HTML`：需要稳定的确定性排版或尝试导出可编辑 PPTX 时选择，但不再作为默认推荐。
- `SVG`：适合文字、卡片、箭头和简单图形组成的矢量页面。

所有项目文件默认写入当前工作区的 `output/<project>/`。在本仓库内使用时会加载项目本地 Skill；在其他工作目录中新建 Codex 任务时，会使用安装到 `$CODEX_HOME/skills/ppt-deck-workflow` 的全局 Skill。

全局 Skill 维护也可以直接通过自然语言触发：

```text
使用 $ppt-deck-workflow 查看当前全局 PPT Skill 状态。
使用 $ppt-deck-workflow 检查 GitHub 是否有更新，只检查，不升级。
使用 $ppt-deck-workflow 升级到记录的 GitHub 分支最新版本。
使用 $ppt-deck-workflow 回滚到最近一个备份版本。
```

`status` 不联网，`check` 只读检查远端；只有明确提出“升级”或“回滚”时才会修改全局 Skill。首次安装请继续阅读 [Install For An Agent](#install-for-an-agent)，更新与回滚细节见 [Upgrade The Global Skill](#upgrade-the-global-skill)。

## PowerPoint Skill Routing / PowerPoint Skill 路由

Codex 可能同时提供通用 `Presentations` Skill 和本项目的 `ppt-deck-workflow`。两者都可能匹配“创建 PowerPoint”请求，但第三方 Skill 没有可用于声明固定优先级的配置。因此，全局安装完成后，安装 Agent 必须检查当前用户的全局 Codex 指令是否已经划分这两个 Skill 的职责。

安装脚本只负责安装和验证 Skill，不会直接修改用户的全局指令。执行安装的 Agent 应在安装验证通过后完成以下检查：

1. 确定 `$CODEX_HOME`；未设置时使用 `~/.codex`。
2. 如果 `$CODEX_HOME/AGENTS.override.md` 存在且非空，它是当前活动的全局指令文件；否则检查 `$CODEX_HOME/AGENTS.md`。
3. 如果活动文件已经包含等效的 PowerPoint Skill 路由，不要重复修改。
4. 如果缺少路由，先向用户说明冲突并请求修改全局指令的权限。获得批准后，保留文件中的所有现有内容，只追加或更新下面的规则；不得覆盖整个文件。
5. 如果用户不批准修改，明确报告全局路由尚未配置。以后新建 PPT 时需要显式使用 `$ppt-deck-workflow`。
6. 修改完成后提示用户新建一个 Codex 任务；全局 `AGENTS.md` 通常在新任务启动时加载。

建议写入的全局规则：

```markdown
## Presentation Skill Routing

- For any request to create, make, generate, or design a new PowerPoint, PPT, PPTX, presentation, or slide deck, use `ppt-deck-workflow`.
- This routing takes precedence over the generic `Presentations` skill for all net-new PowerPoint creation.
- Use the generic `Presentations` skill only to inspect or edit an unrelated existing presentation, work with native Google Slides, or when the user explicitly invokes `$Presentations`.
- If both skills match, `ppt-deck-workflow` owns the workflow. Do not start both presentation workflows in parallel.
```

修改全局 Codex 指令不是安装脚本的一部分。不同 Agent 或沙箱的权限机制可能不同；如果目标文件不在当前可写范围内，安装 Agent 应在安装过程中向用户申请所需权限，而不是跳过检查或静默覆盖文件。

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

完成本节的安装和验证后，安装 Agent 还必须执行 [PowerPoint Skill Routing](#powerpoint-skill-routing--powerpoint-skill-路由) 中的全局路由检查。Skill 文件安装成功不代表路由检查可以省略；是否需要修改全局 `AGENTS.md`，应以当前用户的实际配置为准。

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
4. Inspects the shared Playwright cache and its `.links` metadata before dependency resolution. If a complete cached Chromium headless-shell revision maps to a Playwright version satisfying the Skill minimum, the installed runtime selects that exact version instead of downloading a newer browser revision.
5. Runs `uv sync --project <installed-skill>/runtime` with `--bootstrap`.
6. Records the GitHub repository, branch, commit, managed file hashes, selected Playwright requirement, cache-reuse decision, and browser revision in `.install-state.json`.
7. Installs only the Playwright Chromium headless shell with `--install-browser` and uses the shared OS browser cache. When the compatible revision already exists, Playwright reuses it without a browser download.
8. Runs the installed `workflow.py --help` as a final verification.

The global skill is therefore independent of the original repository directory. Its Python environment remains under `runtime/.venv`; Playwright browser binaries are shared through the OS cache instead of being duplicated per repository or Skill. The source requirement remains an open minimum, while each installed runtime may materialize an exact cache-compatible Playwright version discovered on that machine. A raw browser revision is never guessed: reuse requires both a complete cache marker and a linked Playwright package whose `browsers.json` names that revision.

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
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-renderer --run-dir output/... --renderer img
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer img
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

Codex writes `outline.json`, `contents.json`, `slide-plans.json`, and the final `html/`, `svg/`, or `img/` renderer files. The helper does not call model APIs.

For `html` and `svg`, renderer choice is followed by an explicit render-review preference:

- `off`: default and recommended unless the user wants an extra review/repair pass
- `on`: Codex runs a screenshot review subflow before export, then records completion with `complete-review`

For `img`, the first `export` creates the original full-image PPTX and completes the requested workflow. Codex should hand off that PPTX, then ask once whether the user wants the optional IMG-to-SVG derivative. Explain that conversion preserves text and simple geometry as vectors so PowerPoint can convert much of the page into editable shapes, and disclose that it uses additional per-page model calls/Token budget. The user only replies to opt in; no reply is required to keep the completed IMG result.

```bash
# only after the IMG PPTX exists and the user explicitly asks to continue
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

With `on`, every `render-jobs/img-svg/slide-xx.json` contains a `source_image_path` that must be passed directly to a vision-capable model. Create one final 1280x720 SVG per page under `img-svg/`: rebuild text and simple geometry as vectors, crop incompatible logo/icon regions directly from the source IMG with Pillow, and embed those crops as Base64 PNG `<image>` nodes. Do not create `v1`, `v2`, overlay, image-elements, or clean SVG variants. The final `<topic>-img-svg.pptx` embeds native SVG media rather than rasterizing the reconstructed page.

After the SVG PPTX is exported, Codex should give these desktop PowerPoint steps: select the slide's SVG object, choose **Convert to Shape**, edit the resulting pieces from **Shape Format**, and use **Shape Format → Group → Ungroup** if the pieces remain grouped. State the boundary clearly: vector regions become editable Office shapes, but semantic text boxes, native charts, and SmartArt are not guaranteed; text may be vector outlines and embedded raster crops remain images.

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
