# 舞迹智存：组员调试交接说明

## 已完成

- 网页前端已接入本地姿态处理服务（默认前端 `127.0.0.1:5173`、后端 `127.0.0.1:8765`）。
- 可上传舞蹈视频，按流程运行 RTMPose 二维姿态提取、遮挡修复、MotionAGFormer 三维姿态估计，并在网页展示原视频、二维 Canvas 骨架和三维结果。
- 网页 Canvas 的二维骨架已改为使用**未过滤的原始 RTMPose 输出**；过滤后的二维姿态仍用于三维估计、指标计算与动作比对。
- 舞蹈资源库改为读取 MySQL 的 `dances` 表，不再固定显示 MD-001。
- 资源库中的当前样本会同步到数字化工作台和动作分析页面。
- 动作比对不再写死原型视频：可从数据库选择任意已有二维姿态的舞蹈记录作为标准动作。
- 动作解说不再固定使用 MD-001：按当前舞蹈记录读取、编辑并保存至 `dances.narration`。
- 新增 `scripts/import_raw_videos_to_db.py`：可将 `data/raw_videos/video_001.mp4` 到 `video_021.mp4` 关联为 `MD-001` 到 `MD-021`。

## 当前待调试 / 待完成

1. **AI 动作解说生成**
   - 目前已具备“按舞蹈记录读取、编辑、保存”能力。
   - 尚未接入真实大模型或本地文本生成模型，因此没有“点击后自动生成解说”的能力。
   - 建议：新增后端生成接口；输入当前视频的动作指标、分段姿态特征和舞蹈资料；由模型返回 JSON 分段解说；调用现有 `PUT /api/dances/{dance_id}/narration` 保存。

2. **动作比对联调**
   - 在“动作分析”页面选择一条显示“可比对”的样本，再上传学习者视频。
   - 验证是否输出标准动作 ID、对齐帧数、归一化关节误差、右肩角度差等指标。
   - 若提示“标准动作尚未生成二维姿态”，需先为该条数据库记录生成或关联 `pose_2d_path`。

3. **数据库内容核验**
   - 检查每条记录的 `name`、`ethnic_group`、`region`、`description`、`review_status` 是否真实准确。
   - `metadata/samples.csv` 当前只有表头；视频元数据仍需补充后批量导入。
   - 视频路径导入后，建议逐条检查资源库中的原始视频是否可播放。

4. **历史处理结果**
   - 本次已将 Canvas 切换为未过滤二维骨架。
   - 旧任务目录中的 `pose_data.json` 仍使用旧的过滤版数据；需要重新上传处理视频，或重建对应 JSON，才能看到未过滤骨架。

## 本地启动

打开两个 PowerShell 窗口，均在项目根目录或网页目录运行。

### 后端

```powershell
cd D:\ethnic_dance_project

$env:MYSQL_HOST = "localhost"
$env:MYSQL_USER = "dance_user"
$env:MYSQL_PASSWORD = "请填写本机数据库密码"

Set-ExecutionPolicy -Scope Process Bypass
.\start_pose_service.ps1
```

### 前端

```powershell
cd D:\ethnic_dance_project\web

& "C:\Users\<用户名>\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" scripts\run-framework.mjs dev
```

浏览器访问：`http://127.0.0.1:5173`

> 每台成员电脑的 Node 路径可能不同。若已安装 Node.js 和 pnpm，可直接使用 `pnpm dev`。

## 数据库与视频导入

MySQL 数据库本身不会包含在项目压缩包中，需要组员自行安装、创建并配置数据库，或由一台电脑统一运行服务。

导入前设置数据库环境变量后，先预览：

```powershell
cd D:\ethnic_dance_project
& "D:\miniconda\envs\dance3d_clean\python.exe" scripts\import_raw_videos_to_db.py
```

确认映射后正式写入：

```powershell
& "D:\miniconda\envs\dance3d_clean\python.exe" scripts\import_raw_videos_to_db.py --apply --create-missing
```

## 不建议压缩或共享

- MySQL 密码、MySQL 数据目录和任何 `.env` 文件。
- `runtime/pose_jobs/`：这是临时上传和处理结果，体积可能较大。
- `web/node_modules/`：其他成员应自行安装依赖。
- `third_party/MotionAGFormer` 的模型权重如体积过大，可单独传输并说明放置位置。

