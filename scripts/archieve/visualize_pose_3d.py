from pathlib import Path

import cv2
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1]

POSE_PATH = (
    PROJECT_DIR
    / "data"
    / "pose_3d_est"
    / "video_001_pose_3d.npy"
)

VIDEO_PATH = (
    PROJECT_DIR
    / "data"
    / "raw_videos"
    / "video_001.mp4"
)

OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "pose_visualization"
    / "video_001_pose_3d_views.mp4"
)


POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27),
    (24, 26), (26, 28),
    (27, 29), (29, 31),
    (28, 30), (30, 32),
]


PANEL_WIDTH = 400
PANEL_HEIGHT = 600


def project_point(point, view, scale):
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
        raise ValueError(f"未知视角：{view}")

    pixel_x = int(
        PANEL_WIDTH / 2
        + horizontal * scale
    )

    pixel_y = int(
        PANEL_HEIGHT / 2
        + vertical * scale
    )

    return pixel_x, pixel_y


def draw_view(
    canvas,
    points,
    visibility,
    view,
    offset_x,
    title,
    scale,
):
    cv2.rectangle(
        canvas,
        (offset_x, 0),
        (
            offset_x + PANEL_WIDTH - 1,
            PANEL_HEIGHT - 1,
        ),
        (80, 80, 80),
        1,
    )

    cv2.putText(
        canvas,
        title,
        (offset_x + 20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
    )

    projected = []

    for point in points:
        px, py = project_point(
            point,
            view,
            scale,
        )

        projected.append(
            (px + offset_x, py)
        )

    for start, end in POSE_CONNECTIONS:
        if (
            visibility[start] >= 0.5
            and visibility[end] >= 0.5
        ):
            cv2.line(
                canvas,
                projected[start],
                projected[end],
                (0, 255, 0),
                2,
            )

    for joint_id, point in enumerate(projected):
        if visibility[joint_id] >= 0.5:
            color = (0, 0, 255)

            if joint_id in [15, 16]:
                color = (255, 0, 255)

            if joint_id in [27, 28]:
                color = (255, 255, 0)

            cv2.circle(
                canvas,
                point,
                4,
                color,
                -1,
            )


def main():
    if not POSE_PATH.exists():
        raise FileNotFoundError(
            f"找不到3D坐标：{POSE_PATH}"
        )

    pose = np.load(POSE_PATH)

    if pose.shape[1:] != (33, 4):
        raise ValueError(
            f"预期形状为[T,33,4]，"
            f"实际为：{pose.shape}"
        )

    xyz = pose[:, :, :3]
    visibility = pose[:, :, 3]

    # 以左右髋中心作为每帧骨架中心
    hip_center = (
        xyz[:, 23, :]
        + xyz[:, 24, :]
    ) / 2

    centered_xyz = (
        xyz
        - hip_center[:, None, :]
    )

    coordinate_limit = float(
        np.nanmax(np.abs(centered_xyz))
    )

    scale = (
        min(PANEL_WIDTH, PANEL_HEIGHT)
        * 0.42
        / coordinate_limit
    )

    input_video = cv2.VideoCapture(
        str(VIDEO_PATH)
    )

    fps = input_video.get(
        cv2.CAP_PROP_FPS
    )

    input_video.release()

    if fps <= 0:
        fps = 25.0

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_size = (
        PANEL_WIDTH * 3,
        PANEL_HEIGHT,
    )

    writer = cv2.VideoWriter(
        str(OUTPUT_PATH),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        output_size,
    )

    if not writer.isOpened():
        raise RuntimeError(
            f"无法创建视频：{OUTPUT_PATH}"
        )

    for frame_id in range(pose.shape[0]):
        canvas = np.zeros(
            (
                PANEL_HEIGHT,
                PANEL_WIDTH * 3,
                3,
            ),
            dtype=np.uint8,
        )

        points = centered_xyz[frame_id]
        frame_visibility = visibility[frame_id]

        draw_view(
            canvas,
            points,
            frame_visibility,
            "front",
            0,
            "Front view",
            scale,
        )

        draw_view(
            canvas,
            points,
            frame_visibility,
            "side",
            PANEL_WIDTH,
            "Side view",
            scale,
        )

        draw_view(
            canvas,
            points,
            frame_visibility,
            "top",
            PANEL_WIDTH * 2,
            "Top view",
            scale,
        )

        cv2.putText(
            canvas,
            f"Frame: {frame_id}",
            (20, PANEL_HEIGHT - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

        writer.write(canvas)

    writer.release()

    print("3D骨架视频生成完成")
    print(f"帧数：{pose.shape[0]}")
    print(f"输出文件：{OUTPUT_PATH}")
    print("重点检查第54—55帧和第235—237帧")


if __name__ == "__main__":
    main()