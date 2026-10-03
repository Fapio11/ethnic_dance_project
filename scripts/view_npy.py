from pathlib import Path

import cv2
import numpy as np
import pandas as pd


# 项目路径
PROJECT_DIR = Path(__file__).resolve().parents[1]

NPY_PATH = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / "video_001_pose.npy"
)

VIDEO_PATH = (
    PROJECT_DIR
    / "data"
    / "raw_videos"
    / "video_001.mp4"
)

CSV_PATH = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / "video_001_pose.csv"
)


# MediaPipe Pose的33个关键点名称
LANDMARK_NAMES = [
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
]


def get_video_info(video_path):
    """读取原视频的宽度、高度和帧率。"""

    video = cv2.VideoCapture(str(video_path))

    if not video.isOpened():
        raise RuntimeError(f"无法打开原视频：{video_path}")

    width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(video.get(cv2.CAP_PROP_FPS))

    video.release()

    if fps <= 0:
        fps = 25.0

    return width, height, fps


def main():
    if not NPY_PATH.exists():
        raise FileNotFoundError(f"找不到NPY文件：{NPY_PATH}")

    if not VIDEO_PATH.exists():
        raise FileNotFoundError(f"找不到原始视频：{VIDEO_PATH}")

    pose = np.load(NPY_PATH)

    print("数据文件：", NPY_PATH)
    print("数据形状：", pose.shape)
    print("数据类型：", pose.dtype)

    # 当前项目要求的数据必须是：
    # [帧数, 33个关键点, 4个数值]
    if pose.ndim != 3:
        raise ValueError(
            f"数据应当有3个维度，实际形状为：{pose.shape}"
        )

    if pose.shape[1] != 33:
        raise ValueError(
            f"应当包含33个MediaPipe关键点，"
            f"实际为：{pose.shape[1]}"
        )

    if pose.shape[2] != 4:
        raise ValueError(
            f"每个关键点应包含x、y、z、visibility四个值，"
            f"实际为：{pose.shape[2]}"
        )

    width, height, fps = get_video_info(VIDEO_PATH)

    print("视频宽度：", width)
    print("视频高度：", height)
    print("视频帧率：", fps)

    rows = []

    for frame_id in range(pose.shape[0]):
        time_seconds = frame_id / fps

        for joint_id in range(pose.shape[1]):
            x_norm, y_norm, z_relative, visibility = (
                pose[frame_id, joint_id]
            )

            # 没有检测到人体的帧使用NaN保存
            detected = not np.isnan(
                [x_norm, y_norm, z_relative, visibility]
            ).all()

            if detected:
                x_pixel = x_norm * width
                y_pixel = y_norm * height
            else:
                x_pixel = np.nan
                y_pixel = np.nan

            rows.append(
                {
                    "frame_id": frame_id,
                    "time_seconds": time_seconds,
                    "joint_id": joint_id,
                    "joint_name": LANDMARK_NAMES[joint_id],
                    "x_norm": x_norm,
                    "y_norm": y_norm,
                    "x_pixel": x_pixel,
                    "y_pixel": y_pixel,
                    "z_relative": z_relative,
                    "visibility": visibility,
                    "detected": detected,
                }
            )

    dataframe = pd.DataFrame(rows)

    CSV_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe.to_csv(
        CSV_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    # 统计有效帧
    valid_frames = ~np.isnan(pose).all(axis=(1, 2))
    valid_frame_count = int(valid_frames.sum())
    total_frame_count = int(pose.shape[0])

    detection_rate = (
        valid_frame_count / total_frame_count * 100
        if total_frame_count > 0
        else 0
    )

    mean_visibility = float(
        np.nanmean(pose[:, :, 3])
    )

    print()
    print("转换完成")
    print(f"总帧数：{total_frame_count}")
    print(f"有效骨架帧数：{valid_frame_count}")
    print(f"人体检出率：{detection_rate:.2f}%")
    print(f"平均可见度：{mean_visibility:.4f}")
    print(f"CSV文件：{CSV_PATH}")

    print()
    print("前10行数据：")
    print(dataframe.head(10).to_string(index=False))


if __name__ == "__main__":
    main()