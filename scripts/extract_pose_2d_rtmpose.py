"""使用 RTMLib/RTMPose 提取 COCO-17 二维人体关键点。"""

from pathlib import Path

import cv2
import numpy as np
from rtmlib import Body, draw_skeleton


PROJECT_DIR = Path(__file__).resolve().parents[1]
_POSE_MODEL = None

# balanced：精度较高，速度较慢
# lightweight：网页预览更快
RTMPOSE_MODE = "balanced"

# 第一阶段只提取坐标，不生成无用的原始骨架视频
WRITE_RAW_POSE_VIDEO = False
INPUT_VIDEO = (
    PROJECT_DIR
    / "data"
    / "raw_videos"
    / "video_012.mp4"
)

OUTPUT_POINTS = (
    PROJECT_DIR
    / "data"
    / "pose_2d"
    / "video_012_rtmpose.npy"
)

OUTPUT_VIDEO = (
    PROJECT_DIR
    / "outputs"
    / "pose_visualization"
    / "video_012_rtmpose.webm"
)

NUM_KEYPOINTS = 17
SCORE_THRESHOLD = 0.3

def get_pose_model():
    """首次调用时加载RTMPose，后续任务复用模型。"""

    global _POSE_MODEL

    if _POSE_MODEL is None:
        print("首次加载RTMPose模型……")

        _POSE_MODEL = Body(
            mode=RTMPOSE_MODE,
            backend="onnxruntime",
            device="cpu",
            to_openpose=False,
        )

        print("RTMPose模型加载完成")
    else:
        print("复用已加载的RTMPose模型")

    return _POSE_MODEL
def select_primary_person(keypoints, scores):
    """多人出现时，选择平均置信度最高的人。"""

    keypoints = np.asarray(keypoints, dtype=np.float32)
    scores = np.asarray(scores, dtype=np.float32)

    if keypoints.size == 0 or scores.size == 0:
        return None

    if keypoints.ndim == 2:
        keypoints = keypoints[None, ...]

    if scores.ndim == 1:
        scores = scores[None, ...]

    if scores.ndim == 3 and scores.shape[-1] == 1:
        scores = scores[..., 0]

    if keypoints.shape[1:] != (NUM_KEYPOINTS, 2):
        raise ValueError(
            f"关键点形状异常：{keypoints.shape}"
        )

    if scores.shape[1:] != (NUM_KEYPOINTS,):
        raise ValueError(
            f"置信度形状异常：{scores.shape}"
        )

    person_scores = np.nanmean(scores, axis=1)
    person_index = int(np.nanargmax(person_scores))

    return (
        keypoints[person_index],
        scores[person_index],
    )


def main():
    if not INPUT_VIDEO.is_file():
        raise FileNotFoundError(
            f"找不到输入视频：{INPUT_VIDEO}"
        )

    write_video = (
        WRITE_RAW_POSE_VIDEO
        and OUTPUT_VIDEO is not None
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
    video = cv2.VideoCapture(str(INPUT_VIDEO))

    if not video.isOpened():
        raise RuntimeError(
            f"无法打开视频：{INPUT_VIDEO}"
        )

    fps = float(video.get(cv2.CAP_PROP_FPS))

    if not np.isfinite(fps) or fps <= 0:
        fps = 25.0

    width = int(
        video.get(cv2.CAP_PROP_FRAME_WIDTH)
    )

    height = int(
        video.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )

    total_frames = int(
        video.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    writer = None
    if write_video:
        writer = cv2.VideoWriter(
            str(OUTPUT_VIDEO),
            cv2.VideoWriter_fourcc(*"VP80"),
            fps,
            (width, height),
        )

        if not writer.isOpened():
            video.release()
            raise RuntimeError(
                f"无法创建骨架视频：{OUTPUT_VIDEO}"
            )
    print(f"输入视频：{INPUT_VIDEO}")
    print(f"视频尺寸：{width} × {height}")
    print(f"帧率：{fps:.2f}")
    print(f"总帧数：{total_frames}")
    print("正在加载 RTMPose 模型……")
    # Body 模型原生输出 COCO-17 关键点。
    # 当前 dance3d 环境只有 CPUExecutionProvider，
    # 因此使用 onnxruntime + cpu。
    pose_model = get_pose_model()

    all_poses = []
    detected_frames = 0
    frame_index = 0

    try:
        while True:
            success, frame = video.read()

            if not success:
                break

            keypoints, scores = pose_model(frame)

            selected = select_primary_person(
                keypoints,
                scores,
            )

            if selected is None:
                # 未检测到人体：
                # x、y 使用 NaN，confidence 使用 0。
                frame_pose = np.full(
                    (NUM_KEYPOINTS, 3),
                    np.nan,
                    dtype=np.float32,
                )

                frame_pose[:, 2] = 0.0

                if writer is not None:
                    cv2.putText(
                        frame,
                        "No pose detected",
                        (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.0,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )

            else:
                person_keypoints, person_scores = selected

                # 组合为 [17, 3]：
                # x像素坐标、y像素坐标、置信度。
                frame_pose = np.column_stack(
                    (
                        person_keypoints,
                        person_scores,
                    )
                ).astype(np.float32)

                # 只绘制选中的主要人物。
                if writer is not None:
                    draw_skeleton(
                        frame,
                        person_keypoints[None, ...],
                        person_scores[None, ...],
                        openpose_skeleton=False,
                        kpt_thr=SCORE_THRESHOLD,
                        radius=4,
                        line_width=2,
                    )

                detected_frames += 1

            all_poses.append(frame_pose)
            if writer is not None:
                writer.write(frame)

            frame_index += 1

            if frame_index % 100 == 0:
                print(
                    f"已处理 "
                    f"{frame_index}/{total_frames} 帧"
                )


    finally:
        video.release()
        if writer is not None:
            writer.release()

    if all_poses:
        pose_array = np.stack(
            all_poses,
            axis=0,
        ).astype(np.float32)
    else:
        pose_array = np.empty(
            (0, NUM_KEYPOINTS, 3),
            dtype=np.float32,
        )

    np.save(
        OUTPUT_POINTS,
        pose_array,
    )

    detection_rate = (
        detected_frames / frame_index * 100
        if frame_index > 0
        else 0.0
    )

    print()
    print("处理完成")
    print(f"实际处理帧数：{frame_index}")
    print(f"人体检出帧数：{detected_frames}")
    print(f"人体检出率：{detection_rate:.2f}%")
    print(f"骨架数据形状：{pose_array.shape}")
    print(
        "坐标格式："
        "(x_pixel, y_pixel, confidence)"
    )
    print(f"坐标文件：{OUTPUT_POINTS}")
    if write_video:
        print(f"骨架视频：{OUTPUT_VIDEO}")
    else:
        print("骨架视频：未生成，网页端将根据坐标实时绘制")


if __name__ == "__main__":
    main()