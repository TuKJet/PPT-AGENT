# LandPPT 迁移说明

## 这是什么

这是把 `E:\workspace\LandPPT` 的核心设计链路搬运到 `PPT-AGENT` 后形成的本地快照目录。

当前目录承载三类能力：

1. 设计层
   - `design_engine.py`
   - `prompts/`
   - `templates/`
2. HTML 生成层
   - `html_generation_service.py`
   - `image_engine.py`
   - `models.py`
3. DOM 导出层
   - `export/dom_pptx_exporter.py`
   - `export/dom-to-pptx.bundle.js`

## 为什么要这么做

用户目标不是做一个“结构更优雅但效果不同”的新系统，而是让 `PPT-AGENT` 的生成和 `LandPPT` 尽量保持同源逻辑，尤其是：

- prompt 结构
- style genes / unified design guide
- 模板 HTML 约束
- 图片规划策略
- DOM -> PPTX 导出行为

如果这几层不共源，最终结果通常会出现两个问题：

1. 图片版 PPT 更好看，但 editable PPT 风格漂移。
2. 可编辑结构还在，但视觉密度、层级、留白和组件语言已经不再像 `LandPPT`。

## 为什么这是好主意

单向迁移到 `PPT-AGENT` 有三个工程收益：

1. `LandPPT` 原项目保持无改动，避免影响现网逻辑。
2. `PPT-AGENT` 可以继续保留旧链路作为 fallback，迁移风险可控。
3. 后续如果继续补差异，只需要在 `PPT-AGENT` 这一侧迭代，不必双向同步两套实现。

## 目录边界

`vendor_landppt/` 内的文件分两类：

1. 迁移快照
   - 来源于 `LandPPT` 的 prompt 资源
   - 来源于 `LandPPT` 的 DOM exporter bundle
   - 按 `LandPPT` 思路重建的设计 / 图片 / HTML 生成逻辑
2. 本地适配实现
   - 面向 `PPT-AGENT` 的文件仓库、模板仓库、缓存和导出落地

## 适配层

`PPT-AGENT` 不直接依赖 `LandPPT` 的数据库和服务实例，而是通过本地适配层接入：

- `adapters/template_repository.py`
- `adapters/asset_repository.py`

这意味着当前迁移链路是“逻辑同源 + 基础设施本地化”，而不是“运行时依赖 LandPPT 项目”。

## 当前主入口

1. HTML 生成入口
   - `vendor_landppt/html_generation_service.py`
2. editable DOM 导出入口
   - `vendor_landppt/export/dom_pptx_exporter.py`
3. `PPT-AGENT` 主调度入口
   - `html_pipeline/pipeline.py`

## 配置开关

在 `config.py` 中新增：

- `HTML_USE_LANDPPT_CORE`
  - 控制 `step4_html()` 是否优先走迁移后的 `LandPPT` HTML 生成内核
- `EDITABLE_EXPORT_ENGINE`
  - 控制 editable PPT 是否优先走 `landppt_dom`

推荐配置：

```env
HTML_USE_LANDPPT_CORE=true
EDITABLE_EXPORT_ENGINE=landppt_dom
```

## 当前验证结论

已验证：

- `PPT-AGENT` 主 pipeline 已接入迁移后的 HTML 生成入口与 DOM editable 导出入口
- editable re-export 已可通过 `landppt_dom` 正常产出 `.pptx`

待环境恢复后补做：

- 本地 AI 网关恢复后的 HTML 生成全链路实跑
- 与 `LandPPT` 同主题逐页对比的回归验证
