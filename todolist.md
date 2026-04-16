# 当前 Todo

> 当前目标：在不改动 `LandPPT` 的前提下，把 `LandPPT` 的设计层、HTML 生成层、DOM 导出层迁入 `PPT-AGENT`，让 `PPT-AGENT` 的结果尽量向 `LandPPT` 对齐，同时保留旧链路 fallback。

## 已确认策略

- [x] 采用“单向迁移到 `PPT-AGENT`”而不是“双项目公共模块抽取”
  - 这是什么：把 `LandPPT` 的核心逻辑和实现搬进 `PPT-AGENT`，`LandPPT` 保持无改动。
  - 为什么要这么做：目标是让两边效果尽量一致，不是优先追求模块抽象优雅。
  - 为什么这是好主意：可以最大化复用 `LandPPT` 的 prompt、模板、style genes、图片规划和 DOM export 能力，同时不影响 `LandPPT` 现有链路。
- [x] 明确迁移范围是“三层一起迁”
  - 这是什么：设计层 + HTML 生成层 + DOM 导出层一并迁入。
  - 为什么要这么做：只搬设计层无法保证最终 HTML 和 editable PPT 仍然同源。
  - 为什么这是好主意：只有三层共源，`PPT-AGENT` 才有机会同时在美观度和可编辑性上贴近 `LandPPT`。

## 已完成

### Phase 0：迁移骨架

- [x] 建立 `vendor_landppt/` 目录
- [x] 建立迁移说明文档
  - 文件：`vendor_landppt/README.md`
- [x] 建立本地适配层目录
  - 文件：`adapters/template_repository.py`
  - 文件：`adapters/asset_repository.py`

### Phase 1：Prompt 与设计内核

- [x] 迁移 `LandPPT` prompts 资源
  - 目录：`vendor_landppt/prompts/`
- [x] 迁移 `style genes` 提取逻辑
  - 文件：`vendor_landppt/design_engine.py`
- [x] 迁移 `unified design guide` 生成逻辑
  - 文件：`vendor_landppt/design_engine.py`
- [x] 迁移模板生成与模板 HTML 校验逻辑
  - 文件：`vendor_landppt/design_engine.py`
- [x] 在 `PPT-AGENT` 中实现本地模板仓库
  - 文件：`adapters/template_repository.py`
  - 文件：`vendor_landppt/templates/templates.json`

### Phase 2：图片规划与素材决策

- [x] 迁移图片需求分析逻辑
  - 文件：`vendor_landppt/image_engine.py`
- [x] 迁移图片相关模型
  - 文件：`vendor_landppt/models.py`
- [x] 实现图片服务本地适配层
  - 文件：`adapters/asset_repository.py`
- [x] 把图片规划结果接入 HTML 生成链路
  - 文件：`vendor_landppt/html_generation_service.py`

### Phase 3：HTML 生成内核

- [x] 新建 `LandPPT` 风格单页 HTML 生成服务
  - 文件：`vendor_landppt/html_generation_service.py`
- [x] 迁移关键 prompt 组装逻辑
  - 文件：`vendor_landppt/html_generation_service.py`
  - 文件：`vendor_landppt/prompts/`
- [x] 接管现有 `step4_html()` 的主生成入口
  - 文件：`html_pipeline/pipeline.py`
- [x] 保留旧 HTML 链路作为 fallback
  - 文件：`html_pipeline/pipeline.py`

### Phase 4：DOM 导出内核

- [x] 迁入 `dom-to-pptx.bundle.js`
  - 文件：`vendor_landppt/export/dom-to-pptx.bundle.js`
- [x] 实现 headless DOM 导出 runner
  - 文件：`vendor_landppt/export/dom_pptx_exporter.py`
- [x] 在 `PPT-AGENT` 适配 DOM 导出输入协议
  - 文件：`vendor_landppt/export/dom_pptx_exporter.py`
- [x] 保留当前 `editable_ppt_poc.py` 作为 fallback
  - 文件：`html_pipeline/pipeline.py`

### Phase 5：链路集成

- [x] 将“设计层 + 图片层 + HTML 生成层”接入现有 `html_pipeline`
  - 文件：`html_pipeline/pipeline.py`
- [x] 将 editable 默认导出切换为 DOM 导出链路
  - 配置：`config.py`
  - 调度：`html_pipeline/pipeline.py`
- [x] 补充迁移配置开关
  - 配置：`HTML_USE_LANDPPT_CORE`
  - 配置：`EDITABLE_EXPORT_ENGINE`
- [x] 统一第一版中间产物结构
  - 文件：`editable-ppt-chain.json`
  - 文件：`editable/editable-export-manifest.json`
  - 文件：`editable/previews/html-source-xx.png`
  - 文件：`editable/previews/editable-preview-xx.png`
- [x] 增加一致性审查所需的双预览产物
  - 当前已保留 HTML source preview 与 editable preview
  - 备注：当前 `editable-preview` 仍以 DOM source 为基准，还不是 Office 实际回读渲染图

### Phase 6：验证与收尾

- [x] 固定一组 2 页样例用于迁移 smoke test
  - 主题：`咖啡的由来`
  - 来源：`output/咖啡的由来/html`
- [x] 跑通 DOM editable re-export 链路
  - 输出目录：`output/咖啡的由来_landppt_dom_test`
- [x] 验证 editable PPT 不是截图壳
  - 检查方式：`python-pptx`
  - 结果：2 slides；第 1 页 56 shapes / 37 text shapes；第 2 页 52 shapes / 36 text shapes
- [x] 记录迁移测试结论与当前阻塞
  - 文件：`migration_test_report.md`

## 当前阻塞

- [x] 跑通“topic -> outline -> content -> plan -> LandPPT HTML -> editable PPT”完整 AI 生成链路
  - 样例：`output/AI_Agent_商业化路径与产品落地`
  - 结果：2 页 HTML、图片版 PPT、editable PPT 全部成功输出
- [ ] 使用同主题逐页对比 `LandPPT` 与 `PPT-AGENT` 输出
  - 当前状态：`PPT-AGENT` 一侧已可完整生成；还需单独运行 `LandPPT` 同主题样例做页面级并排对比

## 完成标准

- [x] `PPT-AGENT` 已接入迁入后的 `LandPPT` 设计与 HTML 生成入口
- [x] `PPT-AGENT` 的 editable 默认导出链路已切换到 `landppt_dom`
- [x] 已有至少一组样例完成 editable DOM 导出与可编辑结构验证
- [x] 已有至少一组样例完成完整 AI 生成到 editable PPT 的端到端验证
- [x] `LandPPT` 项目代码保持无改动

## 备注

- 历史参考文档：`p0_editable_architecture.md`
- 迁移说明：`vendor_landppt/README.md`
- 测试报告：`migration_test_report.md`
- 当前结论：
  - 代码层迁移与接线已完成
  - DOM editable 导出已实测跑通
  - 完整 AI 生成链路在 `127.0.0.1:8080` 端点下已跑通
  - 当前只剩 `LandPPT` 同主题逐页对照这一项增强验证
## 2026-04-16 视觉增强补充

- [x] 放开 `design_prompts.py` 的图片 / 抽象图形提示触发条件
- [x] 在 `html_generation_service.py` 为 cover / toc / summary 追加 richer composition 与 corner cluster 约束
- [x] 在 `signal_dark_master.html` 把右上角升级为 `corner-cluster` 母版结构
- [x] 在 `dom_pptx_exporter.py` 稳定 header 右侧 tail/tag/chip 的宽度与对齐
- [x] 用 1-2 页真实主题重新生成并复核观感
- [x] 在 `html_builder.py` 增加 `cover-header-safe`，让封面页左上标题在贴近上边时自动下沉约 6px
- [x] 在 `dom_pptx_exporter.py` 增加 PPTX 结构审计与自动 fallback，避免 DOM editable 导出退化成近似截图壳时仍被判为通过
