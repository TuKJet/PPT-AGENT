# P0 改造方案: 让 PPT-AGENT 接近 LandPPT 的“好看 + 可编辑”

## 1. 这份方案是什么

这是一版 `P0` 级别的架构改造图和模块输入输出定义，目标不是一次性重写整个项目，而是在保留 `HTML-first` 主链路的前提下，把当前的 `editable ppt` 导出从“基础图元翻译”升级成“设计受控的混合导出”。

现有接入点如下:

- `step4_html()` 在 [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:325)
- `HTML review/fix` 在 [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:442)
- `HTML validate/regenerate` 在 [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:529)
- 图片版 PPT 导出在 [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:657)
- editable 版导出入口在 [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:664)
- HTML -> scene 抽取在 [editable_ppt_poc.py](E:/PPT-AGENT/editable_ppt_poc.py:347)
- editable deck 组装在 [editable_ppt_poc.py](E:/PPT-AGENT/editable_ppt_poc.py:748)
- scene -> pptx 渲染在 [pptx_builder.py](E:/PPT-AGENT/pptx_builder.py:122) 和 [pptx_builder.py](E:/PPT-AGENT/pptx_builder.py:151)

LandPPT 可复用的能力锚点如下:

- `style genes` / design guide 在 [enhanced_ppt_service.py](E:/workspace/LandPPT/src/landppt/services/enhanced_ppt_service.py:3840) 和 [enhanced_ppt_service.py](E:/workspace/LandPPT/src/landppt/services/enhanced_ppt_service.py:3931)
- 全局模板生成在 [global_master_template_service.py](E:/workspace/LandPPT/src/landppt/services/global_master_template_service.py:343)
- 图片需求分析在 [ppt_image_processor.py](E:/workspace/LandPPT/src/landppt/services/ppt_image_processor.py:153)
- DOM 对象级导出与 `addShape/addImage/addText/addTable` 在 [project_slides_editor.html](E:/workspace/LandPPT/src/landppt/web/templates/project_slides_editor.html:18101) 和 [dom-to-pptx.bundle.js](E:/workspace/LandPPT/src/landppt/web/static/js/dom-to-pptx.bundle.js:63883)

## 2. 为什么要这么做

当前 `PPT-AGENT` 的图片版好看，是因为它把 HTML 直接截图进 PPT；editable 版效果差，是因为当前链路只抽到了 `shape/textbox/line` 这类低层图元，丢掉了容器、层次、语义、图片策略和复杂视觉节点的保真能力。

所以真正要补的不是“再写几个 selector”，而是补齐这 4 个缺口:

1. `Deck-level design control`
2. `Visual asset planning`
3. `Semantic scene + hybrid editable export`
4. `HTML vs editable consistency review`

## 3. 为什么这是好主意

因为这套改造复用了现有 `HTML-first` 主链路，不需要推翻重来，却能把最影响效果的瓶颈都卡住:

- 上游把风格锁住，避免每页自由发挥
- 中游把图片和视觉素材决策前置，避免空有文本框
- 下游允许“能编辑的尽量编辑，难复刻的局部截图保真”
- 最后再用一致性审查兜底，避免导出后页页手修

## 4. P0 目标

P0 只追求一件事:

`editable ppt` 生成结果明显更接近 HTML 原稿，同时保留主体内容可编辑，不强求 100% 全原生对象。

量化目标建议:

- `80%+` 的文本内容保持原生可编辑
- `90%+` 的主要布局块位置信息保持稳定
- 复杂装饰节点允许局部位图回退
- 每页自动产出 `html-source.png` 与 `editable-preview.png` 做一致性比对

## 5. P0 总体架构图

```text
                           ┌─────────────────────────────┐
                           │  A. Deck Design Orchestrator │
                           │  全局模板 / style genes / guide│
                           └──────────────┬──────────────┘
                                          │ deck_design_context
                                          v
┌───────────────┐   slide brief   ┌─────────────────────────────┐
│ outline/plan  ├────────────────>│  B. Visual Asset Planner    │
└───────────────┘                 │  图片需求 / 素材来源 / 回退区 │
                                  └──────────────┬──────────────┘
                                                 │ slide_asset_plan
                                                 v
                                  ┌─────────────────────────────┐
                                  │  C. HTML Generation Layer    │
                                  │  step4_html + review + validate│
                                  └──────────────┬──────────────┘
                                                 │ html + preview png
                                                 v
                                  ┌─────────────────────────────┐
                                  │  D. Semantic Scene Extractor │
                                  │  DOM/layout -> semantic scene│
                                  └──────────────┬──────────────┘
                                                 │ scene_v2.json
                                                 v
                                  ┌─────────────────────────────┐
                                  │  E. Hybrid Editable Exporter │
                                  │  native objects + local raster│
                                  └──────────────┬──────────────┘
                                                 │ pptx + preview png
                                                 v
                                  ┌─────────────────────────────┐
                                  │  F. Consistency Auditor      │
                                  │  diff / AI review / fallback │
                                  └─────────────────────────────┘
```

## 6. 模块设计与输入输出

### A. Deck Design Orchestrator

这是什么:
在单页 HTML 生成前，先为整个 deck 生成统一的设计上下文，包含模板、style genes、版式语言、字体策略、颜色和间距规则。

为什么要这么做:
当前 `step4_html()` 主要吃的是单页 prompt。这样单页可能不炸，但全局审美会漂。

为什么这是好主意:
先把“整套 deck 应该长什么样”固定住，后面的 HTML 和 editable 导出都不再是各页单打独斗。

建议新增文件:

- `E:/PPT-AGENT/html_pipeline/deck_design_orchestrator.py`

输入:

```json
{
  "title": "项目标题",
  "audience": "受众",
  "theme_hint": "行业/风格偏好",
  "outline": [{"index": 1, "page_role": "cover", "title": "..." }],
  "brand_assets": {
    "logo_paths": [],
    "preferred_fonts": [],
    "brand_colors": []
  }
}
```

输出:

```json
{
  "template_id": "master_clean_01",
  "style_genes": {
    "tone": "editorial + data-card",
    "palette": ["#0F172A", "#F8FAFC", "#C9974D"],
    "font_pairs": [{"title": "Microsoft YaHei", "body": "Microsoft YaHei"}],
    "shape_language": ["rounded-card", "thin-divider", "badge-pill"]
  },
  "design_guide": {
    "spacing_scale": [4, 8, 12, 16, 24, 32],
    "title_rules": ["single dominant headline"],
    "container_rules": ["card radius 16-24", "avoid dense borders"],
    "export_hints": {
      "prefer_native_text": true,
      "allow_local_raster_for_complex_decorations": true
    }
  }
}
```

接入点:

- 在 [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:325) 之前构建一次 `deck_design_context`
- `step4_html()` 的 prompt 入参增加 `template/style_genes/design_guide`

失败回退:

- 没有生成成功时，使用本地默认模板配置
- 不阻断 HTML 生成，但会降低美观上限

### B. Visual Asset Planner

这是什么:
为每一页决定“要不要图、用什么图、图片应该占多大视觉比重、哪些节点未来允许图片回退”。

为什么要这么做:
当前 editable 版差，很多时候不是文本排版错，而是缺了图片和视觉焦点。

为什么这是好主意:
把图片规划前置后，HTML 和 editable 使用同一份素材策略，不会一个版本有视觉中心，另一个版本只剩文本框。

建议新增文件:

- `E:/PPT-AGENT/html_pipeline/visual_asset_planner.py`

输入:

```json
{
  "slide_brief": {
    "index": 3,
    "page_role": "summary",
    "title": "全球布局",
    "key_points": ["区域扩张", "供应链", "里程碑"]
  },
  "deck_design_context": {},
  "available_assets": {
    "local_images": [],
    "icons": [],
    "illustrations": []
  }
}
```

输出:

```json
{
  "asset_mode": "mixed",
  "hero_visual": {
    "kind": "image",
    "source": "local-search",
    "query": "global supply chain map"
  },
  "support_visuals": [
    {"kind": "icon", "topic": "factory"},
    {"kind": "icon", "topic": "route"}
  ],
  "editable_hints": {
    "safe_native_regions": [".title-wrap", ".summary-card", ".metric-box"],
    "prefer_raster_regions": [".route-map", ".complex-gradient-bg"]
  }
}
```

接入点:

- 在 `step4_html()` 前生成每页 `slide_asset_plan`
- HTML prompt 中明确要求哪些区域必须留出图片位、哪些区域不得用重度 CSS 特效

失败回退:

- 若没有合适图片，降级为 icon + shape 组合
- 若素材检索失败，不阻塞页面生成，但记录缺图状态

### C. HTML Generation Layer 增强

这是什么:
保留现有 `step4_html() + review + validate` 主链路，只补设计控制输入和视觉验收规则。

为什么要这么做:
现有 HTML 生成已经是项目里最成熟的部分，不该推翻；问题在于它只做了“可显示”，还没做足“设计受控”。

为什么这是好主意:
增量改造风险低，而且能把 `P0` 重心留给更关键的 editable 保真问题。

建议改造文件:

- [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:325)
- [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:442)
- [html_pipeline/pipeline.py](E:/PPT-AGENT/html_pipeline/pipeline.py:529)

新增输入:

- `deck_design_context`
- `slide_asset_plan`

新增输出:

```json
{
  "html_path": "html/03_global_map.html",
  "preview_png_path": "html/previews/03.png",
  "visual_contract": {
    "must_preserve_regions": [".title-wrap", ".metric-box"],
    "complex_regions": [".route-map", ".hero-visual"]
  }
}
```

新增校验项:

- 不只检查 overflow
- 还检查视觉重心、留白、主标题支配感、图片占比是否符合 `design_guide`

### D. Semantic Scene Extractor

这是什么:
把当前 [editable_ppt_poc.py](E:/PPT-AGENT/editable_ppt_poc.py:347) 的“平铺 selector 抽取”升级为“容器识别 + 语义图元 + 回退标记”。

为什么要这么做:
现在 scene 基本只有 `shape/textbox/line`，复杂卡片、时间线、图文块一旦拆散，editable 就会变丑。

为什么这是好主意:
先保住语义，再谈渲染。否则 builder 再强，也只能渲染出一堆散件。

建议新增文件:

- `E:/PPT-AGENT/editable_scene/schema_v2.py`
- `E:/PPT-AGENT/editable_scene/dom_semantic_extractor.py`
- `E:/PPT-AGENT/editable_scene/layout_tree.py`

建议替换/改造:

- [editable_ppt_poc.py](E:/PPT-AGENT/editable_ppt_poc.py:347)
- [editable_ppt_poc.py](E:/PPT-AGENT/editable_ppt_poc.py:748)

输入:

```json
{
  "html_path": "html/03_global_map.html",
  "preview_png_path": "html/previews/03.png",
  "visual_contract": {},
  "slide_asset_plan": {},
  "deck_design_context": {}
}
```

输出 `scene_v2.json`:

```json
{
  "background": {"type": "solid", "color": "#F7F8FA"},
  "elements": [
    {
      "type": "group",
      "role": "hero-card",
      "frame": {"x": 0.8, "y": 1.2, "w": 5.4, "h": 2.8},
      "children": [
        {"type": "text", "role": "title", "text": "全球布局", "editable": true},
        {"type": "image", "role": "hero-image", "src": "assets/map.png", "editable": false}
      ]
    },
    {
      "type": "timeline-node",
      "frame": {"x": 7.1, "y": 1.4, "w": 4.8, "h": 1.0},
      "title": "阶段一",
      "desc": "进入新区域",
      "editable": true
    },
    {
      "type": "raster-fragment",
      "role": "decorative-route",
      "frame": {"x": 6.4, "y": 2.2, "w": 2.1, "h": 1.3},
      "source_selector": ".route-map"
    }
  ]
}
```

P0 必须支持的元素类型:

- `text`
- `shape`
- `line`
- `image`
- `table`
- `icon`
- `group`
- `timeline-node`
- `metric-card`
- `raster-fragment`

核心规则:

- 能保持编辑价值的节点优先原生化
- 复杂 SVG、渐变、自由曲线、强装饰节点允许标记为 `raster-fragment`

### E. Hybrid Editable Exporter

这是什么:
把当前 [pptx_builder.py](E:/PPT-AGENT/pptx_builder.py:122) 从只会 `shape/textbox/line` 的 builder，升级为“原生对象优先 + 局部截图回退”的混合导出器。

为什么要这么做:
PowerPoint 不是浏览器，很多 HTML 视觉效果强行翻译只会失真。

为什么这是好主意:
混合导出不是妥协，而是工程上最稳的平衡点。主体内容能改，复杂视觉也不丢。

建议新增文件:

- `E:/PPT-AGENT/pptx_export/hybrid_exporter.py`
- `E:/PPT-AGENT/pptx_export/raster_fallback.py`
- `E:/PPT-AGENT/pptx_export/pptx_object_renderers.py`

建议改造:

- [pptx_builder.py](E:/PPT-AGENT/pptx_builder.py:122)
- [pptx_builder.py](E:/PPT-AGENT/pptx_builder.py:151)

输入:

```json
{
  "scene_v2_path": "editable/scenes/03_global_map.scene.json",
  "assets_dir": "editable/assets/",
  "fallback_fragments_dir": "editable/fragments/"
}
```

输出:

```json
{
  "pptx_path": "out/project_editable.pptx",
  "preview_png_path": "editable/previews/editable-preview-03.png",
  "export_report": {
    "native_text_count": 18,
    "native_shape_count": 9,
    "native_image_count": 2,
    "native_table_count": 1,
    "raster_fragment_count": 3
  }
}
```

P0 渲染能力要求:

- `text` -> `addText` / textbox
- `shape` / `line` -> 原生 shape
- `image` -> 原生 image
- `table` -> 原生 table
- `group` -> 保留逻辑分组信息，至少保证子节点相对布局稳定
- `timeline-node` / `metric-card` -> 映射为预定义原生对象组合
- `raster-fragment` -> 截图后按区域贴图

### F. Consistency Auditor

这是什么:
让 editable 导出真正闭环。对同一页同时产出 `html-source.png` 和 `editable-preview.png`，然后做规则比对或 AI review，决定通过、修复还是降级。

为什么要这么做:
当前链路已经会产出预览，但 review 并没有真正驱动导出修复策略。

为什么这是好主意:
只要有这个模块，质量问题就不再是“肉眼觉得差”，而是“系统知道哪里差、怎么回退”。

建议新增文件:

- `E:/PPT-AGENT/editable_review/consistency_auditor.py`
- `E:/PPT-AGENT/editable_review/repair_policy.py`

输入:

```json
{
  "html_preview_png_path": "editable/previews/html-source-03.png",
  "editable_preview_png_path": "editable/previews/editable-preview-03.png",
  "scene_v2_path": "editable/scenes/03_global_map.scene.json",
  "export_report": {}
}
```

输出:

```json
{
  "result": "repair",
  "score": 0.81,
  "diff_regions": [
    {"selector": ".route-map", "reason": "native reconstruction drift"}
  ],
  "actions": [
    {"type": "replace_with_raster_fragment", "selector": ".route-map"}
  ]
}
```

接入点:

- 置于 [editable_ppt_poc.py](E:/PPT-AGENT/editable_ppt_poc.py:748) 导出后
- 若评分不达标，触发 `scene patch` 或 `fragment fallback`

## 7. P0 数据产物设计

P0 建议固定这几份中间产物，后续调试和回归都依赖它们:

- `deck_design_context.json`
- `slide_asset_plan/{index}.json`
- `editable/scenes/{index}.scene.json`
- `editable/fragments/{index}_{region}.png`
- `editable/previews/html-source-{index}.png`
- `editable/previews/editable-preview-{index}.png`
- `editable/export-report.json`
- `editable/consistency-report.json`

## 8. 与现有代码的接入关系

### 现有链路

```text
outline -> step4_html -> review/fix -> validate/regenerate
       -> build_pptx(image)
       -> build_editable_deck_from_html
          -> extract_html_layout_to_scene
          -> build_editable_deck
```

### P0 改造后链路

```text
outline
  -> build_deck_design_context
  -> build_slide_asset_plan
  -> step4_html(design_context, asset_plan)
  -> review/fix(visual_contract)
  -> validate/regenerate(visual_contract)
  -> build_pptx(image mode)
  -> build_semantic_scene_from_html
  -> export_editable_hybrid
  -> consistency_audit
  -> if needed: patch_scene / replace_fragment / retry_export
```

## 9. 推荐新增模块清单

- `html_pipeline/deck_design_orchestrator.py`
- `html_pipeline/visual_asset_planner.py`
- `editable_scene/schema_v2.py`
- `editable_scene/layout_tree.py`
- `editable_scene/dom_semantic_extractor.py`
- `pptx_export/pptx_object_renderers.py`
- `pptx_export/raster_fallback.py`
- `pptx_export/hybrid_exporter.py`
- `editable_review/consistency_auditor.py`
- `editable_review/repair_policy.py`

## 10. P0 实施顺序

### Step 1. 先补 scene schema 和 hybrid exporter

这是什么:
先把 editable 导出层能表达的对象扩起来。

为什么:
没有表达能力，再好的设计控制也落不进 pptx。

为什么是好主意:
这是影响“可编辑但很丑”最直接的瓶颈。

### Step 2. 再补 visual asset planner

这是什么:
在 HTML 生成前决定图片与复杂区域策略。

为什么:
视觉素材不前置，scene 里永远只剩文字和基础框。

为什么是好主意:
它会让 HTML 和 editable 的视觉中心开始统一。

### Step 3. 最后补 consistency auditor

这是什么:
自动发现 HTML 和 editable 的失真点并回退。

为什么:
没有验收闭环，系统就不知道自己导出了坏结果。

为什么是好主意:
这一步决定方案能不能长期稳定迭代。

## 11. P0 非目标

P0 不做这些事:

- 不追求 100% 把所有 CSS 特效都翻译成原生 pptx
- 不在第一阶段做完整 chart 引擎
- 不在第一阶段做复杂动画还原
- 不先重构整个 HTML pipeline

## 12. 一句话结论

`PPT-AGENT` 想接近 `LandPPT`，不是“把当前 `shape/textbox/line` 规则继续堆厚”，而是要把 editable 链路升级成:

`设计控制 + 图片规划 + 语义 scene + 混合导出 + 一致性闭环`

P0 只要这 5 个点补起来，结果就会从“能编辑但像翻译件”提升到“主体可编辑、视觉明显接近 HTML 原稿”。
