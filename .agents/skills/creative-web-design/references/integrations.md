# 已安装上游适配

## 解析、读取、执行是三件事

对话中 `$design-taste-frontend`、`$impeccable audit`、`$oil-motion` 是 Skill 请求，不是 shell 命令。宿主有明确、真实的原生加载能力时采用并记录；没有时主代理用文件工具读取 doctor 解析到的入口与本阶段参考，再使用实际存在的工具执行工作。

当前创建环境有 Skill 目录发现和对话显式提及约定，本次已用真实 Codex CLI 显式请求在隔离样例验证加载与执行。未暴露通用 `invoke_skill()` 工具，主代理执行时实际读取入口并使用工具；其他宿主缺少原生加载机制时采用这条文件读取兼容路线。Codex `skills/list` 只用于发现验证，不是执行接口。不要将文档中的斜线指令或 JSON 规划当作终端程序。

只读入口并记录 SHA-256 后才标记 `read`；shell 工具的输出才能支持 `executed`；有目标行为证据才能支持 `verified`。不要将三个阶段写成一个“已调用”。上游必要初始化同样要有实际执行结果或明确 fallback。

## Doctor

```text
python "SKILL_DIR/scripts/doctor.py" --project "PROJECT"
python "SKILL_DIR/scripts/doctor.py" --project "PROJECT" --require taste
python "SKILL_DIR/scripts/doctor.py" --project "PROJECT" --require impeccable
python "SKILL_DIR/scripts/doctor.py" --project "PROJECT" --require oil-motion --media
python "SKILL_DIR/scripts/doctor.py" --project "PROJECT" --skill-root "EXTRA_SKILLS_ROOT" --shareable
```

默认检查三个入口；运行阶段用 `--require` 缩小必需集合。它仍在有限搜索根中读取入口 frontmatter 和字节哈希以识别真实名称/重复安装，可能列出其他上游元数据；这不代表主代理加载并应用了其他上游指令。默认搜索项目祖先的 `.agents/skills` 到最近仓库根，以及用户 `.agents/skills`、`CODEX_HOME/skills`（未设置时用户 `.codex/skills`）。插件或宿主的其他位置由已暴露的真实路径、`--skill-root` 指定，不扫描整块盘。搜索根可以是 Skills 容器或单个 Skill 目录。

同一规范路径的符号链接去重，不同目录的同名安装保持歧义，即使内容相同。向用户/宿主确定使用哪个入口后仅记录本次选择；不要自动删除另一份。缺失、解析错误与漂移如实报告。入口不存在时不写“已读取”。

能从标准目录及真实头部明确归属的无关依赖诊断列为 `warnings`，不阻塞所需阶段；涉及所需名称的冲突、无法识别的入口、未知/重复名称或读取失败保守列为 `errors`，不能假装发现完整。诊断归属提示不会生成可用候选；只有完整 frontmatter 验证成功才算入口可用。

退出码 0 表示所要求入口/依赖可用；2 表示相关缺失或歧义；1 表示输入/读取/解析错误。JSON 中的本机绝对路径仅为本地输出；分享用 `--shareable`。脚本不下载、安装、读取密钥或更改 hooks。版本无法从文件/与哈希匹配的核对记录确认时为 unknown/null。

## Taste：`design-taste-frontend`

读取解析后的 `SKILL.md`，用其项目理解、方向和构图指导。已核对安装来自标准 `skills/taste-skill`；README 将该入口标为 v2 experimental，入口本身没有版本字段，因此明确记录版本依据。不给它替换成 `gpt-taste`。

规则与参数在任务上下文应用。已确认方向作为输入；教学业务界面或多步骤任务不强套展示页结构。微小 CSS 修复可以跳过 Taste。无需 shell “调用 Taste”。

## Impeccable：`impeccable`

已核对安装为 4.5.2，入口位于其包根 `SKILL.md`，命令详情在 `reference/`。这是一个统一 Skill，Overdrive 是其中的局部能力；独立 `$overdrive` 可只是快捷入口，本编排器依赖统一入口。

进入时按真实 Setup：以项目为 cwd，审阅 `scripts/impeccable`（Windows 使用 `scripts/impeccable.cmd`）及将运行的动作，执行一次 `context`，需要明确目标时传 `--target`。launcher 可能首次下载引擎，不能盲目执行下载；已装引擎或获准后才运行。失败时按上游 fallback 读既有项目上下文并如实说明，不虚构 PRODUCT/DESIGN。

Skill 元数据版本与二进制引擎版本独立；从实际 `scripts/VERSION` 和 launcher 解析引擎位置，不按 4.5.2 猜缓存目录。不要把 `context --help` 当成纯帮助探测：本次安装版本会执行 context；按已读入口传真实目标并记录一次执行。

只加载本次命令对应参考：现状 `reference/critique.md` 或 `audit.md`，实现前按上游要求读 `craft-floor.md`，精修读 `polish.md`；其他任务从入口真实 Commands 表解析。审查不自动运行 `init`、`document`、`doctor` 修复、pin 或 hooks。

`overdrive` 的当前参考有方向选择要求；沿用用户已确认且足以覆盖本次具体效果的选择，只有缺少关键选择时形成检查点。技术效果局限于目标片段，不重新决定全站风格。若需要确认，引用实际上游文件和要求，解释它与当前已授权内容的关系。

## Oil Motion：`oil-motion`

只有 `existing-media`/`generate-media` 路线读取入口。若包内存在 `LOCAL-RUNTIME.md`，先读取其本地环境说明；没有时按实际上游要求核对。只在媒体阶段要求 Python 3.10+、其 Python 包和 FFmpeg/ffprobe，生成凭据组件还要求适用 Node 与锁定依赖。缺失时报告，不自动安装。

按本次路线逐步读 `references/delivery-selection.md`、所选格式的参考、`runtime.md`、`qa.md`。已有素材从分析开始，不要求 Key。实际生成前才读取 `api-key-setup.md` 和 `prompting.md`，并使用真实受控凭据入口；不让用户把密钥贴进聊天。

沿用四个事实源：`source/concept-contract.yaml`、`source/motion-brief.yaml`、`build/timeline.json`、`build/motion-budget.json`。本编排器的 session 只引用它们。主体/画幅/连续性/输入/时间控制/降级来自项目要求，先做 Pilot 并在真实页面验收再扩展。

## 来源与漂移

[upstreams.json](upstreams.json) 是 2026-10-10 的可共享核对记录，保存仓库、相对源路径、已确认 commit/版本依据和哈希；没有机器路径。Oil Motion 的本地入口包含上一轮安装加入的环境说明，记录本地修改和上游哈希分别保留，不能假装字节相同。

核对官方来源：[Codex Skills](https://learn.chatgpt.com/docs/build-skills)、[skill-creator](https://github.com/openai/skills/tree/main/skills/.system/skill-creator)、[Agent Skills 规范](https://agentskills.io/specification)、[Taste](https://github.com/Leonxlnx/taste-skill)、[Impeccable](https://github.com/pbakaus/impeccable)、[Oil Motion](https://github.com/oil-oil/oil-motion)。这些是来源说明，不是自动更新配置。
