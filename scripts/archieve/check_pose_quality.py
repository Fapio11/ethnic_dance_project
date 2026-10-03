from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]

NPY_PATH = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / "video_001_pose.npy"
)

OUTPUT_CSV = (
    PROJECT_DIR
    / "outputs"
    / "logs"
    / "video_001_qc_frames.csv"
)


# MediaPipe关键点可见度阈值
VISIBILITY_THRESHOLD = 0.5

# 一帧至少有多少个清晰可见的关键点
MIN_VISIBLE_JOINTS = 20

# 相邻帧关键点最大允许位移
# x、y是0—1归一化坐标，因此0.15表示画面尺寸的15%
JUMP_THRESHOLD = 0.15


def main():
    if not NPY_PATH.exists():
        raise FileNotFoundError(
            f"找不到骨架数据：{NPY_PATH}"
        )

    pose = np.load(NPY_PATH)

    if pose.shape[1:] != (33, 4):
        raise ValueError(
            f"预期形状为[T, 33, 4]，"
            f"实际形状为：{pose.shape}"
        )

    total_frames = pose.shape[0]
    results = []

    previous_xy = None
    previous_visibility = None

    missing_frame_count = 0
    low_visibility_count = 0
    jump_frame_count = 0

    for frame_id in range(total_frames):
        frame = pose[frame_id]

        xy = frame[:, 0:2]
        visibility = frame[:, 3]

        frame_detected = not np.isnan(frame).all()

        if not frame_detected:
            visible_joint_count = 0
            mean_visibility = np.nan
            max_displacement = np.nan
            status = "missing"

            missing_frame_count += 1

        else:
            visible_mask = (
                np.isfinite(xy).all(axis=1)
                & np.isfinite(visibility)
                & (visibility >= VISIBILITY_THRESHOLD)
            )

            visible_joint_count = int(
                visible_mask.sum()
            )

            mean_visibility = float(
                np.nanmean(visibility)
            )

            max_displacement = np.nan

            if (
                previous_xy is not None
                and previous_visibility is not None
            ):
                previous_valid = (
                    np.isfinite(previous_xy).all(axis=1)
                    & np.isfinite(previous_visibility)
                    & (
                        previous_visibility
                        >= VISIBILITY_THRESHOLD
                    )
                )

                comparable = (
                    visible_mask
                    & previous_valid
                )

                if comparable.any():
                    displacement = np.linalg.norm(
                        xy[comparable]
                        - previous_xy[comparable],
                        axis=1,
                    )

                    max_displacement = float(
                        displacement.max()
                    )

            if visible_joint_count < MIN_VISIBLE_JOINTS:
                status = "low_visibility"
                low_visibility_count += 1

            elif (
                np.isfinite(max_displacement)
                and max_displacement > JUMP_THRESHOLD
            ):
                status = "possible_jump"
                jump_frame_count += 1

            else:
                status = "pass"

        results.append(
            {
                "frame_id": frame_id,
                "visible_joint_count": visible_joint_count,
                "mean_visibility": mean_visibility,
                "max_displacement": max_displacement,
                "status": status,
            }
        )

        if frame_detected:
            previous_xy = xy.copy()
            previous_visibility = visibility.copy()

    dataframe = pd.DataFrame(results)

    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    valid_frame_count = (
        total_frames - missing_frame_count
    )

    detection_rate = (
        valid_frame_count / total_frames * 100
        if total_frames > 0
        else 0
    )

    overall_mean_visibility = float(
        np.nanmean(pose[:, :, 3])
    )

    print("video_001骨架质量检查完成")
    print()
    print(f"总帧数：{total_frames}")
    print(f"有效检测帧数：{valid_frame_count}")
    print(f"人体检出率：{detection_rate:.2f}%")
    print(
        f"整体平均可见度："
        f"{overall_mean_visibility:.4f}"
    )
    print(f"完全缺失帧数：{missing_frame_count}")
    print(
        f"低可见度帧数："
        f"{low_visibility_count}"
    )
    print(
        f"疑似跳点帧数："
        f"{jump_frame_count}"
    )
    print()
    print(f"逐帧检查结果：{OUTPUT_CSV}")

    problem_frames = dataframe[
        dataframe["status"] != "pass"
    ]

    if problem_frames.empty:
        print("没有发现明显异常帧。")
    else:
        print()
        print("需要人工检查的帧：")
        print(
            problem_frames.to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()