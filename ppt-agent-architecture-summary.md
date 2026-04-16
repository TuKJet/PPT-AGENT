# PPT Agent 架构拆解与复用指南

> 目的：把当前仓库 `ppt-agent` 的执行逻辑、阶段状态机、接口调用、提示词体系、产物设计与可复用抽象整理成一份可迁移文档，方便在另一个 `ppt-agent` 项目中复用或重构。

---

## 1. 一句话结论

当前项目本质上是一个**文档驱动的多智能体 PPT 生成工作流**：

- 入口由 `/ppt-agent:ppt` 命令负责调度
- 通过 4 个专职 agent 分阶段协作
- 通过共享 prompt / style / asset 资源统一生成规范
- 通过 `slide-status.json` 与 `review-manifest.json` 实现断点恢复与质量门控
- 通过 Gemini 审查链路把“生成”和“审查”拆开，避免同模型自我打分失真

这套架构适合迁移到另一个项目的原因是：

1. **阶段边界清晰**：每一阶段有明确输入、输出、停止点
2. **中间产物完整**：适合调试、追溯、恢复
3. **提示词体系分层**：内容规划、布局生成、视觉审查互相解耦
4. **外部能力可降级**：搜索能力、Gemini 能力都有 fallback

---

## 2. 文档范围

本文重点覆盖以下内容：

1. 仓库的总体架构分层
2. `/ppt-agent:ppt` 的 7 阶段执行流程
3. 各 agent 的职责、输入输出与消息协议
4. 外部接口/CLI 调用链
5. prompt / skill / role / style / asset 资源体系
6. 状态管理、恢复机制、质量门控
7. 迁移到另一个 `ppt-agent` 项目时建议保留的抽象与建议修正点

---

## 3. 总体架构分层

可以把当前项目拆成 5 层：

| 层 | 作用 | 主要位置 |
|---|---|---|
| 入口编排层 | 接收用户命令、推进阶段、决定何时停住等用户确认 | `commands/ppt.md` |
| 执行代理层 | 分别负责 research / outline / design / review | `agents/*.md` |
| 共享资源层 | 提供 prompt、style、preview template、role prompt | `skills/_shared/**`、`skills/gemini-cli/**` |
| 能力适配层 | 把搜索、Gemini、平台命令封装为 skill/脚本 | `skills/agent-reach/**`、`skills/gemini-cli/**` |
| 运行产物层 | 存储需求、素材、大纲、草稿、审查、交付文件 | `openspec/changes/<run_id>/` |

### 3.1 这是什么

这是一个**偏“流程编排 + 资源驱动”**的仓库，而不是传统的 `src/core/*.ts` 代码主导型仓库。

### 3.2 为什么这么做

因为 Claude 插件/技能生态里，很多逻辑天然就是：

- 命令描述
- agent 行为约束
- prompt 资源
- 中间产物协议

也就是说，当前项目把“流程规则”更多写在文档与技能描述里，而不是完全写进可执行代码。

### 3.3 为什么这是好主意

在 AI 工作流项目早期，这样做有三个现实好处：

- **改 prompt 快**
- **改阶段约束快**
- **跨宿主迁移快**

但它的代价是：当流程变复杂后，容易出现文档漂移，需要你后续在另一个项目里考虑是否补一层真正可执行的 `core/`。

---

## 4. 顶层入口：`/ppt-agent:ppt`

主入口定义在：

- `commands/ppt.md`

它定义了整个工作流的：

- 允许工具
- 参数格式
- required artifacts
- 各阶段流程
- 恢复逻辑
- 质量门控
- 交付逻辑

### 4.1 入口的核心职责

入口 orchestrator 不是“干活的 agent”，而是**调度者**。它主要负责：

1. 解析用户输入与 flag
2. 选择 style / brand override
3. 创建 `run_dir`
4. 决定从哪个 phase 开始或恢复
5. 派发不同 agent
6. 等待用户在 Hard Stop 节点确认
7. 汇总各 agent 产物
8. 驱动 fix loop 与最终 delivery

### 4.2 入口的重要设计原则

当前入口体现了 4 个值得复用的设计原则：

- **每阶段都有明确产物**
- **关键节点必须停下来等用户**
- **并行阶段尽量并行，但共享文件只允许串行合并**
- **状态恢复永远基于文件产物，而不是会话记忆**

---

## 5. 七阶段工作流拆解

下面是最核心的执行流程。

---

### Phase 1 — Init

#### 目标
建立运行上下文，解析参数，确定 style 和运行目录，为后续阶段准备统一输入。

#### 输入
- 用户命令：`/ppt-agent:ppt [--style=...] [--brand-colors=...] [--pages=10-15] [--run-id=...] <topic>`

#### 主要动作
1. 解析 `--style` / `--pages` / `--run-id`
2. 若未提供 `--style`：
   - 先按风格组问用户
   - 再按具体 style 问用户
3. 从 `skills/_shared/index.json` 动态发现 style 注册表，而不是写死列表
4. 如提供 `--brand-colors`，读取品牌色并生成 `brand-style.yaml`
5. 生成 `CHANGE_ID` 与 `RUN_DIR`
6. 创建 OpenSpec scaffold：
   - `proposal.md`
   - `tasks.md`
   - `input.md`

#### 输出产物
- `${RUN_DIR}/proposal.md`
- `${RUN_DIR}/tasks.md`
- `${RUN_DIR}/input.md`
- 可选 `${RUN_DIR}/brand-style.yaml`

#### 为什么这样设计
因为所有后续 agent 都依赖统一上下文：

- 主题是什么
- 风格是什么
- 页数范围是什么
- 当前运行目录在哪里

如果入口不统一，后续 agent 就会各自猜。

#### 为什么这是好主意
它把“会影响全局输出”的变量提前固化成文件，避免后续 agent 因上下文漂移产生分叉。

---

### Phase 2 — Requirement Research（Hard Stop）

#### 目标
先做背景调研，再向用户确认真正要讲什么、给谁讲、用什么口吻讲。

#### 派发 agent
- `ppt-agent:research-core`

#### 主要动作
1. 调用 `research-core mode=research`
2. 产出背景调研文件 `research-context.md`
3. 强制使用 `AskUserQuestion` 询问：
   - audience
   - purpose
   - key messages
   - tone
   - constraints
4. 等用户回答后，生成 `requirements.md`

#### 输出产物
- `${RUN_DIR}/research-context.md`
- `${RUN_DIR}/requirements.md`

#### 这是 Hard Stop 的原因
因为即便搜索结果很多，PPT 依然可能有多种方向：

- 面向投资人
- 面向客户
- 面向内部汇报
- 面向科普教学

没有用户确认，后续大纲很容易走偏。

#### 为什么这是好主意
它把“事实调研”和“表达目标”区分开了：

- research 负责找资料
- user clarification 负责校准用途

这个区分是做演示文稿最容易被忽略、但最关键的一步。

---

### Phase 3 — Material Collection（Parallel）

#### 目标
围绕 `requirements.md` 中拆出的章节主题，做更深的分主题素材收集。

#### 派发 agent
- 多个并行 `ppt-agent:research-core`

#### 主要动作
1. 从 `requirements.md` 提取 major section topics
2. 为每个 topic 启动独立 research task
3. 每个 task 把结果写到自己的隔离文件，例如：
   - `materials-market.md`
   - `materials-product.md`
   - `materials-competition.md`
4. 所有收集结束后，由 lead 串行合并成 `materials.md`

#### 输出产物
- `${RUN_DIR}/materials-*.md`（若干中间文件）
- `${RUN_DIR}/materials.md`

#### 为什么这么做
如果多个 agent 同时 append 一个共享文件，会非常容易发生：

- 覆盖
- 顺序混乱
- 内容交叉
- merge 不可预测

#### 为什么这是好主意
“并行收集 + 串行合并”是一个非常值得在另一个项目继续保留的模式。

这是 AI 多 agent 流水线里最常见、也最稳的并发模式之一。

---

### Phase 4 — Outline Planning（Hard Stop）

#### 目标
根据需求与材料，生成结构化大纲，并要求用户显式批准。

#### 派发 agent
- `ppt-agent:content-core mode=outline`

#### 主要动作
1. `content-core` 读取：
   - `input.md`
   - `requirements.md`
   - `materials.md`
   - `outline-architect.md`
2. 按结构框架生成 `outline.json`
3. 生成便于人看的 `outline-preview.md`
4. 以“digital sticky notes”形式向用户展示
5. 用户批准后，把 `outline.json.approved = true`
6. 若用户要求修改，则走 `mode=revise` 做增量修订

#### 输出产物
- `${RUN_DIR}/outline.json`
- `${RUN_DIR}/outline-preview.md`

#### 关键状态位
`outline.json` 中的 `approved` 字段是一个非常重要的**恢复闸门**。

它决定恢复时：

- 是否可以跳过 Phase 4
- 还是必须重新回到大纲确认

#### 为什么这样设计
很多 AI 工作流有“生成了文件就算完成”的误区。但大纲阶段本质上是一个**人与系统共同决策阶段**。

只存在 `outline.json` 不够，必须存在“用户已批准”的状态位。

#### 为什么这是好主意
这是当前仓库最值得移植的设计之一：

> **把“文件存在”和“用户批准”区分成两个状态。**

否则恢复时你会误把“未确认的大纲”当成“已完成的大纲”。

---

### Phase 5 — Planning Draft（策划稿）

#### 目标
基于已批准的大纲，先生成低成本、结构导向的 SVG 草稿。

#### 派发 agent
- `ppt-agent:content-core mode=draft`

#### 主要动作
1. 读取 `outline.json`
2. 读取 `svg-generator.md`
3. 为每一页生成简版 SVG 草稿
4. 生成 `draft-manifest.json`
5. 每 3 页通过消息 `draft_slides_ready(indices=[...])` 通知 lead 可以提前进入设计阶段

#### 输出产物
- `${RUN_DIR}/drafts/slide-{nn}.svg`
- `${RUN_DIR}/draft-manifest.json`

#### 为什么需要草稿层
因为正式设计是最贵的阶段，直接跳到重视觉版式会导致：

- 内容位置反复重排
- 审查成本过高
- fix loop 太重

草稿层的意义是：

- 先确认每页要素布局
- 先建立信息块层级
- 为 Phase 6 提供可靠参考

#### 为什么这是好主意
这是内容生成型工作流的标准优化：

> **先做 cheap draft，再做 expensive polish。**

这个阶段建议你在另一个项目里继续保留。

---

### Phase 6 — Design Draft + Gemini Review

这是整个项目最有价值的一段，也是迁移时最值得保留的核心机制。

#### 目标
逐页生成最终设计稿，并通过独立审查链路做质量把关与修复闭环。

#### 派发 agent
- `ppt-agent:slide-core mode=design`
- `ppt-agent:review-core mode=review`
- 所有页完成后再执行 `review-core mode=holistic`

#### 子流程 A：最终设计生成
`slide-core` 读取：

- `outline.json`
- `drafts/slide-{nn}.svg`
- `bento-grid-layout.md`
- `svg-generator.md`
- `skills/_shared/references/styles/${style}.yaml`
- 若存在 `brand-style.yaml` 则优先使用

输出：
- `${RUN_DIR}/slides/slide-{nn}.svg`

#### 子流程 B：设计后自动校验
`slide-core` 在生成 SVG 后会做自动检查：

- XML validity
- `viewBox="0 0 1280 720"`
- font-size floor
- safe area boundary
- color zone compliance

#### 子流程 C：逐页 Gemini 审查
`review-core` 对每页：

1. 读取完整 SVG 源码
2. 读取 style token
3. 读取 `outline.json` 中该页上下文
4. 构造 review prompt
5. 调用 `ppt-agent:gemini-cli`
6. 产出结构化 `review-{nn}.md`

#### 子流程 D：Fix Loop
基于 review 结果进入修复闭环。

修复不是简单按分数分段，而是按**建议类型**驱动：

- `full_rethink`
- `layout_restructure`
- `content_reduction`
- `attribute_change`
- `deck_coordination`（holistic review 用）

这是一个很重要的设计：

> **不要只看分数，要看“应该怎么修”。**

#### 子流程 E：逐页进度持久化
使用 `slide-status.json` 记录每页状态：

```json
{
  "slides": {
    "01": { "status": "passed", "score": 8.2, "fix_rounds": 0, "timestamp": "2026-03-21T10:30:00Z" }
  }
}
```

并采用原子更新流程：

1. 读旧状态
2. 在内存合并
3. 写入 `slide-status.tmp.json`
4. 用 `python3` 校验 JSON
5. 原子替换为 `slide-status.json`

#### 子流程 F：整体一致性审查（Holistic Review）
所有单页 review 完成后，再做整套 deck 的协调性审查，关注：

- Visual Rhythm
- Color Story
- Narrative Arc
- Style Consistency
- Pacing

输出：
- `${RUN_DIR}/reviews/review-holistic.md`

#### 子流程 G：Review Manifest 汇总
最终根据 `slide-status.json` 聚合生成：

- `${RUN_DIR}/review-manifest.json`

这个文件是 Phase 7 的唯一质量输入。

#### 为什么 Phase 6 这么设计
因为 PPT 任务有两个完全不同的问题：

1. **生成问题**：怎么把内容画成版式
2. **评估问题**：这个版式是否真的可读、平衡、统一

把这两件事交给不同角色/模型处理，会比“自己画自己评”靠谱得多。

#### 为什么这是好主意
这是整个项目最值得复用的设计结论：

> **生成器和审查器分离，逐页质量关闭环，再做整套协调审查。**

如果你另一个项目只保留一个创新点，我建议就保留这个。

---

### Phase 7 — Delivery（Hard Stop）

#### 目标
把所有最终产物整理成用户可直接查看和交付的形式。

#### 主要动作
1. 读取 `review-manifest.json`
2. 拷贝所有最终 SVG 到 `output/`
3. 基于 `preview-template.html` 生成 `output/index.html`
4. 从 `outline.json.notes` 提取演讲者备注，生成 `speaker-notes.md`
5. 调用平台命令打开浏览器预览
6. 打印最终摘要

#### 输出产物
- `${RUN_DIR}/output/slide-{nn}.svg`
- `${RUN_DIR}/output/index.html`
- `${RUN_DIR}/output/speaker-notes.md`

#### 为什么这是好主意
因为用户最终需要的不是一堆中间文件，而是：

- 可浏览的交付目录
- 可切换模式的 HTML 预览
- 可讲稿演示的 notes

这让整个 pipeline 从“生成内容”真正升级为“可交付产品”。

---

## 6. 四个 agent 的职责与边界

---

### 6.1 `research-core`

#### 职责
- 背景调研
- 分主题素材收集

#### 输入
- `run_dir`
- `mode`: `research | collect`
- `topic`
- `research_context`（collect 模式可选）

#### 输出
- `research-context.md`
- `materials-*.md`

#### 外部依赖
- `agent-reach` skill
- `probe.sh`
- `WebSearch`
- 可选 CLI：`curl` / `gh` / `yt-dlp` / `xreach` / `mcporter`

#### 核心价值
它不是固定绑死一个搜索服务，而是先探测机器上有什么，再按能力选渠道。

#### 值得迁移的点
- 能力探测
- 分级 fallback
- research 与 collection 的模式分离

---

### 6.2 `content-core`

#### 职责
- 结构化大纲生成
- 大纲增量修订
- 简版草稿 SVG 生成

#### 输入
- `input.md`
- `requirements.md`
- `materials.md`
- `outline-architect.md`
- `svg-generator.md`

#### 输出
- `outline.json`
- `outline-preview.md`
- `drafts/slide-{nn}.svg`
- `draft-manifest.json`

#### 核心价值
它把“内容规划”和“视觉打磨”分开了。这里生成的是**结构正确的草稿**，不是最终视觉稿。

#### 值得迁移的点
- `outline` / `revise` / `draft` 三模式分离
- `approved=false` 的初始约束
- `outline-preview.md` 的人类可审阅层

---

### 6.3 `slide-core`

#### 职责
- 生成最终设计质量的 SVG
- 应用 style token 与 Bento Grid 规范
- 根据 review suggestions 做修复/重构

#### 输入
- `outline.json`
- `draft SVG`
- `bento-grid-layout.md`
- `svg-generator.md`
- style YAML / brand-style YAML
- 可选 `fixes_json`

#### 输出
- `slides/slide-{nn}.svg`

#### 核心价值
它不是从零瞎画，而是基于：

- 结构化大纲
- 草稿布局
- 明确布局规范
- 明确风格 token

来生成最终设计。

#### 值得迁移的点
- `fixes_json` typed suggestions 机制
- 设计后自动校验
- style 与 brand override 合并

---

### 6.4 `review-core`

#### 职责
- 对单页做 layout & aesthetic review
- 在 Gemini 不可用时做技术校验 fallback
- 对整套 deck 做 holistic review

#### 输入
- 最终 SVG 源码
- style token
- page context / outline context

#### 输出
- `review-{nn}.md`
- `review-holistic.md`
- 通过消息返回 `review_passed` / `review_failed`

#### 核心价值
它是整个系统里的“质量裁判 + 修复建议生成器”。

#### 值得迁移的点
- 逐页 review 与 holistic review 分离
- typed suggestion taxonomy
- 明确 hard rules 与 weighted scoring

---

## 7. 消息协议（隐式编排协议）

虽然仓库没有单独的 `protocol.ts`，但实际上已经存在一套隐式消息协议。

### 7.1 常见消息类型

| 消息 | 发送者 | 含义 |
|---|---|---|
| `heartbeat` | 各 agent | 表示任务开始/仍在处理 |
| `research_ready` | `research-core` | 背景调研完成 |
| `collection_ready` | `research-core` | 单主题素材收集完成 |
| `outline_ready` | `content-core` | 大纲或修订版完成 |
| `draft_slides_ready(indices=[...])` | `content-core` | 一批草稿页已可进入下一阶段 |
| `draft_complete` | `content-core` | 草稿阶段全部完成 |
| `slide_ready` | `slide-core` | 单页设计稿完成 |
| `slide_fixed` | `slide-core` | 单页修复完成 |
| `review_passed(...)` | `review-core` | 审查通过 |
| `review_failed(...)` | `review-core` | 审查失败并附建议 |
| `error` | 各 agent | 当前步骤失败 |

### 7.2 这是什么

这是整个系统真正的“运行时协议”。

### 7.3 为什么这么做

因为多 agent 场景下，编排器最需要知道的是：

- 谁完成了
- 谁失败了
- 失败后怎么修
- 哪一批可以继续往下走

### 7.4 为什么这是好主意

这使得 orchestrator 可以保持轻：

- 只负责推进状态
- 不把所有执行细节塞进入口 prompt

### 7.5 迁移建议

在另一个项目里，最好把这些消息协议**显式化**，做成一个固定文档或代码结构，例如：

```ts
interface AgentEvent {
  type:
    | 'heartbeat'
    | 'research_ready'
    | 'collection_ready'
    | 'outline_ready'
    | 'draft_slides_ready'
    | 'draft_complete'
    | 'slide_ready'
    | 'slide_fixed'
    | 'review_passed'
    | 'review_failed'
    | 'error';
  payload: Record<string, unknown>;
}
```

这样你后续会轻松很多。

---

## 8. 外部接口 / CLI 调用地图

当前项目主要不是 HTTP API 调用型，而是 **CLI/Skill/Tool 编排型**。

---

### 8.1 搜索接口链

#### 调用链
`research-core` → `probe.sh` → 根据能力选择 `mcporter / curl / gh / yt-dlp / xreach / WebSearch`

#### 设计特点
- 先探测机器能力
- 再按 tier 选择搜索方式
- 最低可降级到 `WebSearch`

#### 值得复用的地方
不要在另一个项目里把搜索引擎绑死。建议保留：

- provider probing
- tier fallback
- research / collect 区分

---

### 8.2 Gemini 审查接口链

#### 调用链
`review-core` → `Skill(skill="ppt-agent:gemini-cli")` → `invoke-gemini-ppt.ts` → `spawnSync("gemini", ...)`

#### 关键行为
- 把 reviewer role prompt 与运行时 prompt 拼接
- 尝试多个 Gemini model
- 输出 raw review 到 `gemini-raw-{nn}.md`
- 失败后走 fallback

#### 值得复用的地方
保留“**raw output 永久保存**”这个设计。它对调试与追溯非常有价值。

---

### 8.3 交付接口链

#### 调用链
orchestrator → 读取 `preview-template.html` → 填充占位符 → 生成 `output/index.html` → 调用平台命令打开浏览器

#### 值得复用的地方
- preview 模板化
- 输出目录统一
- notes 自动提取

---

## 9. Prompt / Skill / Role / Style 体系

这是另一个你很值得搬过去的部分。

---

### 9.1 Prompt 资源分层

当前共享 prompt 注册表位于：

- `skills/_shared/index.json`

主要 prompt 包括：

| Prompt | 作用 | 典型使用者 |
|---|---|---|
| `outline-architect.md` | 生成结构化 PPT 大纲 | `content-core` |
| `bento-grid-layout.md` | 定义卡片布局系统与组合方式 | `slide-core` |
| `svg-generator.md` | 定义 SVG 画布、字体、图表、CJK 规则 | `content-core` / `slide-core` |
| `cognitive-design-principles.md` | 提供基于认知科学的信息密度/表达原则 | `outline-architect.md` 间接引用 |

### 9.2 Review Role Prompt

独立放在：

- `skills/gemini-cli/references/roles/reviewer.md`

这个文件定义了：

- 质量标准
- suggestion taxonomy
- 输出格式
- 评分模型

这是“审查”能力得以稳定复用的关键。

### 9.3 Skill 层的角色

| Skill | 作用 |
|---|---|
| `agent-reach` | 多平台研究能力适配 |
| `ppt-agent:gemini-cli` | Gemini 视觉审查能力适配 |

也就是说，项目采用的是：

- **prompt 负责规则**
- **skill 负责能力接入**
- **agent 负责业务角色**

这是一个非常干净的三层拆法。

### 9.4 Style Registry 体系

style 不是散落的 yaml 文件集合，而是通过 `skills/_shared/index.json` 注册与检索。

这意味着 style 在系统里是“资源”，而不是“文件偶然存在”。

这很适合迁移后继续抽象成：

```ts
interface StyleResource {
  id: string;
  name: string;
  file_path: string;
  keywords: string[];
  description: string;
  use_cases: string[];
}
```

### 9.5 为什么这是好主意

这种资源分层使得你未来扩展时不必动主流程，只要新增：

- 一个 prompt
- 一个 style yaml
- 一个 registry entry

即可纳入系统。

---

## 10. 关键产物设计与目录协议

运行目录是：

```text
openspec/changes/<run_id>/
```

建议把它视作一次运行的**单独工作空间**。

### 10.1 产物分层

| 产物 | 层次 | 用途 |
|---|---|---|
| `input.md` | 输入层 | 记录运行参数 |
| `proposal.md` | 管理层 | 说明这次变更是什么 |
| `tasks.md` | 管理层 | 跟踪阶段完成情况 |
| `research-context.md` | 研究层 | 背景调研结果 |
| `requirements.md` | 需求层 | 用户确认后的需求基线 |
| `materials.md` | 内容层 | 汇总素材 |
| `outline.json` | 结构层 | 正式大纲协议文件 |
| `outline-preview.md` | 结构展示层 | 供用户审阅的大纲视图 |
| `drafts/*.svg` | 草稿层 | 低成本结构草稿 |
| `draft-manifest.json` | 草稿索引层 | 草稿页目录 |
| `slides/*.svg` | 设计层 | 最终设计稿 |
| `slide-status.json` | 状态层 | 单页处理进度 |
| `reviews/review-*.md` | 质量层 | 单页审查报告 |
| `reviews/review-holistic.md` | 质量层 | 整套审查报告 |
| `review-manifest.json` | 发布门禁层 | 最终质量门控 |
| `output/*` | 交付层 | 用户最终可消费产物 |

### 10.2 这个目录协议的价值

这是整个项目第二个非常值得移植的东西。

它把一次运行拆成了：

- 输入
- 中间状态
- 最终产物
- 交付结果

这样一来：

- 好 debug
- 好 resume
- 好做离线审查
- 好做回归比较

---

## 11. 状态管理与恢复机制

这是当前仓库最成熟的工程设计之一。

---

### 11.1 恢复依赖的不是会话，而是文件

恢复逻辑完全基于 `run_dir` 中已有的产物决定下一阶段，从而保证：

- 会话中断后可恢复
- 不依赖 agent 记忆
- 可在不同宿主之间继续执行

### 11.2 Resume 决策顺序

恢复决策大致如下：

1. 有合法 `slide-status.json` → Phase 6 继续
2. 仅有 `draft-manifest.json` → 从 Phase 6 起点继续
3. `outline.json.approved=true` → Phase 5
4. `outline.json.approved=false` 或缺失 → 回到 Phase 4
5. 有 `materials.md` → Phase 4
6. 有 `requirements.md` → Phase 3
7. 有 `research-context.md` → Phase 2
8. 其他情况 → Phase 1

### 11.3 为什么这样设计

AI 流程项目里，真正稳定的恢复点必须是：

- 可验证
- 可读
- 可重建上下文

文件天生比内存态更符合这个要求。

### 11.4 为什么这是好主意

这套机制非常适合另一个项目继续采用，尤其如果你要支持：

- 长时运行
- 大文件产出
- 多宿主运行
- 中途审批

---

## 12. 质量系统设计

当前质量系统分成三层：

1. **生成后自动检查**（slide-core）
2. **逐页视觉审查**（review-core）
3. **整套一致性审查**（holistic review）

---

### 12.1 自动检查层

主要检查：

- XML validity
- 正确 viewBox
- font-size 下限
- safe area
- color zone

#### 作用
先过滤掉“明显坏掉”的 SVG，避免浪费昂贵的 LLM 审查资源。

---

### 12.2 逐页审查层

reviewer 采用 weighted scoring：

| Criterion | Weight |
|---|---|
| Layout Balance | 25% |
| Readability | 25% |
| Typography | 20% |
| Information Density | 20% |
| Color Harmony | 10% |

通过条件：

- weighted overall score >= 7.0
- Layout >= 6
- Readability >= 6
- 无 Critical issue

#### 亮点
不是只打分，而是输出**typed suggestions**。

这意味着系统可以自动判断：

- 改属性就够
- 需要换布局
- 需要重做
- 需要删内容

---

### 12.3 整套一致性审查层

holistic review 检查 deck 级问题：

- 视觉节奏是否单调
- 颜色叙事是否一致
- 讲述节奏是否合理
- 是否缺少“呼吸页”
- 是否存在连续高密度页压迫感

#### 亮点
单页优秀，不代表整套优秀。

这一层正好补上单页审查看不到的问题。

---

## 13. 当前架构的优点总结

### 13.1 强过程约束
每一阶段做什么、不做什么、产出什么都很清楚。

### 13.2 人机协作点明确
Hard Stop 节点很清晰，避免“先做完再说”。

### 13.3 中间文件齐全
几乎每一步都有文件产物，方便回放与定位问题。

### 13.4 生成与审查解耦
避免自评失真，提升质量控制可信度。

### 13.5 可恢复能力强
`approved`、`slide-status.json`、`review-manifest.json` 构成了很稳的恢复链。

### 13.6 可扩展性不错
style、prompt、skill 都有明确挂载点。

---

## 14. 当前架构的局限与风险

这部分对你迁移时很重要。

---

### 14.1 目前更像“文档编排”，不是“代码编排”

仓库里没有真正独立的 `core/` 工作流代码层（至少当前仓库里未看到）。

#### 风险
- 状态机逻辑容易散落在多个 md 中
- prompt 改了但命令文档没同步，就会漂移
- 很难做真正自动化测试

#### 迁移建议
如果另一个项目更长期维护，建议把下面几类逻辑抽成代码：

- run state 判定
- artifact existence / validity 校验
- review suggestion routing
- manifest 聚合

---

### 14.2 Gemini fallback 文档存在分叉

这里有一处需要你注意：

- `skills/gemini-cli/SKILL.md` 一处表述倾向“Gemini 不可用时用 Claude self-optimization”
- `agents/review-core.md` 和主流程文档则更明确倾向“technical validation only”

#### 风险
另一个项目如果照抄，可能会在 fallback 策略上自相矛盾。

#### 建议
迁移时统一成一个单一事实来源。我更推荐当前仓库较新的、也更诚实的策略：

> Gemini 不可用时只做 technical validation，不伪造审美评审。

---

### 14.3 消息协议尚未显式结构化

当前消息是隐式约定，缺少统一 schema。

#### 风险
随着 agent 增多，消息名和 payload 可能失控。

#### 建议
在新项目里显式定义事件协议。

---

### 14.4 搜索能力依赖宿主环境

虽然有 fallback，但研究质量仍然会受到：

- 是否有 `mcporter`
- 是否有 `gh`
- 是否有 `yt-dlp`
- `curl` 是否可用

影响。

#### 建议
新项目里尽量把“能力探测结果”写入一个固定诊断文件，比如：

```json
{
  "search_capabilities": {
    "curl": true,
    "gh": false,
    "mcporter": true,
    "exa": true
  }
}
```

这样会更可观察。

---

## 15. 迁移到另一个 `ppt-agent` 项目时，建议保留什么

如果你要在另一个项目里复用这套思路，我建议分成“必须保留”和“可简化”两组。

---

### 15.1 必须保留的设计

#### A. Hard Stop 机制
至少保留两个：
- 需求确认
- 大纲确认

#### B. `outline.json.approved`
这个状态位非常关键。

#### C. 草稿层
不要直接从 outline 跳 final design。

#### D. review suggestion taxonomy
typed suggestion 比“打分 + 文字点评”强很多。

#### E. `slide-status.json`
断点恢复的核心。

#### F. `review-manifest.json`
最终发布门禁核心。

#### G. style registry
不要写死风格列表。

---

### 15.2 可以按项目规模简化的设计

#### A. 平台搜索能力
如果你的另一个项目只跑固定环境，可以删掉一部分多平台 fallback。

#### B. holistic review
如果项目前期规模小，可以先只保留逐页 review。

#### C. brand color override
如果另一个项目只做通用模板，可以先不做品牌色覆盖。

#### D. preview HTML
如果你只需要 SVG 输出，可先不生成 `index.html`。

---

## 16. 建议在新项目中抽象出的核心模块

如果你准备把另一个项目做得更“工程化”，建议抽这些抽象。

---

### 16.1 `RunContext`
负责统一管理：
- run_id
- run_dir
- topic
- style
- page range
- flags

---

### 16.2 `ArtifactStore`
负责：
- 读写运行产物
- 文件存在性检测
- schema 校验
- 原子写入 checkpoint

---

### 16.3 `PhaseController`
负责：
- 当前 phase 决策
- resume point 判定
- Hard Stop 进入/退出

---

### 16.4 `MessageBus` / `AgentEventProtocol`
负责：
- agent 事件 schema
- 事件路由
- ack / error 规范

---

### 16.5 `StyleRegistry`
负责：
- 枚举可用 style
- 查询 style metadata
- brand override 合并

---

### 16.6 `SearchProviderResolver`
负责：
- 探测能力
- 决定 provider
- 输出统一 research result

---

### 16.7 `ReviewEngine`
负责：
- 调用 Gemini / fallback
- 解析 structured review
- 计算 fix strategy
- 生成 `review-manifest.json`

---

### 16.8 `DeliveryAssembler`
负责：
- 整理 SVG
- 生成 preview HTML
- 生成 speaker notes
- 输出最终 summary

---

## 17. 一个推荐的“新项目更优架构”

如果你是基于这个仓库思路去完善另一个项目，我建议采用：

### 方案：文档规则 + 代码状态机混合架构

#### 保留文档驱动的部分
- prompt 资源
- role 资源
- style 资源
- agent 职责描述

#### 改成代码驱动的部分
- phase state machine
- resume logic
- artifact validation
- message protocol
- review manifest aggregation

### 为什么这么做
因为这些部分更适合代码：

- 状态判断
- JSON schema 校验
- 文件完整性校验
- 多 agent 事件处理

### 为什么这是好主意
你可以同时保留：

- AI 工作流的灵活性
- 工程系统的稳定性

这比完全照搬当前“主要靠 md 文档编排”的方式，更适合长期演进。

---

## 18. 可直接复用的设计清单

下面是一份可以直接作为新项目 backlog 的清单：

### 流程设计
- [ ] 保留 7 阶段 pipeline
- [ ] 至少保留需求与大纲两个 Hard Stop
- [ ] 保留草稿层与最终设计层分离
- [ ] 保留逐页 review + holistic review 双层质量机制

### 状态管理
- [ ] 保留 `outline.json.approved`
- [ ] 保留 `slide-status.json` checkpoint
- [ ] 保留 `review-manifest.json` 作为发布门禁
- [ ] 把恢复逻辑改成代码实现

### 资源系统
- [ ] 建立 prompt registry
- [ ] 建立 style registry
- [ ] 把 role prompt 独立成资源文件
- [ ] 把 preview template 独立成 asset

### 协议系统
- [ ] 显式定义 agent event schema
- [ ] 统一 `review_failed` 的 payload 结构
- [ ] 统一 typed suggestions schema

### 质量系统
- [ ] 保留自动技术校验
- [ ] 保留 layout/readability hard gate
- [ ] 明确 Gemini fallback 的唯一策略
- [ ] 保留 raw review artifact

---

## 19. 给另一个项目的落地建议（按优先级）

### P0：必须先做
1. 建 run_dir 产物协议
2. 建 `outline.json` schema
3. 建 `approved` 状态位
4. 建 `slide-status.json` checkpoint
5. 建 typed review suggestions

### P1：强烈建议做
1. 建草稿层
2. 建 style registry
3. 建 preview HTML
4. 建 holistic review

### P2：可后做
1. 多平台搜索 fallback
2. 品牌色覆盖
3. 多宿主适配
4. MCP 化 / headless 化

---

## 20. 结语

这套 `ppt-agent` 架构最有价值的，不是“它会做 PPT”，而是它把 AI 生成任务拆成了一个相对成熟的工程流水线：

- 前面用 research 和 outline 解决“做什么”
- 中间用 draft 和 design 解决“怎么做”
- 后面用 review 和 delivery 解决“做得够不够好、怎么交付”

如果你要完善另一个 `ppt-agent` 项目，我最推荐你复用这 5 个核心思想：

1. **阶段化**：不要一把梭生成最终 PPT
2. **Hard Stop**：需求和大纲必须确认
3. **双层产物**：草稿与设计分离
4. **双角色质量机制**：生成器与审查器分离
5. **文件化状态恢复**：恢复永远基于产物

如果做得再工程化一点，就把状态机、协议、校验逻辑抽到代码里。

---

## 21. 参考文件索引

### 主流程
- `commands/ppt.md`
- `CLAUDE.md`
- `README.md`

### Agents
- `agents/research-core.md`
- `agents/content-core.md`
- `agents/slide-core.md`
- `agents/review-core.md`

### Shared Prompts
- `skills/_shared/references/prompts/outline-architect.md`
- `skills/_shared/references/prompts/bento-grid-layout.md`
- `skills/_shared/references/prompts/svg-generator.md`
- `skills/_shared/references/prompts/cognitive-design-principles.md`

### Skills
- `skills/agent-reach/SKILL.md`
- `skills/agent-reach/scripts/probe.sh`
- `skills/gemini-cli/SKILL.md`
- `skills/gemini-cli/scripts/invoke-gemini-ppt.ts`
- `skills/gemini-cli/references/roles/reviewer.md`

### Registry / Assets
- `skills/_shared/index.json`
- `skills/_shared/assets/preview-template.html`

---

## 22. 附：推荐在新项目中保留的最小结构

```text
ppt-agent/
├─ commands/
│  └─ ppt.md
├─ agents/
│  ├─ research-core.md
│  ├─ content-core.md
│  ├─ slide-core.md
│  └─ review-core.md
├─ skills/
│  ├─ _shared/
│  │  ├─ index.json
│  │  ├─ references/
│  │  │  ├─ prompts/
│  │  │  │  ├─ outline-architect.md
│  │  │  │  ├─ bento-grid-layout.md
│  │  │  │  └─ svg-generator.md
│  │  └─ assets/
│  │     └─ preview-template.html
│  ├─ agent-reach/
│  └─ gemini-cli/
├─ core/                    # 新项目建议新增
│  ├─ phase-controller.ts
│  ├─ artifact-store.ts
│  ├─ review-engine.ts
│  ├─ event-protocol.ts
│  └─ style-registry.ts
└─ openspec/changes/<run_id>/
```

如果你的另一个项目要做长期维护，我建议最终目标就是这个结构。
