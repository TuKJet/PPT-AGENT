# 迁移内核说明

## 这是什么

`vendor_presentation_core/` 是 `PPT-AGENT` 当前使用的本地迁移内核目录，承载模板、设计约束、图片规划、HTML 生成和 DOM editable 导出能力。

## 为什么要这么做

把核心能力收拢到仓库内，可以避免运行时依赖外部工程，同时让当前项目直接控制模板、导出和审计逻辑。

## 为什么这是好主意

这样做以后，`PPT-AGENT` 可以独立迭代自己的生成与导出能力，不需要维护一套分散的跨工程依赖。

## 目录结构

- `design_engine.py`
- `image_engine.py`
- `html_generation_service.py`
- `prompts/`
- `templates/`
- `export/dom_pptx_exporter.py`
- `export/dom-to-pptx.bundle.js`

## 当前入口

- HTML 生成入口：`html_generation_service.py`
- editable 导出入口：`export/dom_pptx_exporter.py`
- 主调度入口：`html_pipeline/pipeline.py`

## 当前配置

```env
HTML_USE_MIGRATED_CORE=true
EDITABLE_EXPORT_ENGINE=dom_export
```

## 当前状态

- 已接入主 pipeline
- 已支持从现有 HTML 重导出 editable PPT
- 已接入导出结构审计与 PowerPoint 回读预览
- 当前主链统一为开源 `DOM -> editable PPTX`
