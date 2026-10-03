"""使用MotionAGFormer将RTMPose COCO-17二维骨架提升为三维骨架。"""

from pathlib import Path
import sys

import cv2
import numpy as np
import torch
import torch.nn as nn


PROJECT_DIR = Path(__file__).resolve().parents[1]
VIDEO_ID = "video_012"
_DEVICE = torch.device(
    "cuda:0" if torch.cuda.is_available() else "cpu"
)

_MODEL: nn.Module | None = None
MOTIONAGFORMER_DIR = (
    PROJECT_DIR
    / "third_party"
    / "MotionAGFormer"
)

CHECKPOINT_FILE = (
    MOTIONAGFORMER_DIR
    / "checkpoint"
    / "motionagformer-b-h36m.pth.tr"
)

INPUT_VIDEO = (
    PROJECT_DIR
    / "data"
    / "raw_videos"
    / "video_012.mp4"
)

INPUT_2D = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / f"{VIDEO_ID}_rtmpose_filtered.npy"
)

OUTPUT_3D = (
    PROJECT_DIR
    / "data"
    / "pose_3d_est"
    / "video_012_motionagformer.npy"
)

OUTPUT_VIDEO = (
    PROJECT_DIR
    / "outputs"
    / "pose_visualization"
    / "video_012_motionagformer_3d.webm"
)

NUM_FRAMES = 243
NUM_JOINTS = 17
CONFIDENCE_THRESHOLD = 0.1
# True：双次推理，结果更稳定但更慢
# False：单次推理，适合网页快速预览,记得比完赛修改一下
USE_FLIP_AUGMENTATION = False
# 网页端读取三维坐标实时绘制，不生成三维骨架视频
WRITE_3D_POSE_VIDEO = False
# Human3.6M-17关节连接关系
H36M_CONNECTIONS = [
    (0, 1),
    (1, 2),
    (2, 3),

    (0, 4),
    (4, 5),
    (5, 6),

    (0, 7),
    (7, 8),
    (8, 9),
    (9, 10),

    (8, 11),
    (11, 12),
    (12, 13),

    (8, 14),
    (14, 15),
    (15, 16),
]

LEFT_JOINTS = {
    1, 2, 3,
    14, 15, 16,
}

RIGHT_JOINTS = {
    4, 5, 6,
    11, 12, 13,
}


def check_files():
    """检查所有输入文件和MotionAGFormer目录。"""

    required_paths = [
        INPUT_VIDEO,
        INPUT_2D,
        CHECKPOINT_FILE,
        MOTIONAGFORMER_DIR,
    ]

    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(
                f"缺少文件或目录：{path}"
            )


def interpolate_missing_points(pose):
    """沿时间轴插补缺失或低置信度二维坐标。"""

    pose = pose.copy().astype(np.float32)

    total_frames = pose.shape[0]
    frame_ids = np.arange(total_frames)

    confidence = np.nan_to_num(
        pose[:, :, 2],
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    confidence = np.clip(
        confidence,
        0.0,
        1.0,
    )

    for joint_id in range(NUM_JOINTS):
        valid = (
            np.isfinite(
                pose[:, joint_id, 0]
            )
            & np.isfinite(
                pose[:, joint_id, 1]
            )
            & (
                confidence[:, joint_id]
                >= CONFIDENCE_THRESHOLD
            )
        )

        valid_count = int(valid.sum())

        if valid_count == 0:
            raise ValueError(
                f"COCO关节{joint_id}在全部帧中"
                "均没有有效坐标"
            )

        for coordinate_id in (0, 1):
            values = pose[
                :,
                joint_id,
                coordinate_id,
            ]

            pose[
                :,
                joint_id,
                coordinate_id,
            ] = np.interp(
                frame_ids,
                frame_ids[valid],
                values[valid],
            )

    pose[:, :, 2] = confidence

    return pose


def coco_to_h36m(coco):
    """将COCO-17映射为Human3.6M-17关节顺序。"""

    h36m = np.zeros_like(
        coco,
        dtype=np.float32,
    )

    # 0：髋部中心
    h36m[:, 0] = (
        coco[:, 11] + coco[:, 12]
    ) * 0.5

    # 1—3：左腿
    h36m[:, 1] = coco[:, 11]
    h36m[:, 2] = coco[:, 13]
    h36m[:, 3] = coco[:, 15]

    # 4—6：右腿
    h36m[:, 4] = coco[:, 12]
    h36m[:, 5] = coco[:, 14]
    h36m[:, 6] = coco[:, 16]

    # 8：肩部中心
    h36m[:, 8] = (
        coco[:, 5] + coco[:, 6]
    ) * 0.5

    # 7：脊柱中心
    h36m[:, 7] = (
        h36m[:, 0] + h36m[:, 8]
    ) * 0.5

    # 9：鼻子/颈部方向
    h36m[:, 9] = coco[:, 0]

    # 10：头部
    h36m[:, 10] = (
        coco[:, 1] + coco[:, 2]
    ) * 0.5

    # 11—13：右臂
    h36m[:, 11] = coco[:, 6]
    h36m[:, 12] = coco[:, 8]
    h36m[:, 13] = coco[:, 10]

    # 14—16：左臂
    h36m[:, 14] = coco[:, 5]
    h36m[:, 15] = coco[:, 7]
    h36m[:, 16] = coco[:, 9]

    return h36m


def normalize_screen_coordinates(
    pose,
    width,
    height,
):
    """按照MotionAGFormer官方方式归一化画面坐标。"""

    result = pose.copy()

    result[:, :, :2] = (
        result[:, :, :2]
        / width
        * 2.0
    )

    result[:, :, 0] -= 1.0
    result[:, :, 1] -= height / width

    return result


def flip_pose(data):
    """水平翻转并交换Human3.6M左右关节。"""

    left_joints = [
        1, 2, 3,
        14, 15, 16,
    ]

    right_joints = [
        4, 5, 6,
        11, 12, 13,
    ]

    flipped = data.clone()
    flipped[..., 0] *= -1

    source = flipped.clone()

    target_indices = (
        left_joints + right_joints
    )

    source_indices = (
        right_joints + left_joints
    )

    flipped[
        ...,
        target_indices,
        :,
    ] = source[
        ...,
        source_indices,
        :,
    ]

    return flipped


def create_model():
    """创建MotionAGFormer-Base模型。"""

    sys.path.insert(
        0,
        str(MOTIONAGFORMER_DIR),
    )

    from model.MotionAGFormer import MotionAGFormer

    model = MotionAGFormer(
        n_layers=16,
        dim_in=3,
        dim_feat=128,
        dim_rep=512,
        dim_out=3,
        mlp_ratio=4,
        act_layer=nn.GELU,
        attn_drop=0.0,
        drop=0.0,
        drop_path=0.0,
        use_layer_scale=True,
        layer_scale_init_value=0.00001,
        use_adaptive_fusion=True,
        num_heads=8,
        qkv_bias=False,
        qkv_scale=None,
        hierarchical=False,
        num_joints=17,
        use_temporal_similarity=True,
        temporal_connection_len=1,
        use_tcn=False,
        graph_only=False,
        neighbour_num=2,
        n_frames=NUM_FRAMES,
    )

    return model


def load_checkpoint(model, device):
    """加载官方预训练权重。"""

    checkpoint = torch.load(
    CHECKPOINT_FILE,
    map_location=device,
    weights_only=False,
)

    if (
        isinstance(checkpoint, dict)
        and "model" in checkpoint
    ):
        state_dict = checkpoint["model"]
    else:
        state_dict = checkpoint

    cleaned_state_dict = {}

    for key, value in state_dict.items():
        if key.startswith("module."):
            key = key[7:]

        cleaned_state_dict[key] = value

    model.load_state_dict(
        cleaned_state_dict,
        strict=True,
    )
def get_model():
    """首次调用时加载模型，后续任务复用同一模型。"""

    global _MODEL

    if _MODEL is None:
        print(f"推理设备：{_DEVICE}")
        print(f"模型权重：{CHECKPOINT_FILE}")
        print("首次加载MotionAGFormer……")

        model = create_model()
        model = model.to(_DEVICE)

        load_checkpoint(
            model,
            _DEVICE,
        )

        model.eval()
        _MODEL = model

        print("MotionAGFormer加载完成")
    else:
        print("复用已加载的MotionAGFormer模型")

    return _MODEL, _DEVICE

def pad_clip(clip):
    """将不足243帧的片段使用最后一帧补齐。"""

    original_length = clip.shape[0]

    if original_length == NUM_FRAMES:
        return clip, original_length

    pad_length = (
        NUM_FRAMES - original_length
    )

    padding = np.repeat(
        clip[-1:],
        pad_length,
        axis=0,
    )

    padded_clip = np.concatenate(
        [clip, padding],
        axis=0,
    )

    return padded_clip, original_length


@torch.inference_mode()
def infer_pose_3d(
    model,
    pose_2d,
    device,
):
    """按243帧分段执行2D到3D姿态提升。"""

    all_outputs = []

    total_frames = pose_2d.shape[0]

    for start in range(
        0,
        total_frames,
        NUM_FRAMES,
    ):
        clip = pose_2d[
            start:start + NUM_FRAMES
        ]

        clip, original_length = pad_clip(
            clip
        )

        input_tensor = torch.from_numpy(
            clip[None].astype(np.float32)
        ).to(device)

        # 第一次：使用原始二维姿态进行推理
        output_normal = model(
            input_tensor
        )

        if USE_FLIP_AUGMENTATION:
            # 第二次：水平翻转后再次推理
            flipped_input = flip_pose(
                input_tensor
            )

            output_flipped = model(
                flipped_input
            )

            # 将翻转结果恢复到原始方向
            output_flipped = flip_pose(
                output_flipped
            )

            # 对两次推理结果取平均
            output = (
                             output_normal + output_flipped
                     ) * 0.5
        else:
            # 快速模式：只进行一次推理
            output = output_normal

        # 变为髋部相对坐标
        output = (
            output
            - output[:, :, 0:1, :]
        )

        output = output[
            0,
            :original_length,
        ].cpu().numpy()

        all_outputs.append(output)

        finished = min(
            start + original_length,
            total_frames,
        )

        print(
            f"已完成3D提升："
            f"{finished}/{total_frames}帧"
        )

    pose_3d = np.concatenate(
        all_outputs,
        axis=0,
    )

    return pose_3d.astype(
        np.float32
    )


def project_point(
    point,
    view,
    scale,
    center,
):
    """把一个3D关节点投影到指定二维视图。"""

    x, y, z = point

    if view == "front":
        horizontal = x
        vertical = y

    elif view == "side":
        horizontal = z
        vertical = y

    elif view == "top":
        horizontal = x
        vertical = z

    else:
        raise ValueError(
            f"未知视角：{view}"
        )

    pixel_x = int(
        center[0] + horizontal * scale
    )

    pixel_y = int(
        center[1] + vertical * scale
    )

    return pixel_x, pixel_y


def get_bone_color(start, end):
    """根据左右肢体返回绘制颜色。"""

    if (
        start in LEFT_JOINTS
        or end in LEFT_JOINTS
    ):
        return 255, 100, 40

    if (
        start in RIGHT_JOINTS
        or end in RIGHT_JOINTS
    ):
        return 40, 80, 255

    return 80, 80, 80


def draw_pose_view(
    canvas,
    pose,
    view,
    center,
    scale,
    title,
):
    """绘制一个角度的骨架视图。"""

    cv2.putText(
        canvas,
        title,
        (
            center[0] - 85,
            45,
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (40, 40, 40),
        2,
        cv2.LINE_AA,
    )

    projected_points = [
        project_point(
            joint,
            view,
            scale,
            center,
        )
        for joint in pose
    ]

    for start, end in H36M_CONNECTIONS:
        color = get_bone_color(
            start,
            end,
        )

        cv2.line(
            canvas,
            projected_points[start],
            projected_points[end],
            color,
            3,
            cv2.LINE_AA,
        )

    for point in projected_points:
        cv2.circle(
            canvas,
            point,
            5,
            (30, 180, 30),
            -1,
            cv2.LINE_AA,
        )

    # 标出肩部方向，便于观察转圈。
    right_shoulder = projected_points[11]
    left_shoulder = projected_points[14]

    cv2.line(
        canvas,
        right_shoulder,
        left_shoulder,
        (180, 0, 180),
        4,
        cv2.LINE_AA,
    )


def estimate_shoulder_yaw(pose):
    """根据左右肩在x-z平面中的方向估计旋转角。"""

    right_shoulder = pose[11]
    left_shoulder = pose[14]

    shoulder_vector = (
        left_shoulder - right_shoulder
    )

    yaw_radians = np.arctan2(
        shoulder_vector[2],
        shoulder_vector[0],
    )

    yaw_degrees = np.degrees(
        yaw_radians
    )

    return float(yaw_degrees)


def create_visualization(
    pose_3d,
    fps,
):
    """生成正视图、侧视图和俯视图骨架视频。"""

    canvas_width = 1920
    canvas_height = 640

    writer = cv2.VideoWriter(
        str(OUTPUT_VIDEO),
        cv2.VideoWriter_fourcc(*"VP80"),
        fps,
        (
            canvas_width,
            canvas_height,
        ),
    )

    if not writer.isOpened():
        raise RuntimeError(
            f"无法创建视频：{OUTPUT_VIDEO}"
        )

    coordinate_limit = float(
        np.nanpercentile(
            np.abs(pose_3d),
            99,
        )
    )

    if not np.isfinite(
        coordinate_limit
    ):
        coordinate_limit = 1.0

    coordinate_limit = max(
        coordinate_limit,
        1e-6,
    )

    scale = (
        230.0 / coordinate_limit
    )

    total_frames = pose_3d.shape[0]

    try:
        for frame_id, pose in enumerate(
            pose_3d
        ):
            canvas = np.full(
                (
                    canvas_height,
                    canvas_width,
                    3,
                ),
                255,
                dtype=np.uint8,
            )

            # 三个视图之间的分隔线
            cv2.line(
                canvas,
                (640, 0),
                (640, canvas_height),
                (210, 210, 210),
                2,
            )

            cv2.line(
                canvas,
                (1280, 0),
                (1280, canvas_height),
                (210, 210, 210),
                2,
            )

            draw_pose_view(
                canvas,
                pose,
                view="front",
                center=(320, 350),
                scale=scale,
                title="Front view",
            )

            draw_pose_view(
                canvas,
                pose,
                view="side",
                center=(960, 350),
                scale=scale,
                title="Side view",
            )

            draw_pose_view(
                canvas,
                pose,
                view="top",
                center=(1600, 350),
                scale=scale,
                title="Top view",
            )

            yaw = estimate_shoulder_yaw(
                pose
            )

            cv2.putText(
                canvas,
                f"Estimated shoulder yaw: {yaw:.1f} deg",
                (1420, 590),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (100, 0, 100),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                canvas,
                f"Frame: {frame_id}",
                (20, 615),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (80, 80, 80),
                2,
                cv2.LINE_AA,
            )

            writer.write(canvas)

            if (frame_id + 1) % 100 == 0:
                print(
                    f"已生成3D可视化："
                    f"{frame_id + 1}/"
                    f"{total_frames}帧"
                )

    finally:
        writer.release()


def main():
    check_files()

    write_video = (
        WRITE_3D_POSE_VIDEO
        and OUTPUT_VIDEO is not None
    )

    OUTPUT_3D.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if write_video:
        OUTPUT_VIDEO.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    pose_2d = np.load(
        INPUT_2D
    )

    if (
        pose_2d.ndim != 3
        or pose_2d.shape[1:] != (17, 3)
    ):
        raise ValueError(
            "二维输入应为[T,17,3]，"
            f"实际形状为：{pose_2d.shape}"
        )

    video = cv2.VideoCapture(
        str(INPUT_VIDEO)
    )

    if not video.isOpened():
        raise RuntimeError(
            f"无法打开视频：{INPUT_VIDEO}"
        )

    width = int(
        video.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        video.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    fps = float(
        video.get(
            cv2.CAP_PROP_FPS
        )
    )

    video_frames = int(
        video.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    video.release()

    if (
        not np.isfinite(fps)
        or fps <= 0
    ):
        fps = 25.0

    print(f"输入视频：{INPUT_VIDEO}")
    print(f"二维坐标：{INPUT_2D}")
    print(f"二维形状：{pose_2d.shape}")
    print(
        f"视频尺寸：{width} × {height}"
    )
    print(f"视频帧率：{fps:.2f}")
    print(f"视频帧数：{video_frames}")

    if video_frames != pose_2d.shape[0]:
        print(
            "警告：视频帧数与二维坐标帧数不一致。"
        )

    print()
    print("正在插补缺失关键点……")

    if not np.isfinite(
    pose_2d[:, :, :2]
    ).all():
        raise ValueError(
        "过滤后的二维坐标仍包含NaN或无穷值"
    )

    print(
        "正在将COCO-17映射为"
        "Human3.6M-17……"
    )

    pose_h36m = coco_to_h36m(
        pose_2d
    )

    pose_h36m = normalize_screen_coordinates(
        pose_h36m,
        width,
        height,
    )

    model, device = get_model()

    print("开始进行2D到3D提升……")

    pose_3d = infer_pose_3d(
        model,
        pose_h36m,
        device,
    )

    np.save(
        OUTPUT_3D,
        pose_3d,
    )

    if write_video:
        print(
            "正在生成正视图、侧视图和"
            "俯视图视频……"
        )

        create_visualization(
            pose_3d,
            fps,
        )
    else:
        print(
            "跳过三维视频生成，"
            "网页端将根据三维坐标实时绘制"
        )

    print()
    print("MotionAGFormer处理完成")
    print(
        f"3D数据形状：{pose_3d.shape}"
    )
    print(f"3D坐标文件：{OUTPUT_3D}")
    if write_video:
        print(f"3D骨架视频：{OUTPUT_VIDEO}")
    else:
        print("3D骨架视频：未生成")
    print(
        "说明：该结果是单目视频估计的"
        "髋部相对3D坐标，不是真实动作捕捉坐标。"
    )


if __name__ == "__main__":
    main()