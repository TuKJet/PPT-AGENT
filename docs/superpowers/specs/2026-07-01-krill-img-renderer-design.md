# Krill IMG Renderer Design

## Goal

在 PPT workflow 的 `img` 渲染分支中，使用 `.env` 配置的第三方图片生成 API 逐页生成整页图片，并将这些图片打包为 PPTX；不再依赖 Codex 自身的生图接口。

## Requirements

- `img` 分支必须按页逐张请求图片，而不是一次生成整套 deck。
- 图片提示词要继续以已批准的 `slide-plans.json` 为源，保持当前工作流对 prompt 一致性的要求。
- 第三方接口配置必须来自 `.env`，包括接口地址、鉴权、模型与可调参数。
- 如果 `img` 分支所需配置缺失，流程必须明确提示未配置，并让用户改选 `html/svg` 或补齐配置后继续；不得静默降级。
- 生成结果保存到 `output/.../img/`，最终导出为每页一张整图的 PPTX。

## Approach

- 新增独立的图片客户端模块，专门处理第三方图片 API 请求、响应解析和错误信息。
- 新增 `img` 渲染模块，负责：
  - 校验 `img` 分支所需配置；
  - 将 `slide-plans.json` 编译为逐页 prompt；
  - 逐页调用第三方图片 API；
  - 下载或解码图片并保存到 `img/`；
  - 产出 `slide-status.json` 与最终 PPTX。
- `runner` 扩展为支持 `img` 作为 renderer 选项，并在 `render`/`status` 中纳入该分支。
- `pptx_builder` 增加从 PNG/JPG 整页图片目录导出 PPTX 的能力。

## File Responsibilities

- `config.py`: 第三方图片接口 env 配置。
- `krill_image_client.py`: 第三方图片 API 调用与响应解析。
- `img_renderer.py`: prompt 编译、逐页渲染、图片落盘、状态写入与 PPTX 导出。
- `ppt_workflow/runner.py`: `img` 分支接入。
- `pptx_builder.py`: 图片目录导出 PPTX。
- `tests/`: 针对配置校验、prompt 编译、渲染分支行为的回归测试。

## Error Handling

- 未配置：抛出带操作建议的明确错误。
- API 返回无法解析：抛出包含状态码或关键响应片段的错误。
- 单页生成失败：中止本次 `img` render，并保留已生成文件供排查。

## Verification

- 测试 prompt 编译会剔除占位词并保留应显示文本。
- 测试缺失配置时会报出明确错误。
- 测试 `img` render 会逐页生成图片文件、写入 `slide-status.json`，并调用图片 PPTX 导出路径。
