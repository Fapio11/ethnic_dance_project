from __future__ import annotations

import json
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .database import (
    get_all_dances,
    get_dance,
    save_narration,
    update_pose_results,
)
from .pipeline import PROJECT_DIR, run_pipeline


JOBS_ROOT = PROJECT_DIR / "runtime" / "pose_jobs"

MAX_UPLOAD_BYTES = 300 * 1024 * 1024

ALLOWED_SUFFIXES = {
    ".mp4",
    ".mov",
    ".webm",
    ".avi",
    ".mkv",
}

JOBS: dict[str, dict] = {}

LOCK = threading.Lock()

EXECUTOR = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="pose-pipeline",
)


app = FastAPI(
    title="舞迹智存姿态处理服务",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        (
            "https://dance-heritage-lab."
            "black-genet-9783.chatgpt.site"
        ),
    ],
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "OPTIONS",
    ],
    allow_headers=["*"],
)


@app.middleware("http")
async def private_network_access(
    request: Request,
    call_next,
):
    response = await call_next(request)

    if (
        request.headers.get(
            "access-control-request-private-network"
        )
        == "true"
    ):
        response.headers[
            "Access-Control-Allow-Private-Network"
        ] = "true"

    response.headers["Cache-Control"] = "no-store"

    return response


def _now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _normalize_dance_id(
    value: str,
) -> str:
    value = (
        value
        .strip()
        .upper()
        .replace("_", "-")
    )

    if (
        value.startswith("MD")
        and "-" not in value
    ):
        number = value[2:]
        value = f"MD-{number}"

    return value


class NarrationPayload(BaseModel):
    narration: str


def _public_url(
    request: Request,
    value: str | None,
) -> str | None:
    if not value:
        return None

    if value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return value

    # Windows 本地路径不能直接返回给浏览器。
    if (
        len(value) >= 2
        and value[1] == ":"
    ):
        return None

    if not value.startswith("/"):
        value = f"/{value}"

    backend_origin = str(
        request.base_url
    ).rstrip("/")

    return f"{backend_origin}{value}"


def _resolve_project_path(
    value: str,
) -> Path:
    path = Path(value)

    if not path.is_absolute():
        path = PROJECT_DIR / path

    return path.resolve()


def _status_path(
    job_id: str,
) -> Path:
    return (
        JOBS_ROOT
        / job_id
        / "status.json"
    )


def _save(
    job_id: str,
    **changes,
) -> dict:
    with LOCK:
        state = JOBS.setdefault(
            job_id,
            {"id": job_id},
        )

        state.update(
            changes,
            updated_at=_now(),
        )

        snapshot = dict(state)

    path = _status_path(job_id)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)

    return snapshot


def _load(
    job_id: str,
) -> dict:
    with LOCK:
        if job_id in JOBS:
            return dict(
                JOBS[job_id]
            )

    path = _status_path(job_id)

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="处理任务不存在",
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def _process(
    job_id: str,
    input_path: Path,
    dance_id: str | None = None,
    save_to_dataset: bool = False,
    reference_pose_path: Path | None = None,
) -> None:
    def progress(
        stage: str,
        percent: int,
        message: str,
    ) -> None:
        _save(
            job_id,
            status="processing",
            stage=stage,
            progress=percent,
            message=message,
        )

    try:
        result = run_pipeline(
            input_path,
            input_path.parent,
            progress,
            reference_pose_path=(
                reference_pose_path
            ),
            reference_id=(
                dance_id
                if reference_pose_path
                is not None
                else None
            ),
        )

        database_warning = None

        if (
            dance_id
            and save_to_dataset
        ):
            try:
                artifacts = result.get(
                    "artifacts",
                    {},
                )

                input_file = artifacts.get(
                    "input"
                )

                pose_data_file = artifacts.get(
                    "pose_data"
                )

                pose_2d_file = artifacts.get(
                    "pose_2d_data"
                )

                pose_3d_file = artifacts.get(
                    "pose_3d_data"
                )

                metrics_file = artifacts.get(
                    "metrics"
                )

                def artifact_url(
                    filename: str | None,
                ) -> str | None:
                    if not filename:
                        return None

                    return (
                        f"/api/jobs/{job_id}/"
                        f"artifacts/{filename}"
                    )

                def local_job_path(
                    filename: str | None,
                ) -> str | None:
                    if not filename:
                        return None

                    relative_path = (
                        Path("runtime")
                        / "pose_jobs"
                        / job_id
                        / filename
                    )

                    return (
                        relative_path
                        .as_posix()
                    )

                update_pose_results(
                    dance_id=dance_id,
                    video_url=artifact_url(
                        input_file
                    ),
                    pose_data_url=artifact_url(
                        pose_data_file
                    ),
                    pose_2d_path=local_job_path(
                        pose_2d_file
                    ),
                    pose_3d_path=local_job_path(
                        pose_3d_file
                    ),
                    analysis_path=local_job_path(
                        metrics_file
                    ),
                )

            except Exception as error:
                database_warning = str(
                    error
                )

        _save(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            message="姿态处理完成",
            dance_id=dance_id,
            save_to_dataset=(
                save_to_dataset
            ),
            compare_with_reference=(
                reference_pose_path
                is not None
            ),
            database_warning=(
                database_warning
            ),
            **result,
        )

    except Exception as error:
        _save(
            job_id,
            status="failed",
            stage="failed",
            progress=0,
            message=(
                str(error)
                or error.__class__.__name__
            ),
            dance_id=dance_id,
            save_to_dataset=(
                save_to_dataset
            ),
            compare_with_reference=(
                reference_pose_path
                is not None
            ),
        )


@app.get("/api/health")
def health():
    checkpoint = (
        PROJECT_DIR
        / "third_party"
        / "MotionAGFormer"
        / "checkpoint"
        / "motionagformer-b-h36m.pth.tr"
    )

    return {
        "status": "ok",
        "pipeline": (
            "RTMPose → occlusion filter "
            "→ MotionAGFormer"
        ),
        "checkpoint_ready": (
            checkpoint.is_file()
        ),
    }


@app.get("/api/dances")
def list_dances(
    request: Request,
):
    records = get_all_dances()

    status_text = {
        "pending": "待核验",
        "verified": "已核验",
        "rejected": "需修正",
    }

    for record in records:
        record[
            "review_status_text"
        ] = status_text.get(
            record.get(
                "review_status"
            ),
            "待核验",
        )

        # 只转换浏览器需要访问的 URL。
        for field in (
            "video_url",
            "pose_data_url",
            "analysis_url",
        ):
            record[field] = _public_url(
                request,
                record.get(field),
            )

        record["has_pose_2d"] = bool(
            record.get("pose_2d_path")
        )
        record["has_video"] = bool(
            record.get("video_url")
            or record.get("video_path")
        )

        for private_field in (
            "video_path",
            "pose_2d_path",
            "pose_3d_path",
            "analysis_path",
        ):
            record.pop(private_field, None)

    return records


@app.get("/api/dances/{dance_id}")
def dance_detail(
    dance_id: str,
    request: Request,
):
    dance_id = _normalize_dance_id(
        dance_id
    )

    record = get_dance(
        dance_id
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "找不到舞蹈记录："
                f"{dance_id}"
            ),
        )

    status_text = {
        "pending": "待核验",
        "verified": "已核验",
        "rejected": "需修正",
    }

    record[
        "review_status_text"
    ] = status_text.get(
        record.get(
            "review_status"
        ),
        "待核验",
    )

    for field in (
        "video_url",
        "pose_data_url",
        "analysis_url",
    ):
        record[field] = _public_url(
            request,
            record.get(field),
        )

    # 不向前端泄露服务器本地路径。
    record.pop(
        "video_path",
        None,
    )

    record.pop(
        "pose_2d_path",
        None,
    )

    record.pop(
        "pose_3d_path",
        None,
    )

    record.pop(
        "analysis_path",
        None,
    )

    return record


@app.get("/api/dances/{dance_id}/video")
def get_dance_video(
    dance_id: str,
):
    dance_id = _normalize_dance_id(
        dance_id
    )
    record = get_dance(dance_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="舞蹈记录不存在",
        )

    video_url = record.get("video_url")

    if video_url and video_url.startswith(
        ("/", "http://", "https://")
    ):
        # 数据库中保存的是本服务的任务产物 URL。
        from fastapi.responses import RedirectResponse

        return RedirectResponse(video_url)

    video_path_value = (
        record.get("video_path")
        or video_url
    )

    if not video_path_value:
        raise HTTPException(
            status_code=404,
            detail="该舞蹈记录尚未关联原始视频",
        )

    video_path = _resolve_project_path(
        str(video_path_value)
    )

    if not video_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="原始视频文件不存在",
        )

    media_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
    }

    return FileResponse(
        video_path,
        media_type=media_types.get(
            video_path.suffix.lower(),
            "application/octet-stream",
        ),
        filename=None,
    )


@app.put("/api/dances/{dance_id}/narration")
def update_dance_narration(
    dance_id: str,
    payload: NarrationPayload,
):
    dance_id = _normalize_dance_id(
        dance_id
    )

    if get_dance(dance_id) is None:
        raise HTTPException(
            status_code=404,
            detail="舞蹈记录不存在",
        )

    save_narration(
        dance_id,
        payload.narration,
    )

    return {
        "dance_id": dance_id,
        "narration": payload.narration,
    }


@app.post(
    "/api/jobs",
    status_code=202,
)
async def create_job(
    video: UploadFile = File(...),
    dance_id: str | None = Form(
        default=None
    ),
    save_to_dataset: bool = Form(
        default=False
    ),
    compare_with_reference: bool = Form(
        default=False
    ),
):
    suffix = Path(
        video.filename or ""
    ).suffix.lower()

    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                "请上传 MP4、MOV、WebM、"
                "AVI 或 MKV 视频"
            ),
        )

    normalized_dance_id = None
    reference_pose_path = None
    dance = None

    if (
        save_to_dataset
        and compare_with_reference
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "数据集入库与用户动作比对"
                "不能同时执行"
            ),
        )

    if dance_id:
        normalized_dance_id = (
            _normalize_dance_id(
                dance_id
            )
        )

        dance = get_dance(
            normalized_dance_id
        )

        if dance is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "数据库中不存在舞蹈记录："
                    f"{normalized_dance_id}"
                ),
            )

    if (
        save_to_dataset
        and not normalized_dance_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "保存到数据集时"
                "必须提供 dance_id"
            ),
        )

    if compare_with_reference:
        if not normalized_dance_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "动作比对时"
                    "必须提供 dance_id"
                ),
            )

        stored_pose_path = dance.get(
            "pose_2d_path"
        )

        if not stored_pose_path:
            raise HTTPException(
                status_code=409,
                detail=(
                    "该标准动作尚未生成"
                    "二维姿态数据，"
                    "请先完成数据集处理"
                ),
            )

        reference_pose_path = (
            _resolve_project_path(
                stored_pose_path
            )
        )

        if not (
            reference_pose_path
            .is_file()
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "标准动作二维姿态"
                    "文件不存在："
                    f"{reference_pose_path}"
                ),
            )

    job_id = uuid.uuid4().hex[:12]

    job_dir = (
        JOBS_ROOT
        / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    input_path = (
        job_dir
        / f"input{suffix}"
    )

    size = 0

    try:
        with input_path.open(
            "wb"
        ) as target:
            while chunk := await video.read(
                1024 * 1024
            ):
                size += len(chunk)

                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "视频不能超过 "
                            "300 MB"
                        ),
                    )

                target.write(chunk)

    except Exception:
        shutil.rmtree(
            job_dir,
            ignore_errors=True,
        )
        raise

    finally:
        await video.close()

    state = _save(
        job_id,
        status="queued",
        stage="queued",
        progress=0,
        message="任务已进入处理队列",
        filename=video.filename,
        size_bytes=size,
        dance_id=normalized_dance_id,
        save_to_dataset=(
            save_to_dataset
        ),
        compare_with_reference=(
            compare_with_reference
        ),
        created_at=_now(),
    )

    EXECUTOR.submit(
        _process,
        job_id,
        input_path,
        normalized_dance_id,
        save_to_dataset,
        reference_pose_path,
    )

    return state


@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: str,
    request: Request,
):
    state = _load(job_id)

    if (
        state.get("status")
        == "completed"
    ):
        backend_origin = str(
            request.base_url
        ).rstrip("/")

        base = (
            f"{backend_origin}"
            f"/api/jobs/{job_id}"
            f"/artifacts"
        )

        state["artifact_urls"] = {
            key: (
                f"{base}/{filename}"
            )
            for key, filename
            in state.get(
                "artifacts",
                {},
            ).items()
        }

    return JSONResponse(state)


@app.get(
    "/api/jobs/{job_id}/"
    "artifacts/{filename}"
)
def get_artifact(
    job_id: str,
    filename: str,
):
    state = _load(job_id)

    allowed_files = set(
        state.get(
            "artifacts",
            {},
        ).values()
    )

    if filename not in allowed_files:
        raise HTTPException(
            status_code=404,
            detail="结果文件不存在",
        )

    path = (
        JOBS_ROOT
        / job_id
        / filename
    )

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="结果文件尚未生成",
        )

    media_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".json": "application/json",
        ".npy": (
            "application/"
            "octet-stream"
        ),
    }

    return FileResponse(
        path,
        media_type=media_types.get(
            path.suffix.lower(),
            "application/octet-stream",
        ),
        filename=None,
    )
