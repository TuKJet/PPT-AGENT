# 迁移内核导出测试报告

日期：2026-04-17

## 这是什么

这是一份针对 `PPT-AGENT` 可编辑导出链路的回归记录，验证迁移内核是否已经稳定接管 HTML 生成与 DOM editable 导出。

## 为什么要这么做

项目当前的关键目标不是单独跑通某个脚本，而是保证：

- `HTML-first` 主链路可持续工作
- editable PPT 仍然是对象级导出，而不是整页截图壳
- 从现有 HTML 回放时可以稳定重建产物

## 为什么这是好主意

把验证结果沉淀成文档后，后续做布局收敛、导出审计、品牌文本清理时，都能基于同一份事实记录继续推进，减少重复排查。

## 当前验证样例

- 样例一：`output/咖啡的由来_dom_export_test`
- 样例二：`output/AI_Agent_商业化路径与产品落地`

## 当前配置

```powershell
$env:HTML_USE_MIGRATED_CORE='true'
$env:EDITABLE_EXPORT_ENGINE='dom_export'
```

## 已确认结果

- editable 导出链路可以正常产出 `.pptx`
- 导出清单中的 `pipeline` 已统一为 `dom-editable-export`
- 当前模板页脚中的旧品牌文字已移除
- 回放已有 HTML 时，可以重新生成不带旧品牌文案的可编辑产物

## 后续关注点

- 继续做真实主题回放，确认更多历史产物不再残留旧品牌文本
- 保持 DOM 导出与 PowerPoint 回读审计持续可用
