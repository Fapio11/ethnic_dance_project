# 安装、使用和更新

## 项目级发现

将完整 `creative-web-design` 文件夹放入项目 `.agents/skills/`。Codex 从当前项目目录向仓库根发现该位置的 Skill；不需要新增全局配置、hooks、数据库或后台服务。此首版 metadata 设置 `allow_implicit_invocation: false`，只在用户显式提及时加载。

创建日期 2026-10-10。已在 macOS 创建并将验证结果保存在独立开发目录；Windows 的步骤为兼容说明，不能据此声称 Windows 已通过。两个系统各自安装，不会自动同步。发现未刷新时按 [官方说明](https://learn.chatgpt.com/docs/build-skills) 重启 Codex。

## macOS

在项目内使用已有 Python 3.9+ 运行本包标准库检查，带空格/中文路径必须加引号：

```text
python3 ".agents/skills/creative-web-design/scripts/validate.py"
python3 ".agents/skills/creative-web-design/scripts/doctor.py" --project "."
```

运行上游媒体脚本仍需其更高的 Python/媒体要求，不能因为本包检查能用 3.9 就认定 Oil Motion 可用。上游若自带本地环境说明，按其真实路径执行。

## Windows（说明，未实际验证）

把完整文件夹复制至项目 `.agents/skills/creative-web-design`；PowerShell 可用：

```powershell
py -3 ".agents/skills/creative-web-design/scripts/validate.py"
py -3 ".agents/skills/creative-web-design/scripts/doctor.py" --project "."
```

没有 Python launcher 时用实际 Python 可执行文件。脚本使用 pathlib/标准库，不需要 bash、管理员权限或固定盘符。Impeccable 的真实 launcher 应选择 `.cmd`；视频依赖及凭据后端按 Oil Motion 的真实跨平台说明，当前上游部分平台仍需实机验证。

## 可选用户级安装

本次交付只创建项目级 Skill。若另行授权用户级安装，可以使用以下跨平台 Python 复制例；在所需 Python shell 中执行，先替换源路径，目标已存在时会失败而不会覆盖：

```python
from pathlib import Path
import shutil
source = Path("path/to/project/.agents/skills/creative-web-design").resolve()
destination = Path.home() / ".agents" / "skills" / "creative-web-design"
destination.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, destination)
```

不要同时保留两个不同路径的同名安装并假设会合并。采用用户级副本时重新检查宿主发现结果和上游目录；当前环境兼容的 `.codex/skills` 也可能被扫描，但不能假设所有宿主只有这个旧路径。

## 更新

只更新这个包；上游保持独立，不自动升级。目标存在时先比较差异、备份或保存补丁，保留用户修改，用可回滚增量更新。重跑 doctor，若哈希漂移检查新版入口/参考再更新本包适配与 shareable 核对记录；不能只修改哈希掩盖行为变化。重新运行静态检查与相关测试，再确认发现结果。模板 schema 改变时明确迁移旧会话，不能丢掉授权和方向来源。

## 对话示例

```text
$creative-web-design mode=explore
为我的作品集探索三个空间结构或交互叙事不同的方向。
给出可预览比较，在隔离产物目录工作，不修改正式页面。
```

```text
$creative-web-design mode=build
按已确认的舞谱方向实现首屏和一个转场，沿用现有框架与业务接口。
优先现有代码路线，不调用素材生成服务。
```

```text
$creative-web-design mode=motion
把现有角色序列帧接到拖动输入，保留角色身份与静态降级。
只修改角色展示模块，不重新生成素材或重做整站。
```

```text
$creative-web-design mode=review
只读检查现有页面的实际可用性和动效，保留拼贴构图。
给出带证据的问题，不修改业务文件。
```

`refine` 可要求保留身份并修复指定可读性/加载/反馈问题；`auto` 用于让主代理选择最短流程。以上文本是对话请求，不能粘贴到 shell 当命令。

## 验证覆盖

`scripts/validate.py` 检查自定义包结构、元数据、内部引用、routes/manifest/session 数据约定；不能证明审美或浏览器行为。可显式传入真实 `--official-validator PATH`，它与本包检查分开记录；官方 quick_validate 依赖 PyYAML，缺少时报告 not-run，不静默安装。

开发测试位于 `.agents/skill-development/creative-web-design/`，不随生产 Skill 当作另一套技能发现。执行 `python3 -m unittest discover -s ".agents/skill-development/creative-web-design" -p "test_*.py" -v`。测试使用本地最小 fixture，不产生生成服务费用。真实原生激活、独立文件读取演练、mock 路由和浏览器/操作系统验证分别报告。
