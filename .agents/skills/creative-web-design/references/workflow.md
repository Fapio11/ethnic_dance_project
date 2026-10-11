# 工作流与交接

## 从请求选择流程

先理解真实请求，填写结构化意图；`scripts/workflow.py` 是确定性规划辅助，不是自然语言分类器，更不是 Skill 执行引擎。

| 请求 | 路由 | 可以省略 |
| --- | --- | --- |
| 实验性作品集，尚无方向 | `explore` → Taste → 隔离原型与方向比较 | Oil Motion；业务页面实现 |
| 已确认方向，要求制作 | `build` → 沿用方向 → 代表性片段 → 有界验收 | 重选风格与重复批准 |
| 已有业务页面局部优化 | `refine` → 现状证据 → 局部修复 | 新品牌和全套创意探索 |
| 按钮悬浮、文字揭示 | `motion` 或短 `refine` → 原生代码 | Oil Motion、视频生成 |
| 连续视角或程序化 Shader | `motion` → 现有实时路线 | 把效果转换成预渲染视频 |
| 已有角色序列帧拖动 | `motion` → Oil Motion 本地路线 | 生成服务、生成密钥 |
| 新生成角色变形，费用未授权 | 规格与分镜继续；生成 `blocked` | 付费请求、虚假生成结果 |
| 只读评审 | `review` → 证据 → 问题与建议 | 自动修复和精修命令 |
| 后端或无关文案 | 不进入本工作流 | 三个上游全部 |

`auto` 选择最短适用流程，不机械跑 A–F。`build` 的未确认方向形成检查点；明确用户授权代选时记录 `user-delegated` 及依据后推进。请求“直接实现这份已确认设计”本身就是实现授权，不重复询问。

## 阶段交接

每次交接保存：任务输入与来源、已读取 Skill 名称/入口哈希/参考文件、本阶段允许写入范围、产物相对路径、执行和验证证据、阻塞项、下个可执行动作。主代理顺序完成即可。确有隔离价值且宿主支持时才委派，指定上下文、产物和互不重叠的文件范围；不让多个代理重新决定全站风格。

检查 project 文档和视觉现状时只读；没有设计文件仍以现有实现为证据。局部任务不扩张为架构重写。`explore` 的原型仅在获准的产物目录，`review` 不修改业务代码，严格只读时也不落盘报告。

## 结构化意图示例

这是本包自定义输入，可复制到一个临时或任务记录文件；未确认的值保持未确认。

```json
{
  "mode": "motion",
  "task_kind": "animation",
  "direction": {"status": "existing", "reference": "DESIGN.md"},
  "animation": "existing-media",
  "scope": {
    "allowed_paths": ["src/companion/", "public/companion/"],
    "preserve": ["角色身份", "既有拖动输入", "接口和路由"],
    "target_devices": ["desktop"]
  },
  "authorization": {
    "implementation": true,
    "generation": {
      "status": "not-requested", "service": null, "data_scope": [],
      "max_calls": null, "max_cost": null, "currency": null,
      "stop_conditions": []
    }
  },
  "desired_enhancements": []
}
```

实际 shell 中执行 `python "SKILL_DIR/scripts/workflow.py" plan --input "intent.json"`。`SKILL_DIR` 与 `PROJECT` 在说明中表示已解析路径，不是预置环境变量。Windows 可使用 `py -3` 替换 `python`。JSON 输出只规划阶段，不能当作执行证据。

退出码：`plan` 0 为可继续的规划，2 为局部检查点/阻塞，1 为输入错误；2 不代表整个任务必须停止。`resume` 对合法的变更报告返回 0，输入或越界路径错误返回 1。

## 授权与预算

`authorization.implementation` 和 `scope.allowed_paths` 共同记录业务写入授权。探索、只读评审不因这个布尔值变成实现任务。生成 grant 还必须有服务、数据范围、正数次数或金额预算、币种（金额预算时）和停止条件，且覆盖本次数据使用/上传；与原始用户授权对照，不把代理自己填写的 JSON 当作用户授权。

按已授权服务的实际响应累计调用/费用；到预算边界、权限变化、首段内容或连续性失败时停止生成，继续不依赖它的工作。预算记录不会替代宿主审批、账户额度控制或凭据隔离；脚本也不声称能强制拦截所有外部调用。

## session 与恢复

复制 `assets/templates/session.json`，保留 `schema_version`。当前阶段写入 `current_stage`，方向引用写入 `direction.file`，决策仅保存在方向文件。`dependencies` 记录解析结果，`artifacts` 和 `checks` 记录相对产物路径、实际状态、证据及限制。

检查记录例：`{"name":"desktop-animation","status":"verified","evidence":["qa/desktop.mp4"],"notes":"实际触发、反向和取消通过"}`。未运行时用 `not-run` 并写原因，不伪造截图。

`evidence` 示例：`{"path":"src/scene.tsx","sha256":"真实文件的64位SHA256","affects_stages":["implementation","visual-qa"]}`。示例字符串不直接用于真实会话；从实际文件计算哈希。路径须在 project 内；使用相对路径，拒绝穿越和解析到项目外的符号链接。

恢复执行 `python "SKILL_DIR/scripts/workflow.py" resume --session "session.json" --project "PROJECT"`。对改变或缺失的证据使对应阶段失效，其余验证仍可保留；尚有 `blocked` 项时不得宣称整体完成。先确认方向与源素材，再继续 next_step，不从头重复全部阶段。
