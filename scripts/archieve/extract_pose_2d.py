from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np


# 定位项目目录
PROJECT_DIR = Path(__file__).resolve().parents[1]

INPUT_VIDEO = PROJECT_DIR / "data" / "raw_videos" / "video_001.mp4"
MODEL_FILE = PROJECT_DIR / "models" / "pose_landmarker_full.task"

OUTPUT_VIDEO = (
    PROJECT_DIR
    / "outputs"
    / "pose_visualization"
    / "video_001_pose.mp4"
)

OUTPUT_POINTS = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / "video_001_pose.npy"
)


# MediaPipe 33个关键点之间的骨架连接关系
POSE_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 7),
    (0, 4), (4, 5), (5, 6), (6, 8),
    (9, 10),
    (11, 12),
    (11, 13), (13, 15),
    (15, 17), (15, 19), (15, 21), (17, 19),
    (12, 14), (14, 16),
    (16, 18), (16, 20), (16, 22), (18, 20),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27),
    (27, 29), (29, 31), (27, 31),
    (24, 26), (26, 28),
    (28, 30), (30, 32), (28, 32),
]


def draw_pose(frame, landmarks):
    """在视频画面上绘制关键点和骨架连线。"""

    height, width = frame.shape[:2]
    pixel_points = []

    for landmark in landmarks:
        x = int(landmark.x * width)
        y = int(landmark.y * height)
        visibility = getattr(landmark, "visibility", 1.0)

        pixel_points.append((x, y, visibility))

    # 绘制骨架连线
    for start_index, end_index in POSE_CONNECTIONS:
        x1, y1, visibility1 = pixel_points[start_index]
        x2, y2, visibility2 = pixel_points[end_index]

        if visibility1 >= 0.5 and visibility2 >= 0.5:
            cv2.line(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2,
            )

    # 绘制关节点
    for x, y, visibility in pixel_points:
        if visibility >= 0.5:
            cv2.circle(
                frame,
                (x, y),
                4,
                (0, 0, 255),
                -1,
            )

    return frame


def main():
    # 检查文件
    if not INPUT_VIDEO.exists():
        raise FileNotFoundError(f"找不到输入视频：{INPUT_VIDEO}")

    if not MODEL_FILE.exists():
        raise FileNotFoundError(f"找不到模型文件：{MODEL_FILE}")

    OUTPUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_POINTS.parent.mkdir(parents=True, exist_ok=True)

    video = cv2.VideoCapture(str(INPUT_VIDEO))

    if not video.isOpened():
        raise RuntimeError(f"无法打开视频：{INPUT_VIDEO}")

    fps = video.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        fps = 25.0

    width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

    writer = cv2.VideoWriter(
        str(OUTPUT_VIDEO),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    if not writer.isOpened():
        video.release()
        raise RuntimeError(f"无法创建输出视频：{OUTPUT_VIDEO}")

    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    RunningMode = mp.tasks.vision.RunningMode

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_FILE)),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    all_keypoints = []
    frame_index = 0
    detected_frames = 0

    print(f"开始处理：{INPUT_VIDEO.name}")
    print(f"视频大小：{width} × {height}")
    print(f"帧率：{fps:.2f}")
    print(f"总帧数：{total_frames}")

    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            success, frame = video.read()

            if not success:
                break

            # OpenCV是BGR，MediaPipe需要RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb_frame,
            )

            timestamp_ms = int(frame_index * 1000 / fps)

            result = landmarker.detect_for_video(
                mp_image,
                timestamp_ms,
            )

            pose_list = getattr(result, "pose_landmarks", None)

            if pose_list is None:
                pose_list = getattr(result, "landmarks", [])

            if pose_list:
                landmarks = pose_list[0]
                frame_points = []

                for landmark in landmarks:
                    frame_points.append(
                        [
                            landmark.x,
                            landmark.y,
                            landmark.z,
                            getattr(landmark, "visibility", np.nan),
                        ]
                    )

                all_keypoints.append(frame_points)
                draw_pose(frame, landmarks)
                detected_frames += 1

            else:
                # 没检测到人体时，用NaN占位，保持帧数一致
                all_keypoints.append(
                    np.full((33, 4), np.nan).tolist()
                )

                cv2.putText(
                    frame,
                    "No pose detected",
                    (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 0, 255),
                    2,
                )

            writer.write(frame)
            frame_index += 1

            if frame_index % 100 == 0:
                print(f"已处理 {frame_index}/{total_frames} 帧")

    video.release()
    writer.release()

    keypoints_array = np.asarray(
        all_keypoints,
        dtype=np.float32,
    )

    np.save(OUTPUT_POINTS, keypoints_array)

    detection_rate = (
        detected_frames / frame_index * 100
        if frame_index > 0
        else 0
    )

    print()
    print("处理完成")
    print(f"实际处理帧数：{frame_index}")
    print(f"检测到人体的帧数：{detected_frames}")
    print(f"人体检出率：{detection_rate:.2f}%")
    print(f"骨架数据形状：{keypoints_array.shape}")
    print(f"骨架视频：{OUTPUT_VIDEO}")
    print(f"坐标文件：{OUTPUT_POINTS}")


if __name__ == "__main__":
    main()