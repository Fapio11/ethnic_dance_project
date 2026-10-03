from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]

NPY_PATH = (
    PROJECT_DIR
    / "data"
    / "pose_3d_est"
    / "video_001_pose_3d.npy"
)

CSV_PATH = (
    PROJECT_DIR
    / "data"
    / "pose_3d_est"
    / "video_001_pose_3d.csv"
)


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


def main():
    if not NPY_PATH.exists():
        raise FileNotFoundError(
            f"找不到3D骨架文件：{NPY_PATH}"
        )

    pose = np.load(NPY_PATH)

    print("数据形状：", pose.shape)
    print("数据类型：", pose.dtype)

    if pose.ndim != 3:
        raise ValueError(
            f"数据应有3个维度，实际为：{pose.shape}"
        )

    if pose.shape[1:] != (33, 4):
        raise ValueError(
            f"预期形状为[T, 33, 4]，"
            f"实际为：{pose.shape}"
        )

    rows = []

    for frame_id in range(pose.shape[0]):
        for joint_id in range(pose.shape[1]):
            x_world, y_world, z_world, visibility = (
                pose[frame_id, joint_id]
            )

            detected = not np.isnan(
                [
                    x_world,
                    y_world,
                    z_world,
                    visibility,
                ]
            ).all()

            rows.append(
                {
                    "frame_id": frame_id,
                    "joint_id": joint_id,
                    "joint_name": LANDMARK_NAMES[
                        joint_id
                    ],
                    "x_world": x_world,
                    "y_world": y_world,
                    "z_world": z_world,
                    "visibility": visibility,
                    "detected": detected,
                }
            )

    dataframe = pd.DataFrame(rows)

    dataframe.to_csv(
        CSV_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    valid_frames = ~np.isnan(pose).all(
        axis=(1, 2)
    )

    print()
    print("转换完成")
    print(f"总帧数：{pose.shape[0]}")
    print(f"有效帧数：{valid_frames.sum()}")
    print(f"关键点数量：{pose.shape[1]}")
    print(f"CSV文件：{CSV_PATH}")
    print()
    print("前10行：")
    print(dataframe.head(10).to_string(index=False))


if __name__ == "__main__":
    main()