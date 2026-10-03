"""Batch orchestration for the local ethnic-dance pose project.

The runner deliberately reuses the project's verified scripts while replacing
their hard-coded input/output globals at runtime. It does not edit those files.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import traceback
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
DEFAULT_PROJECT = Path(r"D:\ethnic_dance_project")
DEFAULT_MODEL = "gpt-6-astra"


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def load_source_module(path: Path, module_name: str):
    loader = SourceFileLoader(module_name, str(path))
    spec = importlib.util.spec_from_loader(module_name, loader)
    if spec is None:
        raise ImportError(f"无法为脚本创建模块规范：{path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def find_project_script(project: Path, names: Iterable[str]) -> Path:
    for name in names:
        candidate = project / "scripts" / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"项目缺少脚本，候选名称：{', '.join(names)}")


def sanitize_video_id(stem: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_-")
    if not value:
        raise ValueError(f"无法从文件名生成video_id：{stem!r}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def import_video(source: Path, raw_dir: Path) -> Path:
    source = source.resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)
    destination = raw_dir / source.name
    if source == destination.resolve():
        return source
    if destination.exists():
        if source.stat().st_size == destination.stat().st_size and sha256(source) == sha256(destination):
            return destination
        raise FileExistsError(f"目标已存在且内容不同，拒绝覆盖：{destination}")
    shutil.copy2(source, destination)
    return destination


def discover_inputs(items: list[str], project: Path) -> list[Path]:
    if not items:
        items = [str(project / "data" / "raw_videos")]
    discovered: list[Path] = []
    for item in items:
        path = Path(item).expanduser().resolve()
        if path.is_file():
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError(f"不支持的视频扩展名：{path}")
            discovered.append(path)
        elif path.is_dir():
            discovered.extend(
                sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
            )
        else:
            raise FileNotFoundError(f"输入不存在：{path}")
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in discovered:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    if not unique:
        raise FileNotFoundError("没有发现可处理的视频")
    return unique


def video_metadata(path: Path) -> dict:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"无法打开视频：{path}")
    metadata = {
        "frames": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
        "fps": float(capture.get(cv2.CAP_PROP_FPS)),
        "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    capture.release()
    if metadata["fps"] <= 0 or not np.isfinite(metadata["fps"]):
        metadata["fps"] = 25.0
    metadata["duration_seconds"] = (
        metadata["frames"] / metadata["fps"] if metadata["frames"] else 0.0
    )
    return metadata


def outputs_for(project: Path, video_id: str) -> dict[str, Path]:
    return {
        "pose_2d": project / "data" / "pose_2d" / f"{video_id}_rtmpose.npy",
        "pose_2d_video": project / "outputs" / "pose_visualization" / f"{video_id}_rtmpose.mp4",
        "pose_2d_filtered": project / "data" / "pose_2d" / f"{video_id}_rtmpose_filtered.npy",
        "pose_2d_filtered_video": project / "outputs" / "pose_visualization" / f"{video_id}_rtmpose_filtered.mp4",
        "pose_3d": project / "data" / "pose_3d_est" / f"{video_id}_motionagformer.npy",
        "pose_3d_video": project / "outputs" / "pose_visualization" / f"{video_id}_motionagformer_3d.mp4",
        "caption_json": project / "data" / "captions" / f"{video_id}.json",
        "caption_md": project / "data" / "captions" / f"{video_id}.md",
        "log": project / "outputs" / "logs" / f"{video_id}_batch.log",
    }


def valid_array(path: Path, shape_tail: tuple[int, int], require_finite_xy: bool) -> bool:
    if not path.is_file():
        return False
    try:
        array = np.load(path, mmap_mode="r")
        if array.ndim != 3 or tuple(array.shape[1:]) != shape_tail or array.shape[0] == 0:
            return False
        if require_finite_xy and not np.isfinite(array[:, :, :2]).all():
            return False
        return True
    except Exception:
        return False


def run_2d(project: Path, input_video: Path, output: dict[str, Path], video_id: str):
    script = find_project_script(project, ["extract_pose_2d_rtmpose.py", "extract_pose_2d_rtmpose"])
    module = load_source_module(script, f"dance_pose2d_{video_id}")
    module.INPUT_VIDEO = input_video
    module.OUTPUT_POINTS = output["pose_2d"]
    module.OUTPUT_VIDEO = output["pose_2d_video"]
    module.WRITE_RAW_POSE_VIDEO = True
    module.main()


def run_filter(project: Path, input_video: Path, output: dict[str, Path], video_id: str):
    script = find_project_script(project, ["filter_pose_2d_occlusion.py"])
    module = load_source_module(script, f"dance_filter_{video_id}")
    module.VIDEO_ID = video_id
    module.INPUT_VIDEO = input_video
    module.INPUT_POINTS = output["pose_2d"]
    module.OUTPUT_POINTS = output["pose_2d_filtered"]
    module.OUTPUT_VIDEO = output["pose_2d_filtered_video"]
    module.WRITE_FILTERED_POSE_VIDEO = True
    module.main()


def run_3d(project: Path, input_video: Path, output: dict[str, Path], video_id: str):
    script = find_project_script(project, ["extract_pose_3d_motionagformer.py"])
    module = load_source_module(script, f"dance_pose3d_{video_id}")
    module.PROJECT_DIR = project
    module.VIDEO_ID = video_id
    module.MOTIONAGFORMER_DIR = project / "third_party" / "MotionAGFormer"
    module.CHECKPOINT_FILE = module.MOTIONAGFORMER_DIR / "checkpoint" / "motionagformer-b-h36m.pth.tr"
    module.INPUT_VIDEO = input_video
    module.INPUT_2D = output["pose_2d_filtered"]
    module.OUTPUT_3D = output["pose_3d"]
    module.OUTPUT_VIDEO = output["pose_3d_video"]
    module.WRITE_3D_POSE_VIDEO = True
    module.main()


def validate_outputs(input_video: Path, output: dict[str, Path]) -> dict:
    meta = video_metadata(input_video)
    raw = np.load(output["pose_2d"], mmap_mode="r")
    filtered = np.load(output["pose_2d_filtered"], mmap_mode="r")
    pose3d = np.load(output["pose_3d"], mmap_mode="r")
    frame_counts = [meta["frames"], len(raw), len(filtered), len(pose3d)]
    if len(set(frame_counts)) != 1:
        raise ValueError(f"帧数不一致：video/raw/filtered/3d={frame_counts}")
    if raw.shape[1:] != (17, 3) or filtered.shape[1:] != (17, 3) or pose3d.shape[1:] != (17, 3):
        raise ValueError(f"数组形状错误：raw={raw.shape}, filtered={filtered.shape}, 3d={pose3d.shape}")
    if not np.isfinite(filtered[:, :, :2]).all() or not np.isfinite(pose3d).all():
        raise ValueError("过滤二维或三维数组仍包含NaN/Inf")
    for key in ("pose_2d_video", "pose_2d_filtered_video", "pose_3d_video"):
        if not output[key].is_file() or output[key].stat().st_size == 0:
            raise ValueError(f"可视化视频缺失或为空：{output[key]}")
    confidence = np.nan_to_num(raw[:, :, 2], nan=0.0)
    return {
        **meta,
        "shape_2d": list(raw.shape),
        "shape_3d": list(pose3d.shape),
        "mean_2d_confidence": float(confidence.mean()),
        "low_confidence_ratio": float((confidence < 0.3).mean()),
        "finite_filtered_ratio": float(np.isfinite(filtered).mean()),
        "finite_3d_ratio": float(np.isfinite(pose3d).mean()),
    }


def encode_jpeg(frame: np.ndarray, quality: int = 82) -> str:
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("视频帧JPEG编码失败")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def sampled_frames(video_path: Path, count: int) -> list[tuple[float, str]]:
    meta = video_metadata(video_path)
    total = meta["frames"]
    if total <= 0:
        raise ValueError("视频没有可读取帧")
    indices = np.unique(np.linspace(0, total - 1, num=min(count, total), dtype=int))
    capture = cv2.VideoCapture(str(video_path))
    frames: list[tuple[float, str]] = []
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            timestamp = float(index / meta["fps"])
            cv2.putText(
                frame,
                f"t={timestamp:.2f}s",
                (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 0),
                4,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                f"t={timestamp:.2f}s",
                (18, 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            frames.append((timestamp, encode_jpeg(frame)))
    finally:
        capture.release()
    if not frames:
        raise RuntimeError("未能从视频抽取任何帧")
    return frames


CAPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "summary": {"type": "string"},
        "scene": {"type": "string"},
        "appearance": {"type": "string"},
        "motion_segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "description": {"type": "string"},
                    "upper_body": {"type": "string"},
                    "lower_body": {"type": "string"},
                    "torso_and_facing": {"type": "string"},
                    "tempo": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": [
                    "start_seconds", "end_seconds", "description", "upper_body",
                    "lower_body", "torso_and_facing", "tempo", "confidence"
                ],
                "additionalProperties": False,
            },
        },
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "quality_notes": {"type": "string"},
    },
    "required": [
        "video_id", "summary", "scene", "appearance", "motion_segments",
        "uncertainties", "quality_notes"
    ],
    "additionalProperties": False,
}


def caption_video(
    video_path: Path,
    video_id: str,
    output: dict[str, Path],
    validation: dict,
    model: str,
    frame_count: int,
):
    if not os.environ.get("OPENAI_API_KEY"):
        raise EnvironmentError("未设置OPENAI_API_KEY；无法生成OpenAI视觉描述")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError(
            "dance3d环境未安装openai；运行："
            r"D:\miniconda\envs\dance3d\python.exe -m pip install openai"
        ) from exc

    frames = sampled_frames(video_path, frame_count)
    timestamps = [round(item[0], 3) for item in frames]
    prompt = (
        "请根据按时间排序的抽样帧生成严格JSON。只描述可见证据。"
        "不要推断人物身份、民族、性别、具体舞种、音乐、意图或抽样帧之间不可见的动作。"
        "左右方向仅在确定时使用；遮挡、裙摆、宽袖或背身造成不确定时必须写入uncertainties。"
        "motion_segments按时间排序并覆盖可判断的动作阶段。"
        f"video_id={video_id}; duration={validation['duration_seconds']:.3f}s; "
        f"sample_timestamps={timestamps}; mean_pose_confidence={validation['mean_2d_confidence']:.4f}; "
        f"low_confidence_ratio={validation['low_confidence_ratio']:.4f}."
    )
    content = [{"type": "input_text", "text": prompt}]
    for _, encoded in frames:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{encoded}",
                "detail": "high",
            }
        )
    client = OpenAI()
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        text={
            "format": {
                "type": "json_schema",
                "name": "dance_video_annotation",
                "strict": True,
                "schema": CAPTION_SCHEMA,
            }
        },
    )
    annotation = json.loads(response.output_text)
    if annotation.get("video_id") != video_id:
        annotation["video_id"] = video_id
    output["caption_json"].parent.mkdir(parents=True, exist_ok=True)
    output["caption_json"].write_text(
        json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        f"# {video_id} 动作描述",
        "",
        f"- 总结：{annotation['summary']}",
        f"- 场景：{annotation['scene']}",
        f"- 服饰与道具：{annotation['appearance']}",
        "",
        "## 时间分段",
        "",
    ]
    for segment in annotation["motion_segments"]:
        lines.extend(
            [
                f"### {segment['start_seconds']:.2f}–{segment['end_seconds']:.2f} 秒",
                "",
                segment["description"],
                "",
                f"- 上肢：{segment['upper_body']}",
                f"- 下肢：{segment['lower_body']}",
                f"- 躯干与朝向：{segment['torso_and_facing']}",
                f"- 节奏：{segment['tempo']}",
                f"- 描述置信度：{segment['confidence']}",
                "",
            ]
        )
    lines.extend(["## 不确定性", ""])
    lines.extend(f"- {item}" for item in annotation["uncertainties"])
    lines.extend(["", "## 质量说明", "", annotation["quality_notes"], ""])
    output["caption_md"].write_text("\n".join(lines), encoding="utf-8")


def preflight(project: Path, caption: bool) -> int:
    checks = {
        "project": project.is_dir(),
        "pose2d_script": any((project / "scripts" / n).is_file() for n in ("extract_pose_2d_rtmpose.py", "extract_pose_2d_rtmpose")),
        "filter_script": (project / "scripts" / "filter_pose_2d_occlusion.py").is_file(),
        "pose3d_script": (project / "scripts" / "extract_pose_3d_motionagformer.py").is_file(),
        "motionagformer_checkpoint": (
            project / "third_party" / "MotionAGFormer" / "checkpoint" / "motionagformer-b-h36m.pth.tr"
        ).is_file(),
    }
    for name, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    print(f"[{'PASS' if os.environ.get('OPENAI_API_KEY') else 'SKIP'}] OPENAI_API_KEY")
    if caption:
        try:
            import openai  # noqa: F401
            print("[PASS] openai Python SDK")
        except ImportError:
            print("[FAIL] openai Python SDK")
            checks["openai_sdk"] = False
        checks["api_key"] = bool(os.environ.get("OPENAI_API_KEY"))
    return 0 if all(checks.values()) else 1


def append_manifest(project: Path, record: dict):
    path = project / "outputs" / "logs" / "batch_manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def process_one(
    source: Path,
    project: Path,
    force: bool,
    caption: bool,
    caption_model: str,
    caption_frames: int,
) -> dict:
    imported = import_video(source, project / "data" / "raw_videos")
    video_id = sanitize_video_id(imported.stem)
    output = outputs_for(project, video_id)
    output["log"].parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    with output["log"].open("a", encoding="utf-8") as log_stream:
        tee = Tee(sys.stdout, log_stream)
        with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
            print(f"\n===== {video_id} | {started} =====")
            if force or not (
                valid_array(output["pose_2d"], (17, 3), False)
                and output["pose_2d_video"].is_file()
            ):
                print("[1/4] RTMPose 2D")
                run_2d(project, imported, output, video_id)
            else:
                print("[1/4] 复用已验证的RTMPose 2D输出")
            if force or not (
                valid_array(output["pose_2d_filtered"], (17, 3), True)
                and output["pose_2d_filtered_video"].is_file()
            ):
                print("[2/4] 遮挡过滤与平滑")
                run_filter(project, imported, output, video_id)
            else:
                print("[2/4] 复用已验证的过滤2D输出")
            if force or not (
                valid_array(output["pose_3d"], (17, 3), True)
                and output["pose_3d_video"].is_file()
            ):
                print("[3/4] MotionAGFormer估计3D")
                run_3d(project, imported, output, video_id)
            else:
                print("[3/4] 复用已验证的估计3D输出")
            validation = validate_outputs(imported, output)
            if caption:
                if force or not output["caption_json"].is_file():
                    print(f"[4/4] OpenAI视觉描述 | model={caption_model}")
                    caption_video(
                        imported, video_id, output, validation, caption_model, caption_frames
                    )
                else:
                    print("[4/4] 复用已有文字描述")
            else:
                print("[4/4] 跳过OpenAI视觉描述")
            print(f"验证通过：2D={validation['shape_2d']} 3D={validation['shape_3d']}")
    return {
        "video_id": video_id,
        "source": str(source),
        "input_video": str(imported),
        "status": "complete",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "captioned": caption,
        "outputs": {key: str(value) for key, value in output.items()},
        "validation": validation,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="批量执行RTMPose 2D、遮挡过滤、MotionAGFormer 3D及可选视觉描述。"
    )
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--inputs", nargs="*", default=[])
    parser.add_argument("--caption", action="store_true")
    parser.add_argument(
        "--caption-model",
        default=os.environ.get("OPENAI_VISION_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument("--caption-frames", type=int, default=12)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = args.project.resolve()
    if args.caption_frames < 4 or args.caption_frames > 24:
        raise ValueError("--caption-frames必须位于4到24之间")
    if args.preflight:
        return preflight(project, args.caption)
    inputs = discover_inputs(args.inputs, project)
    failed = 0
    print(f"发现{len(inputs)}个视频；项目：{project}")
    for index, source in enumerate(inputs, start=1):
        print(f"\n[{index}/{len(inputs)}] {source}")
        try:
            record = process_one(
                source,
                project,
                args.force,
                args.caption,
                args.caption_model,
                args.caption_frames,
            )
        except Exception as exc:
            failed += 1
            record = {
                "video_id": sanitize_video_id(source.stem),
                "source": str(source),
                "status": "failed",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            print(record["traceback"], file=sys.stderr)
        append_manifest(project, record)
    print(f"\n批处理结束：成功{len(inputs) - failed}，失败{failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
