# 本地姿态处理服务

该服务把网站上传动作接到现有处理链：

1. RTMPose COCO-17 二维姿态提取；
2. 遮挡插值与置信度自适应平滑；
3. MotionAGFormer H36M-17 三维姿态估计；
4. 输出二维视频、三维视频、坐标文件和动作指标。

在项目根目录启动：

```powershell
.\start_pose_service.ps1
```

默认地址为 `http://127.0.0.1:8765`。上传文件和结果保存在
`runtime/pose_jobs/<任务ID>/`，不会覆盖 `data/` 中的原始数据。

