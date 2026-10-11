---
name: creative-web-design
description: "编排实验性作品集、艺术展览、绘本叙事和主题交互网页的创意探索、既定方向实现、局部动效与只读评审。按阶段适配独立安装的 Taste、Impeccable 和 Oil Motion，保存方向与交接证据；不用于纯后端或无关文案任务。"
metadata:
  version: "1.0.0"
---

# Creative Web Design

让一个清晰的创意从探索保留到实际网页。由主代理顺序编排，按需要读取真实的上游 Skill；本包不合并它们的全文，也不自动安装、更新或调度后台代理。

## 调用与范围

显式调用 `$creative-web-design mode=auto`。`mode=...` 是本 Skill 的对话参数约定，不是 Codex CLI 参数。

| 模式 | 本次结果 | 业务页面写入 |
| --- | --- | --- |
| `explore` | 参考研究、可比较的方向和隔离的局部原型 | 不写入 |
| `build` | 按明确方向实现代表性片段，再扩展 | 仅授权范围 |
| `refine` | 保留身份与功能，解决指定问题 | 仅授权范围 |
| `motion` | 完成明确指定的动画 | 仅动画范围 |
| `review` | 只读问题、证据和建议 | 不写入 |
| `auto` | 从真实请求选择以上流程 | 继承所选模式 |

修按钮、修溢出时走短流程，不启动完整艺术方向探索。纯后端、数据库、接口或无关文案任务返回普通任务处理，不加载三件套。已有方向不强制重新选择；没有 `DESIGN.md` 不代表可以重做旧项目。

## 主流程

1. **界定本次工作。** 读取项目约定、当前实现与已有设计证据，记录允许修改的页面、文件、目标设备，以及必须保留的框架、接口、模块、数据流程和角色身份。已有授权直接沿用。
2. **解析所需依赖。** 按 [integrations.md](references/integrations.md) 用只读的 `scripts/doctor.py` 定位真实入口和哈希。仅检查本次需要的阶段；缺失或同名歧义只阻塞相关步骤。不要自动下载、修改全局配置或启用 hooks。
3. **选择短流程或创意流程。** 按 [workflow.md](references/workflow.md) 路由。可以将人工理解的任务写成结构化 intent，运行 `scripts/workflow.py plan --input intent.json` 检查确定性分流；该脚本不会理解自然语言、调用 Skill 或执行计划。
4. **建立或沿用艺术方向。** 方向需要探索时读取 Taste 入口，遵循它的项目判断；依据 [creative-direction.md](references/creative-direction.md) 给出实质不同的方向并提供可查看证据。已有明确方向直接沿用。把确认状态和创意保留项记录在方向文件中。
5. **按选择的路线落地。** 原生代码处理字体、容器、遮罩与微交互；确有空间或程序化变化才使用实时 3D/Shader；素材自身发生语义变化或已有媒体需要交互控制时才读取 Oil Motion。每个属性或播放进度只有一个控制者，优先现有技术栈。
6. **实施代表性片段。** 实现任务先做一个足以验证方向的片段。得到真实浏览器证据后再扩展；`explore` 在方向交付后停止，`review` 只报告。保留可操作的文字、导航、表单和反馈，不把它们烘焙进图片或视频。
7. **按需验收与交接。** 使用 Impeccable 的真实对应参考，按 [quality-gates.md](references/quality-gates.md) 集中检查、批量修复、一次确认复查。交付前逐项将“已执行/通过”的断言核对到本次实际工具返回；文档中提及命令、context 的数组或计划均不能充当检查结果。缺少对应返回就写 `not-run`。无法查看浏览器时记录 `not-run`，不将构建成功等同于视觉通过。

阶段可以跳过。一次性只读取当前阶段需要的资料；已读的指令会留在上下文中，不能宣称已卸载。

## 职责路由

| 当前需要 | 主责 | 边界 |
| --- | --- | --- |
| 核心概念、艺术方向、构图和页面节奏 | Taste `design-taste-frontend` | 通用 v2；不默认替换为 `gpt-taste`，不改上游参数 |
| 旧页现状审查、局部增强、质量检查与精修 | Impeccable `impeccable` | 对应版本的具体参考；不重新决定全站风格 |
| 已有视频/序列帧处理，或素材驱动的语义动画 | Oil Motion `oil-motion` | 遵循它的合同、计划、预算、时间轴和运行时约定 |
| 范围、路由、依赖、方向锁定、授权与证据 | 本 Skill | 记录与编排，不充当安全沙箱或自动审美评分器 |

Impeccable 的 `animate`、`delight`、`overdrive` 只针对明确的局部任务。Overdrive 不是默认开关；沿用现有已确认方向与授权，并遵守实际版本需要的方向选择要求。`quieter`、`distill` 不自动用于抹平用户确认的拼贴、粗野或像素表达。

## 创意和授权约束

遵守宿主指令层级和权限；项目内依次以当前用户要求与硬约束、明确锁定的艺术方向、当前阶段任务、上游通用建议仲裁。艺术方向不能扩大权限。

先确定值得体验的概念，再选技术。创意展示可从任务级 `DESIGN_VARIANCE=8 / MOTION_INTENSITY=7 / VISUAL_DENSITY=3` 推导，数值只是软建议，不修改 Taste 文件，不强制引入动画库或生成素材。

精修应区分有意表达与真实缺陷，优先保留创意机制地修复操作、可读性和性能。确实冲突时给出证据与替代方案，不能悄悄把作品改成常规 SaaS。

默认不调用外部生成 API。费用或素材上传的授权须绑定服务、使用数据、调用次数或金额预算、停止条件；已存在的对应授权直接复用。未授权的生成标记 `blocked`，继续分镜、规格和本地可做部分。密钥不进入对话、日志、模板、Git 或交付物，使用上游真实凭据入口。

## 状态与恢复

按项目现有产物约定保存；没有约定时使用 `.creative-web-design/{run-id}/`。复制 [brief.md](assets/templates/brief.md)、[art-direction.md](assets/templates/art-direction.md)、[session.json](assets/templates/session.json) 作为任务记录。严格只读请求若不授权写报告，则在对话中返回状态。

状态只引用产品和艺术决策，不复制多份事实源。已有 `PRODUCT.md`、`DESIGN.md` 增量处理；Oil Motion 的四个事实源继续归它维护。

使用 `planned / read / executed / verified / skipped / blocked / not-run` 区分证据。读取入口不是执行，执行不是验证。阶段交接记录输入、已读入口与哈希、允许修改范围、输出、验证与未解决项。

恢复前运行 `scripts/workflow.py resume --session session.json --project PROJECT`，对比项目相对路径的证据哈希；只重做受影响的阶段。该脚本只读，不会自动更改状态或重跑业务。

`references/upstreams.json`、`references/routes.json` 和任务 `session.json` 均为本 Skill 自定义数据，不是 Codex 原生配置或子 Skill 自动安装机制。机器路径只能进入本地诊断记录；可共享清单保存来源、相对入口和哈希。

## 安装和验证

跨平台发现、更新、使用示例与各层验证边界见 [installation.md](references/installation.md)。包自身可用标准库运行 `scripts/validate.py`；它的检查是自定义静态检查，官方 `quick_validate.py` 的结果另行记录。

可共享来源核对见 [upstreams.json](references/upstreams.json)，确定性模式枚举见 [routes.json](references/routes.json)。不将子 Skill 伪装为 `dependencies.tools` 的 MCP。
