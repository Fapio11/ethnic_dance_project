from __future__ import annotations

import importlib.util
import json
import math
from functools import lru_cache
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_DIR / "scripts"

ProgressCallback = Callable[
    [str, int, str],
    None,
]


@lru_cache(maxsize=None)
def _load_script(
    name: str,
    path: Path,
):
    if not path.is_file():
        raise RuntimeError(
            f"处理脚本不存在：{path}"
        )

    loader = SourceFileLoader(
        name,
        str(path),
    )

    spec = importlib.util.spec_from_loader(
        name,
        loader,
    )

    if spec is None:
        raise RuntimeError(
            f"无法加载处理脚本：{path}"
        )

    module = importlib.util.module_from_spec(
        spec
    )

    loader.exec_module(module)

    return module


def _video_info(
    path: Path,
) -> dict:
    capture = cv2.VideoCapture(
        str(path)
    )

    if not capture.isOpened():
        raise ValueError(
            "上传文件不是可读取的视频"
        )

    try:
        fps = float(
            capture.get(
                cv2.CAP_PROP_FPS
            )
        )

        frames = int(
            capture.get(
                cv2.CAP_PROP_FRAME_COUNT
            )
        )

        width = int(
            capture.get(
                cv2.CAP_PROP_FRAME_WIDTH
            )
        )

        height = int(
            capture.get(
                cv2.CAP_PROP_FRAME_HEIGHT
            )
        )
    finally:
        capture.release()

    if (
        not math.isfinite(fps)
        or fps <= 0
    ):
        fps = 25.0

    if (
        frames <= 0
        or width <= 0
        or height <= 0
    ):
        raise ValueError(
            "视频没有可处理的有效画面"
        )

    return {
        "fps": round(fps, 3),
        "frames": frames,
        "width": width,
        "height": height,
        "duration_seconds": round(
            frames / fps,
            2,
        ),
    }


def _angles(
    points: np.ndarray,
    a: int,
    b: int,
    c: int,
) -> np.ndarray:
    ba = (
        points[:, a, :2]
        - points[:, b, :2]
    )

    bc = (
        points[:, c, :2]
        - points[:, b, :2]
    )

    denominator = (
        np.linalg.norm(
            ba,
            axis=1,
        )
        * np.linalg.norm(
            bc,
            axis=1,
        )
    )

    cosine = np.divide(
        np.sum(
            ba * bc,
            axis=1,
        ),
        denominator,
        out=np.full(
            len(points),
            np.nan,
            dtype=np.float32,
        ),
        where=denominator > 1e-6,
    )

    return np.degrees(
        np.arccos(
            np.clip(
                cosine,
                -1.0,
                1.0,
            )
        )
    )


def _downsample(
    values: np.ndarray,
    limit: int = 60,
) -> list[float | None]:
    if len(values) == 0:
        return []

    indexes = np.linspace(
        0,
        len(values) - 1,
        min(
            limit,
            len(values),
        ),
    ).astype(int)

    return [
        (
            round(
                float(values[index]),
                2,
            )
            if np.isfinite(
                values[index]
            )
            else None
        )
        for index in indexes
    ]


def _normalize_pose(
    pose: np.ndarray,
) -> np.ndarray:
    if (
        pose.ndim < 3
        or pose.shape[1] < 13
    ):
        raise ValueError(
            "姿态数据格式不正确，"
            "至少需要 13 个关节点"
        )

    xy = (
        pose[..., :2]
        .astype(np.float32)
        .copy()
    )

    center = (
        xy[:, 11]
        + xy[:, 12]
    ) * 0.5

    shoulder_width = np.linalg.norm(
        xy[:, 5] - xy[:, 6],
        axis=1,
    )

    hip_width = np.linalg.norm(
        xy[:, 11] - xy[:, 12],
        axis=1,
    )

    scale = np.maximum(
        (
            shoulder_width
            + hip_width
        )
        * 0.5,
        1.0,
    )

    return (
        xy - center[:, None, :]
    ) / scale[:, None, None]


def _compare_with_reference(
    pose: np.ndarray,
    reference_pose_path: Path | None,
    reference_id: str | None,
) -> dict | None:
    if reference_pose_path is None:
        return None

    if not reference_pose_path.is_file():
        raise FileNotFoundError(
            "标准动作二维姿态文件不存在："
            f"{reference_pose_path}"
        )

    reference = np.load(
        reference_pose_path,
        allow_pickle=False,
    )

    if (
        reference.ndim < 3
        or reference.shape[1] < 13
    ):
        raise ValueError(
            "标准动作姿态数据格式不正确"
        )

    sample_count = min(
        180,
        len(pose),
        len(reference),
    )

    if sample_count < 2:
        return None

    user_ids = np.linspace(
        0,
        len(pose) - 1,
        sample_count,
    ).astype(int)

    reference_ids = np.linspace(
        0,
        len(reference) - 1,
        sample_count,
    ).astype(int)

    user_pose = _normalize_pose(
        pose[user_ids]
    )

    reference_pose = _normalize_pose(
        reference[reference_ids]
    )

    joint_error = np.linalg.norm(
        user_pose - reference_pose,
        axis=-1,
    )

    user_angle = _angles(
        pose[user_ids],
        12,
        6,
        8,
    )

    reference_angle = _angles(
        reference[reference_ids],
        12,
        6,
        8,
    )

    mean_joint_error = float(
        np.nanmean(joint_error)
    )

    mean_angle_delta = float(
        np.nanmean(
            np.abs(
                user_angle
                - reference_angle
            )
        )
    )

    return {
        "reference_id": reference_id,
        "aligned_frames": sample_count,
        "mean_joint_error_normalized": (
            round(
                mean_joint_error,
                3,
            )
            if math.isfinite(
                mean_joint_error
            )
            else None
        ),
        "mean_right_shoulder_angle_delta": (
            round(
                mean_angle_delta,
                1,
            )
            if math.isfinite(
                mean_angle_delta
            )
            else None
        ),
        "note": (
            "基于时间归一化的观察值，"
            "不作为舞蹈水平标准分。"
        ),
    }


def _metrics(
    video: Path,
    pose_2d: Path,
    pose_3d: Path,
    reference_pose_path: Path | None = None,
    reference_id: str | None = None,
) -> dict:
    info = _video_info(video)

    pose = np.load(
        pose_2d,
        allow_pickle=False,
    )

    pose_3d_values = np.load(
        pose_3d,
        mmap_mode="r",
        allow_pickle=False,
    )

    if (
        pose.ndim < 3
        or pose.shape[-1] < 3
    ):
        raise ValueError(
            "二维姿态数据缺少置信度"
        )

    confidence = np.nan_to_num(
        pose[..., 2],
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    detected = np.any(
        confidence >= 0.3,
        axis=1,
    )

    shoulder = _angles(
        pose,
        12,
        6,
        8,
    )

    finite_shoulder = shoulder[
        np.isfinite(shoulder)
    ]

    if len(finite_shoulder) > 0:
        shoulder_mean = round(
            float(
                np.mean(
                    finite_shoulder
                )
            ),
            1,
        )

        shoulder_peak = round(
            float(
                np.max(
                    finite_shoulder
                )
            ),
            1,
        )
    else:
        shoulder_mean = None
        shoulder_peak = None

    return {
        **info,
        "detection_rate": round(
            float(
                detected.mean()
                * 100
            ),
            2,
        ),
        "mean_confidence": round(
            float(
                confidence.mean()
            ),
            4,
        ),
        "right_shoulder_angle": {
            "mean": shoulder_mean,
            "peak": shoulder_peak,
            "series": _downsample(
                shoulder
            ),
        },
        "pose_2d_shape": list(
            pose.shape
        ),
        "pose_3d_shape": list(
            pose_3d_values.shape
        ),
        "comparison": (
            _compare_with_reference(
                pose,
                reference_pose_path,
                reference_id,
            )
        ),
    }


def run_pipeline(
    input_video: Path,
    job_dir: Path,
    progress: ProgressCallback,
    reference_pose_path: Path | None = None,
    reference_id: str | None = None,
) -> dict:
    job_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    pose_2d = (
        job_dir
        / "pose_2d.npy"
    )

    pose_filtered = (
        job_dir
        / "pose_2d_filtered.npy"
    )

    pose_3d = (
        job_dir
        / "pose_3d.npy"
    )

    metrics_path = (
        job_dir
        / "metrics.json"
    )

    pose_data_path = (
        job_dir
        / "pose_data.json"
    )

    progress(
        "validating",
        3,
        "正在检查视频",
    )

    _video_info(input_video)

    progress(
        "pose_2d",
        8,
        "正在运行 RTMPose 二维姿态提取",
    )

    step_2d = _load_script(
        "dance_pose_2d",
        (
            SCRIPTS_DIR
            / "extract_pose_2d_rtmpose.py"
        ),
    )

    step_2d.INPUT_VIDEO = input_video
    step_2d.OUTPUT_POINTS = pose_2d
    step_2d.OUTPUT_VIDEO = None
    step_2d.WRITE_RAW_POSE_VIDEO = False

    step_2d.main()

    if not pose_2d.is_file():
        raise RuntimeError(
            "RTMPose 未生成二维姿态文件"
        )

    progress(
        "filtering",
        48,
        "正在修复遮挡与低置信度跳点",
    )

    filtering = _load_script(
        "dance_pose_filter",
        (
            SCRIPTS_DIR
            / "filter_pose_2d_occlusion.py"
        ),
    )

    filtering.INPUT_VIDEO = input_video
    filtering.INPUT_POINTS = pose_2d
    filtering.OUTPUT_POINTS = (
        pose_filtered
    )
    filtering.OUTPUT_VIDEO = None
    filtering.WRITE_FILTERED_POSE_VIDEO = (
        False
    )

    filtering.main()

    if not pose_filtered.is_file():
        raise RuntimeError(
            "遮挡修复未生成二维姿态文件"
        )

    progress(
        "pose_3d",
        66,
        "正在运行 MotionAGFormer "
        "三维姿态估计",
    )

    step_3d = _load_script(
        "dance_pose_3d",
        (
            SCRIPTS_DIR
            / "extract_pose_3d_motionagformer.py"
        ),
    )

    step_3d.INPUT_VIDEO = input_video
    step_3d.INPUT_2D = pose_filtered
    step_3d.OUTPUT_3D = pose_3d
    step_3d.OUTPUT_VIDEO = None
    step_3d.WRITE_3D_POSE_VIDEO = False

    step_3d.main()

    if not pose_3d.is_file():
        raise RuntimeError(
            "MotionAGFormer "
            "未生成三维姿态文件"
        )

    progress(
        "summarizing",
        92,
        "正在计算动作指标",
    )

    metrics = _metrics(
        input_video,
        pose_filtered,
        pose_3d,
        reference_pose_path=(
            reference_pose_path
        ),
        reference_id=reference_id,
    )

    metrics_path.write_text(
        json.dumps(
            metrics,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    progress(
        "serializing",
        96,
        "正在准备网页姿态数据",
    )

    # 网页 Canvas 展示 RTMPose 的原始二维输出。
    # 过滤版仍用于三维估计、指标计算和标准动作比对。
    pose_2d_values = np.load(
        pose_2d,
        allow_pickle=False,
    ).astype(np.float32)

    pose_3d_values = np.load(
        pose_3d,
        allow_pickle=False,
    ).astype(np.float32)

    pose_2d_values = np.nan_to_num(
        pose_2d_values,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    pose_3d_values = np.nan_to_num(
        pose_3d_values,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    available_frames = min(
        len(pose_2d_values),
        len(pose_3d_values),
    )

    if available_frames <= 0:
        raise RuntimeError(
            "姿态结果中没有有效帧"
        )

    pose_2d_values = (
        pose_2d_values[
            :available_frames
        ]
    )

    pose_3d_values = (
        pose_3d_values[
            :available_frames
        ]
    )

    pose_data = {
        "fps": metrics["fps"],
        "frames": available_frames,
        "width": metrics["width"],
        "height": metrics["height"],
        "pose_2d": (
            pose_2d_values
            .round(4)
            .tolist()
        ),
        "pose_3d": (
            pose_3d_values
            .round(5)
            .tolist()
        ),
    }

    pose_data_path.write_text(
        json.dumps(
            pose_data,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    return {
        "metrics": metrics,
        "artifacts": {
            "input": input_video.name,
            "pose_data": (
                pose_data_path.name
            ),
            "pose_2d_data": (
                pose_filtered.name
            ),
            "pose_3d_data": (
                pose_3d.name
            ),
            "metrics": (
                metrics_path.name
            ),
        },
    }
