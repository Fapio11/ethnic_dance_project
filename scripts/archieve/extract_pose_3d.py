from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1]

INPUT_VIDEO = (
    PROJECT_DIR
    / "data"
    / "raw_videos"
    / "video_001.mp4"
)

MODEL_FILE = (
    PROJECT_DIR
    / "models"
    / "pose_landmarker_full.task"
)

OUTPUT_3D = (
    PROJECT_DIR
    / "data"
    / "pose_3d_est"
    / "video_001_pose_3d.npy"
)


def main():
    if not INPUT_VIDEO.exists():
        raise FileNotFoundError(
            f"找不到视频：{INPUT_VIDEO}"
        )

    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"找不到模型：{MODEL_FILE}"
        )

    OUTPUT_3D.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    video = cv2.VideoCapture(str(INPUT_VIDEO))

    if not video.isOpened():
        raise RuntimeError(
            f"无法打开视频：{INPUT_VIDEO}"
        )

    fps = video.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        fps = 25.0

    total_frames = int(
        video.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = (
        mp.tasks.vision.PoseLandmarkerOptions
    )
    RunningMode = mp.tasks.vision.RunningMode

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path=str(MODEL_FILE)
        ),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    all_world_keypoints = []

    frame_id = 0
    detected_frames = 0

    print(f"开始提取估计3D骨架：{INPUT_VIDEO.name}")
    print(f"视频帧率：{fps:.2f}")
    print(f"视频总帧数：{total_frames}")

    with mp.tasks.vision.PoseLandmarker.create_from_options(
        options
    ) as landmarker:

        while True:
            success, frame = video.read()

            if not success:
                break

            rgb_frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb_frame,
            )

            timestamp_ms = int(
                frame_id * 1000 / fps
            )

            result = landmarker.detect_for_video(
                mp_image,
                timestamp_ms,
            )

            world_pose_list = getattr(
                result,
                "pose_world_landmarks",
                [],
            )

            if world_pose_list:
                world_landmarks = world_pose_list[0]

                frame_points = []

                for landmark in world_landmarks:
                    frame_points.append(
                        [
                            landmark.x,
                            landmark.y,
                            landmark.z,
                            getattr(
                                landmark,
                                "visibility",
                                np.nan,
                            ),
                        ]
                    )

                all_world_keypoints.append(
                    frame_points
                )

                detected_frames += 1

            else:
                all_world_keypoints.append(
                    np.full(
                        (33, 4),
                        np.nan,
                        dtype=np.float32,
                    ).tolist()
                )

            frame_id += 1

            if frame_id % 100 == 0:
                print(
                    f"已处理："
                    f"{frame_id}/{total_frames}"
                )

    video.release()

    pose_3d = np.asarray(
        all_world_keypoints,
        dtype=np.float32,
    )

    np.save(
        OUTPUT_3D,
        pose_3d,
    )

    detection_rate = (
        detected_frames / frame_id * 100
        if frame_id > 0
        else 0
    )

    print()
    print("估计3D骨架提取完成")
    print(f"实际处理帧数：{frame_id}")
    print(f"有效3D骨架帧数：{detected_frames}")
    print(f"检出率：{detection_rate:.2f}%")
    print(f"数据形状：{pose_3d.shape}")
    print(f"保存位置：{OUTPUT_3D}")

    if detected_frames > 0:
        first_valid_frame = pose_3d[
            ~np.isnan(pose_3d).all(axis=(1, 2))
        ][0]

        print()
        print("第一个有效帧的髋部关键点：")
        print("左髋23：", first_valid_frame[23])
        print("右髋24：", first_valid_frame[24])


if __name__ == "__main__":
    main()