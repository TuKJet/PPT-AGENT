# LandPPT 迁移测试报告

日期：2026-04-16

## 测试目标

验证 `PPT-AGENT` 中迁入的 `LandPPT` DOM editable 导出链路是否已经可以稳定工作，并确认主 pipeline 已接好迁移入口。

## 测试样例

- 主题：`咖啡的由来`
- 页数：2 页
- 来源：`E:\PPT-AGENT\output\咖啡的由来\html`
- 输出目录：`E:\PPT-AGENT\output\咖啡的由来_landppt_dom_test`

## 执行命令

```powershell
$env:HTML_USE_LANDPPT_CORE='true'
$env:EDITABLE_EXPORT_ENGINE='landppt_dom'
python -m html_pipeline.main `
  --from-html-dir "E:\PPT-AGENT\output\咖啡的由来\html" `
  --output-dir "E:\PPT-AGENT\output\咖啡的由来_landppt_dom_test"
```

## 结果

通过。

产物：

- 图片版 PPT：`E:\PPT-AGENT\output\咖啡的由来_landppt_dom_test\咖啡的由来.pptx`
- 可编辑版 PPT：`E:\PPT-AGENT\output\咖啡的由来_landppt_dom_test\咖啡的由来_editable.pptx`
- 链路清单：`E:\PPT-AGENT\output\咖啡的由来_landppt_dom_test\editable-ppt-chain.json`
- editable 导出清单：`E:\PPT-AGENT\output\咖啡的由来_landppt_dom_test\editable\editable-export-manifest.json`

## PPTX 结构检查

使用 `python-pptx` 读取导出结果后，得到：

- `咖啡的由来.pptx`
  - 2 slides
  - 每页 1 个图片 shape
- `咖啡的由来_editable.pptx`
  - 2 slides
  - Slide 1：56 shapes，其中 37 个带文本
  - Slide 2：52 shapes，其中 36 个带文本

结论：

- editable 导出结果不是整页截图壳，而是包含大量可编辑文本与形状对象
- `landppt_dom` 路线已经成功接入 `PPT-AGENT`

## 完整生成链路补测

在本地 AI 端点切换到 `http://127.0.0.1:8080/v1` 后，补跑了完整 2 页样例：

- 主题：`AI Agent 商业化路径与产品落地`
- 受众：`企业管理层`
- 页数：2 页
- 输出目录：`E:\PPT-AGENT\output\AI_Agent_商业化路径与产品落地`

执行结果：

- `outline -> content -> plan -> HTML -> 图片版 PPT -> editable PPT` 全链路成功跑通
- HTML 布局检查通过 2/2 页
- 图片版 PPT 成功输出
- editable PPT 成功输出

关键产物：

- `E:\PPT-AGENT\output\AI_Agent_商业化路径与产品落地\AI Agent 商业化路径与产品落地.pptx`
- `E:\PPT-AGENT\output\AI_Agent_商业化路径与产品落地\AI Agent 商业化路径与产品落地_editable.pptx`
- `E:\PPT-AGENT\output\AI_Agent_商业化路径与产品落地\editable-ppt-chain.json`

结构检查：

- 图片版 PPT
  - 2 slides
  - 每页 1 个图片 shape
- editable PPT
  - 2 slides
  - Slide 1：47 shapes，其中 26 个带文本
  - Slide 2：47 shapes，其中 30 个带文本

结论：

- 本地新端点已经解除原先 `localhost:8317` 的阻塞
- 迁移后的 `LandPPT HTML + landppt_dom editable` 主链路已经完成端到端验证

## 当前阻塞

已解除：

- `OPENAI_BASE_URL=http://localhost:8317/v1` 不可用导致的全链路生成阻塞

当前剩余：

- 与 `LandPPT` 同主题逐页对比
  - 这部分需要单独把 `LandPPT` 同主题样例也跑出来，再做页面级并排对照
