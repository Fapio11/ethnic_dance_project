"""对RTMPose二维坐标进行遮挡处理和置信度自适应平滑。"""

from pathlib import Path

import cv2
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1]

VIDEO_ID = "video_012"

INPUT_VIDEO = (
    PROJECT_DIR
    / "data"
    / "raw_videos"
    / f"{VIDEO_ID}.mp4"
)

INPUT_POINTS = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / f"{VIDEO_ID}_rtmpose.npy"
)

OUTPUT_POINTS = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / f"{VIDEO_ID}_rtmpose_filtered.npy"
)

OUTPUT_VIDEO = (
    PROJECT_DIR
    / "outputs"
    / "pose_visualization"
    / f"{VIDEO_ID}_rtmpose_filtered.webm"
)

# 网页端使用坐标实时绘制，不生成过滤后骨架视频
WRITE_FILTERED_POSE_VIDEO = False
# 低于该阈值的点视为不可靠
MIN_CONFIDENCE = 0.30

# 只有低置信度点发生大位移时才判定为跳点
JUMP_CONFIDENCE_LIMIT = 0.55

# 单帧最大合理位移：视频对角线的8%
MAX_JUMP_RATIO = 0.08

# 不超过10帧的连续遮挡执行线性插值
MAX_SHORT_GAP = 10

# 时间平滑窗口，必须是奇数
SMOOTH_WINDOW = 7

# 骨架视频显示阈值
DRAW_CONFIDENCE = 0.15


COCO_CONNECTIONS = [
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),

    (5, 6),

    (5, 7),
    (7, 9),

    (6, 8),
    (8, 10),

    (5, 11),
    (6, 12),
    (11, 12),

    (11, 13),
    (13, 15),

    (12, 14),
    (14, 16),
]


def find_false_runs(valid_mask):
    """找出valid_mask中连续为False的区间。"""

    runs = []
    index = 0
    length = len(valid_mask)

    while index < length:
        if valid_mask[index]:
            index += 1
            continue

        start = index

        while (
            index < length
            and not valid_mask[index]
        ):
            index += 1

        end = index - 1
        runs.append((start, end))

    return runs


def reject_low_confidence_jumps(
    pose,
    frame_width,
    frame_height,
):
    """拒绝低置信度且位移异常的关节点。"""

    result = pose.copy()

    diagonal = np.hypot(
        frame_width,
        frame_height,
    )

    max_jump = (
        diagonal * MAX_JUMP_RATIO
    )

    rejected_count = 0

    for joint_id in range(17):
        for frame_id in range(
            1,
            result.shape[0],
        ):
            previous_xy = result[
                frame_id - 1,
                joint_id,
                :2,
            ]

            current_xy = result[
                frame_id,
                joint_id,
                :2,
            ]

            current_confidence = result[
                frame_id,
                joint_id,
                2,
            ]

            if (
                not np.isfinite(
                    previous_xy
                ).all()
                or not np.isfinite(
                    current_xy
                ).all()
            ):
                continue

            displacement = np.linalg.norm(
                current_xy - previous_xy
            )

            if (
                displacement > max_jump
                and current_confidence
                < JUMP_CONFIDENCE_LIMIT
            ):
                result[
                    frame_id,
                    joint_id,
                    :2,
                ] = np.nan

                result[
                    frame_id,
                    joint_id,
                    2,
                ] = 0.0

                rejected_count += 1

    return result, rejected_count


def fill_missing_points(pose):
    """短遮挡插值，长遮挡仅补模型输入并保持零置信度。"""

    result = pose.copy()
    total_frames = result.shape[0]
    frame_ids = np.arange(total_frames)

    short_gap_frames = 0
    long_gap_frames = 0

    for joint_id in range(17):
        confidence = np.nan_to_num(
            result[:, joint_id, 2],
            nan=0.0,
        )

        valid = (
            np.isfinite(
                result[:, joint_id, 0]
            )
            & np.isfinite(
                result[:, joint_id, 1]
            )
            & (
                confidence
                >= MIN_CONFIDENCE
            )
        )

        valid_ids = frame_ids[valid]

        if len(valid_ids) == 0:
            raise ValueError(
                f"关节{joint_id}在全部帧中"
                "都没有可靠坐标"
            )

        # 先保证所有坐标有限，避免MotionAGFormer收到NaN。
        for coordinate_id in (0, 1):
            values = result[
                :,
                joint_id,
                coordinate_id,
            ]

            result[
                :,
                joint_id,
                coordinate_id,
            ] = np.interp(
                frame_ids,
                valid_ids,
                values[valid],
            )

        for start, end in find_false_runs(
            valid
        ):
            gap_length = end - start + 1

            bounded = (
                start > 0
                and end < total_frames - 1
                and valid[start - 1]
                and valid[end + 1]
            )

            if (
                bounded
                and gap_length
                <= MAX_SHORT_GAP
            ):
                left_confidence = confidence[
                    start - 1
                ]

                right_confidence = confidence[
                    end + 1
                ]

                # 插值点仍保持较低置信度，
                # 防止被误认为真实检测点。
                interpolation_confidence = (
                    min(
                        left_confidence,
                        right_confidence,
                    )
                    * 0.5
                )

                result[
                    start:end + 1,
                    joint_id,
                    2,
                ] = interpolation_confidence

                short_gap_frames += gap_length

            else:
                # 长遮挡必须提供有限坐标给3D模型，
                # 但confidence保持0，表明它不可靠。
                result[
                    start:end + 1,
                    joint_id,
                    2,
                ] = 0.0

                long_gap_frames += gap_length

    return (
        result,
        short_gap_frames,
        long_gap_frames,
    )


def adaptive_smooth(pose):
    """根据当前点置信度决定平滑强度。"""

    result = pose.copy()
    original = pose.copy()

    radius = SMOOTH_WINDOW // 2
    total_frames = pose.shape[0]

    for frame_id in range(total_frames):
        start = max(
            0,
            frame_id - radius,
        )

        end = min(
            total_frames,
            frame_id + radius + 1,
        )

        local_ids = np.arange(
            start,
            end,
        )

        temporal_distance = (
            local_ids - frame_id
        )

        temporal_weights = np.exp(
            -0.5
            * (
                temporal_distance
                / max(radius, 1)
            ) ** 2
        )

        for joint_id in range(17):
            local_xy = original[
                start:end,
                joint_id,
                :2,
            ]

            local_confidence = (
                original[
                    start:end,
                    joint_id,
                    2,
                ]
            )

            weights = (
                temporal_weights
                * np.maximum(
                    local_confidence,
                    0.01,
                )
            )

            weight_sum = weights.sum()

            if weight_sum <= 1e-8:
                continue

            smoothed_xy = (
                local_xy
                * weights[:, None]
            ).sum(axis=0) / weight_sum

            current_confidence = original[
                frame_id,
                joint_id,
                2,
            ]

            # 高置信度点主要保留原始动作；
            # 低置信度点更多依赖附近帧。
            if current_confidence >= 0.70:
                smooth_strength = 0.15

            elif current_confidence >= 0.30:
                smooth_strength = 0.40

            else:
                smooth_strength = 0.80

            result[
                frame_id,
                joint_id,
                :2,
            ] = (
                (
                    1.0 - smooth_strength
                )
                * original[
                    frame_id,
                    joint_id,
                    :2,
                ]
                + smooth_strength
                * smoothed_xy
            )

    return result


def draw_pose(frame, frame_pose):
    """绘制过滤后的COCO-17骨架。"""

    points = frame_pose[:, :2]
    confidence = frame_pose[:, 2]

    for start, end in COCO_CONNECTIONS:
        if (
            confidence[start]
            < DRAW_CONFIDENCE
            or confidence[end]
            < DRAW_CONFIDENCE
        ):
            continue

        point1 = tuple(
            np.round(
                points[start]
            ).astype(int)
        )

        point2 = tuple(
            np.round(
                points[end]
            ).astype(int)
        )

        cv2.line(
            frame,
            point1,
            point2,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    for joint_id in range(17):
        if (
            confidence[joint_id]
            < DRAW_CONFIDENCE
        ):
            continue

        point = tuple(
            np.round(
                points[joint_id]
            ).astype(int)
        )

        color = (
            (0, 0, 255)
            if confidence[joint_id]
            >= MIN_CONFIDENCE
            else (0, 165, 255)
        )

        cv2.circle(
            frame,
            point,
            4,
            color,
            -1,
            cv2.LINE_AA,
        )

    return frame


def create_filtered_video(
    filtered_pose,
    fps,
    width,
    height,
):
    """生成后处理骨架视频。"""

    video = cv2.VideoCapture(
        str(INPUT_VIDEO)
    )

    if not video.isOpened():
        raise RuntimeError(
            f"无法打开视频：{INPUT_VIDEO}"
        )

    writer = cv2.VideoWriter(
        str(OUTPUT_VIDEO),
        cv2.VideoWriter_fourcc(*"VP80"),
        fps,
        (width, height),
    )

    if not writer.isOpened():
        video.release()

        raise RuntimeError(
            f"无法创建视频：{OUTPUT_VIDEO}"
        )

    frame_id = 0

    try:
        while frame_id < len(filtered_pose):
            success, frame = video.read()

            if not success:
                break

            draw_pose(
                frame,
                filtered_pose[frame_id],
            )

            writer.write(frame)
            frame_id += 1

    finally:
        video.release()
        writer.release()

    if frame_id != len(filtered_pose):
        print(
            "警告：可视化视频帧数与"
            "坐标文件帧数不一致。"
        )


def main():
    if not INPUT_VIDEO.is_file():
        raise FileNotFoundError(
            f"找不到视频：{INPUT_VIDEO}"
        )

    if not INPUT_POINTS.is_file():
        raise FileNotFoundError(
            f"找不到二维坐标：{INPUT_POINTS}"
        )
    write_video = (
            WRITE_FILTERED_POSE_VIDEO
            and OUTPUT_VIDEO is not None
    )
    pose = np.load(INPUT_POINTS)

    if (
        pose.ndim != 3
        or pose.shape[1:] != (17, 3)
    ):
        raise ValueError(
            "输入必须为[T,17,3]，"
            f"实际形状为：{pose.shape}"
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

    video.release()

    if (
        not np.isfinite(fps)
        or fps <= 0
    ):
        fps = 25.0

    original_low_confidence = int(
        (
            np.nan_to_num(
                pose[:, :, 2],
                nan=0.0,
            )
            < MIN_CONFIDENCE
        ).sum()
    )

    print(f"输入：{INPUT_POINTS}")
    print(f"形状：{pose.shape}")
    print(
        f"原始低置信度点数："
        f"{original_low_confidence}"
    )

    pose, rejected_count = (
        reject_low_confidence_jumps(
            pose,
            width,
            height,
        )
    )

    (
        pose,
        short_gap_frames,
        long_gap_frames,
    ) = fill_missing_points(pose)

    pose = adaptive_smooth(pose)

    if not np.isfinite(
        pose[:, :, :2]
    ).all():
        raise ValueError(
            "后处理结果仍包含无效二维坐标"
        )

    OUTPUT_POINTS.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if write_video:
        OUTPUT_VIDEO.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    np.save(
        OUTPUT_POINTS,
        pose.astype(np.float32),
    )

    if write_video:
        create_filtered_video(
            pose,
            fps,
            width,
            height,
        )

    print()
    print("遮挡后处理完成")
    print(f"拒绝的跳点数：{rejected_count}")
    print(
        f"短遮挡插值关节帧数："
        f"{short_gap_frames}"
    )
    print(
        f"长遮挡低可信关节帧数："
        f"{long_gap_frames}"
    )
    print(f"输出形状：{pose.shape}")
    print(f"过滤坐标：{OUTPUT_POINTS}")
    if write_video:
        print(f"过滤视频：{OUTPUT_VIDEO}")
    else:
        print("过滤视频：未生成，网页端将根据坐标实时绘制")


if __name__ == "__main__":
    main()