"use client";

import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import {
  Activity,
  CheckCircle2,
  Database,
  Footprints,
  LayoutDashboard,
  LibraryBig,
  Pause,
  Play,
  Search,
  ShieldCheck,
  UploadCloud,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

type View =
  | "studio"
  | "library"
  | "analysis"
  | "about";

type PoseData = {
  fps: number;
  frames: number;
  width: number;
  height: number;
  pose_2d: number[][][];
  pose_3d: number[][][];
};

type Metrics = {
  duration_seconds: number;
  frames: number;
  fps: number;
  detection_rate: number;
  mean_confidence: number;
  right_shoulder_angle?: {
    mean?: number;
    peak?: number;
    series?: Array<number | null>;
  };
  comparison?: {
    note?: string;
    aligned_frames?: number;
    mean_joint_error_normalized?: number;
    mean_right_shoulder_angle_delta?: number;
  } | null;
};

type JobStatus =
  | "uploading"
  | "queued"
  | "processing"
  | "completed"
  | "failed";

type JobState = {
  id?: string;
  status: JobStatus;
  progress?: number;
  message?: string;
  metrics?: Metrics;
  artifact_urls?: Record<string, string>;
};

type NarrationSegment = {
  time: string;
  text: string;
};

type DanceRecord = {
  dance_id: string;
  name: string;
  ethnic_group?: string | null;
  region?: string | null;
  description?: string | null;
  video_url?: string | null;
  pose_data_url?: string | null;
  review_status?: string | null;
  review_status_text?: string | null;
  has_pose_2d?: boolean;
  has_video?: boolean;
  narration?: string | null;
};

type NarrationPayload = {
  danceId: string;
  segments: NarrationSegment[];
};

const API = "http://127.0.0.1:8765";

const nav = [
  ["studio", "数字化工作台", LayoutDashboard],
  ["library", "舞蹈资源库", LibraryBig],
  ["analysis", "动作分析", Activity],
  ["about", "项目与合规", ShieldCheck],
] as const;

function parseNarration(
  danceId: string,
  value: string | null | undefined,
): NarrationPayload {
  if (!value?.trim()) {
    return { danceId, segments: [] };
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed)) {
      const segments = parsed
        .filter(
          (item): item is Record<string, unknown> =>
            Boolean(item) && typeof item === "object",
        )
        .map((item, index) => ({
          time:
            typeof item.time === "string"
              ? item.time
              : `片段 ${index + 1}`,
          text:
            typeof item.text === "string"
              ? item.text
              : typeof item.content === "string"
                ? item.content
                : "",
        }))
        .filter((item) => item.text);

      return { danceId, segments };
    }
  } catch {
    // 兼容数据库中存放的普通 Markdown 或文本解说。
  }

  const segments = value
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => ({ time: "解说", text: line }));

  return { danceId, segments };
}

const COCO_CONNECTIONS = [
  [0, 1],
  [0, 2],
  [1, 3],
  [2, 4],
  [5, 6],
  [5, 7],
  [7, 9],
  [6, 8],
  [8, 10],
  [5, 11],
  [6, 12],
  [11, 12],
  [11, 13],
  [13, 15],
  [12, 14],
  [14, 16],
] as const;

const H36M_CONNECTIONS = [
  [0, 1],
  [1, 2],
  [2, 3],
  [0, 4],
  [4, 5],
  [5, 6],
  [0, 7],
  [7, 8],
  [8, 9],
  [9, 10],
  [8, 11],
  [11, 12],
  [12, 13],
  [8, 14],
  [14, 15],
  [15, 16],
] as const;

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "处理失败";
}

function getArtifactUrl(
  job: JobState | null,
  key: string,
): string {
  const url = job?.artifact_urls?.[key];

  if (!url) {
    return "";
  }

  if (
    url.startsWith("http://") ||
    url.startsWith("https://")
  ) {
    return url;
  }

  return `${API}${url}`;
}

function usePoseData(
  job: JobState | null,
): PoseData | null {
  const [loaded, setLoaded] = useState<{
    url: string;
    data: PoseData;
  } | null>(null);

  const url =
    job?.status === "completed"
      ? getArtifactUrl(job, "pose_data")
      : "";

  useEffect(() => {
    if (!url) {
      return;
    }

    const controller = new AbortController();

    async function loadPoseData() {
      const response = await fetch(url, {
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(
          `姿态数据加载失败：${response.status}`,
        );
      }

      const data =
        (await response.json()) as PoseData;

      setLoaded({
        url,
        data,
      });
    }

    loadPoseData().catch((error: unknown) => {
      if (
        error instanceof DOMException &&
        error.name === "AbortError"
      ) {
        return;
      }

      console.error(error);
    });

    return () => {
      controller.abort();
    };
  }, [url]);

  if (!url || loaded?.url !== url) {
    return null;
  }

  return loaded.data;
}

async function pollJob(
  id: string,
  setJob: (job: JobState) => void,
): Promise<void> {
  for (;;) {
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, 1600);
    });

    const response = await fetch(
      `${API}/api/jobs/${id}`,
    );

    if (!response.ok) {
      throw new Error("无法读取处理进度");
    }

    const state =
      (await response.json()) as JobState;

    setJob(state);

    if (
      state.status === "completed" ||
      state.status === "failed"
    ) {
      return;
    }
  }
}

function Logo() {
  return (
    <span className="logo">
      <i />
      <i />
      <i />
    </span>
  );
}

function Head({
  k,
  t,
  p,
}: {
  k: string;
  t: string;
  p: string;
}) {
  return (
    <header className="head">
      <p className="eyebrow">{k}</p>
      <h1>{t}</h1>
      <p>{p}</p>
    </header>
  );
}

function Card({
  children,
  c = "",
}: {
  children: ReactNode;
  c?: string;
}) {
  return (
    <article className={`card ${c}`}>
      {children}
    </article>
  );
}

function Vid({
  t,
  m,
  s,
  empty = "等待处理结果",
  videoRef,
}: {
  t: string;
  m: string;
  s: string;
  empty?: string;
  videoRef?: RefObject<HTMLVideoElement | null>;
}) {
  return (
    <figure className="vid">
      <figcaption>
        <span>
          <b>{t}</b>
          <small>{m}</small>
        </span>

        <em>SYNC</em>
      </figcaption>

      {s ? (
        <video
          ref={videoRef}
          className="sync"
          src={s}
          autoPlay
          muted
          loop
          playsInline
          controls
        />
      ) : (
        <div className="vid-empty">
          <Activity />
          <b>正在生成</b>
          <small>{empty}</small>
        </div>
      )}
    </figure>
  );
}

function Pose2DCanvas({
  videoRef,
  data,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  data: PoseData;
}) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let animationId = 0;

    const draw = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;

      if (
        !video ||
        !canvas ||
        video.readyState < 2 ||
        data.pose_2d.length === 0
      ) {
        animationId =
          requestAnimationFrame(draw);
        return;
      }

      const context =
        canvas.getContext("2d");

      if (!context) {
        return;
      }

      if (canvas.width !== data.width) {
        canvas.width = data.width;
      }

      if (canvas.height !== data.height) {
        canvas.height = data.height;
      }

      context.clearRect(
        0,
        0,
        canvas.width,
        canvas.height,
      );

      context.drawImage(
        video,
        0,
        0,
        canvas.width,
        canvas.height,
      );

      const frameIndex = Math.min(
        Math.max(
          Math.floor(
            video.currentTime * data.fps,
          ),
          0,
        ),
        data.pose_2d.length - 1,
      );

      const joints =
        data.pose_2d[frameIndex];

      context.strokeStyle = "#39d8ce";
      context.lineWidth = 4;
      context.lineCap = "round";

      for (
        const [start, end]
        of COCO_CONNECTIONS
      ) {
        const point1 = joints[start];
        const point2 = joints[end];

        if (!point1 || !point2) {
          continue;
        }

        if (
          point1[2] < 0.15 ||
          point2[2] < 0.15
        ) {
          continue;
        }

        context.beginPath();
        context.moveTo(
          point1[0],
          point1[1],
        );
        context.lineTo(
          point2[0],
          point2[1],
        );
        context.stroke();
      }

      for (const point of joints) {
        if (!point || point[2] < 0.15) {
          continue;
        }

        context.beginPath();

        context.fillStyle =
          point[2] >= 0.3
            ? "#ffbd4a"
            : "#ff774a";

        context.arc(
          point[0],
          point[1],
          6,
          0,
          Math.PI * 2,
        );

        context.fill();
      }

      animationId =
        requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [data, videoRef]);

  return (
    <figure className="vid">
      <figcaption>
        <span>
          <b>二维骨架</b>
          <small>
            RTMPose · COCO-17
          </small>
        </span>

        <em>SYNC</em>
      </figcaption>

      <canvas
        ref={canvasRef}
        className="pose-canvas"
        style={{
          display: "block",
          width: "100%",
          height: "100%",
          minHeight: 320,
          background: "#07191d",
        }}
      />
    </figure>
  );
}

function Pose3DCanvas({
  videoRef,
  data,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  data: PoseData;
}) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let animationId = 0;
    let coordinateLimit = 0;

    // 使用整个序列的统一缩放比例，
    // 避免播放时骨架忽大忽小。
    for (const frame of data.pose_3d) {
      for (const joint of frame) {
        coordinateLimit = Math.max(
          coordinateLimit,
          Math.abs(joint[0]),
          Math.abs(joint[1]),
          Math.abs(joint[2]),
        );
      }
    }

    coordinateLimit = Math.max(
      coordinateLimit,
      0.000001,
    );

    const leftJoints = new Set([
      1,
      2,
      3,
      14,
      15,
      16,
    ]);

    const rightJoints = new Set([
      4,
      5,
      6,
      11,
      12,
      13,
    ]);

    const draw = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;

      if (
        !video ||
        !canvas ||
        data.pose_3d.length === 0
      ) {
        animationId =
          requestAnimationFrame(draw);
        return;
      }

      const context =
        canvas.getContext("2d");

      if (!context) {
        return;
      }

      /*
       * 整个Canvas分为三栏：
       * 0–320：正视图
       * 320–640：侧视图
       * 640–960：俯视图
       */
      const canvasWidth = 960;
      const canvasHeight = 360;
      const viewWidth = 320;

      if (canvas.width !== canvasWidth) {
        canvas.width = canvasWidth;
      }

      if (canvas.height !== canvasHeight) {
        canvas.height = canvasHeight;
      }

      context.fillStyle = "#07191d";
      context.fillRect(
        0,
        0,
        canvasWidth,
        canvasHeight,
      );

      // 三视图分隔线。
      context.strokeStyle = "#24434a";
      context.lineWidth = 2;

      context.beginPath();
      context.moveTo(viewWidth, 0);
      context.lineTo(
        viewWidth,
        canvasHeight,
      );
      context.stroke();

      context.beginPath();
      context.moveTo(
        viewWidth * 2,
        0,
      );
      context.lineTo(
        viewWidth * 2,
        canvasHeight,
      );
      context.stroke();

      const frameIndex = Math.min(
        Math.max(
          Math.floor(
            video.currentTime * data.fps,
          ),
          0,
        ),
        data.pose_3d.length - 1,
      );

      const pose =
        data.pose_3d[frameIndex];

      const scale =
        115 / coordinateLimit;

      type ViewName =
        | "front"
        | "side"
        | "top";

      const drawView = (
        view: ViewName,
        centerX: number,
        title: string,
      ) => {
        const centerY = 195;

        context.fillStyle = "#9fb5b8";
        context.font =
          "18px sans-serif";
        context.textAlign = "center";

        context.fillText(
          title,
          centerX,
          30,
        );

        const projected =
          pose.map(([x, y, z]) => {
            let horizontal = 0;
            let vertical = 0;

            if (view === "front") {
              // 正视图：X-Y平面
              horizontal = x;
              vertical = y;
            } else if (view === "side") {
              // 侧视图：Z-Y平面
              horizontal = z;
              vertical = y;
            } else {
              // 俯视图：X-Z平面
              horizontal = x;
              vertical = z;
            }

            return [
              centerX +
                horizontal * scale,

              /*
               * 这里必须使用加号。
               * MotionAGFormer输出与Canvas的
               * Y轴方向一致，之前使用减号
               * 会造成上下颠倒。
               */
              centerY +
                vertical * scale,
            ];
          });

        context.lineWidth = 4;
        context.lineCap = "round";

        for (
          const [start, end]
          of H36M_CONNECTIONS
        ) {
          const point1 =
            projected[start];

          const point2 =
            projected[end];

          if (!point1 || !point2) {
            continue;
          }

          if (
            leftJoints.has(start) ||
            leftJoints.has(end)
          ) {
            context.strokeStyle =
              "#ff7845";
          } else if (
            rightJoints.has(start) ||
            rightJoints.has(end)
          ) {
            context.strokeStyle =
              "#4d83ff";
          } else {
            context.strokeStyle =
              "#39d8ce";
          }

          context.beginPath();

          context.moveTo(
            point1[0],
            point1[1],
          );

          context.lineTo(
            point2[0],
            point2[1],
          );

          context.stroke();
        }

        for (
          let jointIndex = 0;
          jointIndex < projected.length;
          jointIndex += 1
        ) {
          const point =
            projected[jointIndex];

          if (
            leftJoints.has(jointIndex)
          ) {
            context.fillStyle =
              "#ff7845";
          } else if (
            rightJoints.has(jointIndex)
          ) {
            context.fillStyle =
              "#4d83ff";
          } else {
            context.fillStyle =
              "#ffbd4a";
          }

          context.beginPath();

          context.arc(
            point[0],
            point[1],
            6,
            0,
            Math.PI * 2,
          );

          context.fill();
        }
      };

      drawView(
        "front",
        160,
        "正视图",
      );

      drawView(
        "side",
        480,
        "侧视图",
      );

      drawView(
        "top",
        800,
        "俯视图",
      );

      context.fillStyle = "#6f8f94";
      context.font = "14px sans-serif";
      context.textAlign = "left";

      context.fillText(
        `第 ${frameIndex + 1} / ${
          data.pose_3d.length
        } 帧`,
        15,
        canvasHeight - 15,
      );

      animationId =
        requestAnimationFrame(draw);
    };

    draw();

    return () => {
      cancelAnimationFrame(animationId);
    };
  }, [data, videoRef]);

    return (
    <figure className="vid">
      <figcaption>
        <span>
          <b>估计三维姿态</b>

          <small>
            正视图 · 侧视图 · 俯视图
          </small>
        </span>

        <em>SYNC</em>
      </figcaption>

      <canvas
        ref={canvasRef}
        className="pose-canvas"
        style={{
          display: "block",
          width: "100%",
          height: "auto",
          minHeight: 320,
          aspectRatio: "8 / 3",
          background: "#07191d",
        }}
      />
    </figure>
  );
}

function Studio({
  selectedDance,
  onNarrationSaved,
}: {
  selectedDance: DanceRecord | null;
  onNarrationSaved: (danceId: string, narration: string) => void;
}) {
  const [play, setPlay] = useState(true);
  const [file, setFile] = useState("");
  const [source, setSource] = useState("");
  const [job, setJob] =
    useState<JobState | null>(null);
  const [narrationDraft, setNarrationDraft] = useState("");
  const [narrationSaving, setNarrationSaving] = useState(false);
  const [narrationMessage, setNarrationMessage] = useState("");

  const masterVideoRef =
    useRef<HTMLVideoElement>(null);

  const poseData = usePoseData(job);
  const datasetPoseData = usePoseData(
    selectedDance?.pose_data_url
      ? {
          status: "completed",
          artifact_urls: {
            pose_data: selectedDance.pose_data_url,
          },
        }
      : null,
  );

  useEffect(() => {
    setNarrationDraft(selectedDance?.narration || "");
  }, [selectedDance?.dance_id, selectedDance?.narration]);

  useEffect(() => {
    setNarrationMessage("");
  }, [selectedDance?.dance_id]);

  async function saveNarration() {
    if (!selectedDance) return;
    setNarrationSaving(true);
    setNarrationMessage("");
    try {
      const response = await fetch(
        `${API}/api/dances/${encodeURIComponent(selectedDance.dance_id)}/narration`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ narration: narrationDraft }),
        },
      );
      const result = (await response.json()) as { detail?: string };
      if (!response.ok) {
        throw new Error(result.detail || "解说保存失败");
      }
      onNarrationSaved(selectedDance.dance_id, narrationDraft);
      setNarrationMessage("已保存到当前舞蹈记录");
    } catch (error) {
      setNarrationMessage(getErrorMessage(error));
    } finally {
      setNarrationSaving(false);
    }
  }

  const busy = Boolean(
    job &&
      [
        "uploading",
        "queued",
        "processing",
      ].includes(job.status),
  );

  const metrics = job?.metrics;

  const original =
    source ||
    (selectedDance?.has_video
      ? selectedDance.video_url ||
        `${API}/api/dances/${encodeURIComponent(
          selectedDance.dance_id,
        )}/video`
      : "");

  const toggle = () => {
    const videos = [
      ...document.querySelectorAll<HTMLVideoElement>(
        ".viewer .sync",
      ),
    ];

    const anchor = videos[0];

    videos.slice(1).forEach((video) => {
      if (
        anchor &&
        Math.abs(
          video.currentTime -
            anchor.currentTime,
        ) > 0.12
      ) {
        video.currentTime =
          anchor.currentTime;
      }
    });

    videos.forEach((video) => {
      if (play) {
        video.pause();
      } else {
        video.play().catch(() => {
          // 浏览器拒绝自动播放时由用户手动点击。
        });
      }
    });

    setPlay(!play);
  };

  const upload = async (
    selectedFile?: File,
  ) => {
    if (!selectedFile) {
      return;
    }

    if (
      selectedFile.size >
      300 * 1024 * 1024
    ) {
      setJob({
        status: "failed",
        progress: 0,
        message: "视频不能超过 300 MB",
      });

      return;
    }

    setFile(selectedFile.name);
    setSource(
      URL.createObjectURL(selectedFile),
    );

    setJob({
      status: "uploading",
      progress: 1,
      message: "正在上传到本地姿态服务",
    });

    const body = new FormData();
    body.append("video", selectedFile);

    try {
      const response = await fetch(
        `${API}/api/jobs`,
        {
          method: "POST",
          body,
        },
      );

      const state =
        (await response.json()) as JobState;

      if (!response.ok) {
        throw new Error(
          state.message || "上传失败",
        );
      }

      if (!state.id) {
        throw new Error(
          "后端没有返回任务编号",
        );
      }

      setJob(state);

      await pollJob(
        state.id,
        setJob,
      );
    } catch (error: unknown) {
      setJob({
        status: "failed",
        progress: 0,
        message:
          error instanceof TypeError
            ? "无法连接本地姿态服务，请先运行 start_pose_service.ps1"
            : getErrorMessage(error),
      });
    }
  };

  return (
    <div className="stack">
      <section className="head action-head">
        <div>
          <p className="eyebrow">
            民族舞蹈数字化工作台
          </p>

          <h1>
            上传一段视频，生成二维与三维姿态
          </h1>

          <p>
            上传后立即显示原始影像；本机完成处理后，
            二维骨架和估计三维姿态会自动载入。
          </p>
        </div>

        <Button asChild>
          <label>
            <UploadCloud />

            {busy
              ? "处理中…"
              : "上传舞蹈视频"}

            <input
              hidden
              disabled={busy}
              type="file"
              accept="video/mp4,video/webm,.mp4,.webm"
              onChange={(event) =>
                upload(
                  event.target.files?.[0],
                )
              }
            />
          </label>
        </Button>
      </section>

      {job && (
        <div
          className={`upload ${job.status}`}
        >
          <b>{file || "上传任务"}</b>

          <span>
            {job.status === "completed"
              ? "二维与三维姿态数据已生成"
              : job.message}
          </span>

          <Progress
            value={job.progress || 0}
          />

          <code>
            {job.progress || 0}%
          </code>
        </div>
      )}

      <section className="viewer">
        <header>
          <div>
            <code>
              {file ? "USER" : selectedDance?.dance_id || "未选择样本"}
            </code>

            <p>
              <b>
                {file
                  ? "学习者上传视频"
                  : selectedDance
                    ? `${selectedDance.ethnic_group || "民族待补充"} · ${selectedDance.name}`
                    : "请先在资源库选择舞蹈样本"}
              </b>

              <small>
                {metrics
                  ? `${metrics.duration_seconds} 秒 · ${metrics.frames} 帧 · ${metrics.fps} FPS`
                  : "9.83 秒 · 295 帧 · 30 FPS"}
              </small>
            </p>
          </div>

          <button
            onClick={toggle}
            disabled={
              file ? !poseData : false
            }
          >
            {play ? <Pause /> : <Play />}

            {play
              ? "同步暂停"
              : "同步播放"}
          </button>
        </header>

        <div className="videos">
          <Vid
            t="原始影像"
            m={
              file
                ? "刚刚上传的本地视频"
                : "文化与动作语境"
            }
            s={original}
            videoRef={masterVideoRef}
          />

          {file ? (
            poseData ? (
              <Pose2DCanvas
                videoRef={masterVideoRef}
                data={poseData}
              />
            ) : (
              <Vid
                t="二维骨架"
                m="RTMPose · COCO-17"
                s=""
                empty={
                  job?.message ||
                  "等待二维姿态数据"
                }
              />
            )
            ) : datasetPoseData ? (
              <Pose2DCanvas
                videoRef={masterVideoRef}
                data={datasetPoseData}
              />
            ) : (
            <Vid
              t="二维骨架"
              m="RTMPose · COCO-17"
                s=""
                empty="该样本尚未关联二维姿态结果"
            />
          )}

          {file ? (
            poseData ? (
              <Pose3DCanvas
                videoRef={masterVideoRef}
                data={poseData}
              />
            ) : (
              <Vid
                t="估计三维姿态"
                m="MotionAGFormer · H36M-17"
                s=""
                empty={
                  job?.message ||
                  "等待三维姿态数据"
                }
              />
            )
            ) : datasetPoseData ? (
              <Pose3DCanvas
                videoRef={masterVideoRef}
                data={datasetPoseData}
              />
            ) : (
            <Vid
              t="估计三维姿态"
              m="MotionAGFormer · H36M-17"
                s=""
                empty="该样本尚未关联三维姿态结果"
            />
          )}
        </div>

        <div className="timeline">
          <p>
            <span>00:00</span>

            <b>
              {job?.status === "completed"
                ? poseData
                  ? "姿态结果已载入"
                  : "正在载入姿态坐标"
                : file
                  ? "正在建立姿态结果"
                  : selectedDance?.name || "等待选择舞蹈样本"}
            </b>

            <span>
              {metrics
                ? `00:${String(
                    metrics.duration_seconds,
                  ).padStart(5, "0")}`
                : "—"}
            </span>
          </p>

          <i />

          <small>
            {file
              ? "原始视频　二维提取　遮挡修复　三维估计　结果载入"
              : selectedDance?.description || "该样本尚无动作摘要"}
          </small>
        </div>
      </section>

      {!file && selectedDance && (
        <section className="cols single">
          <Card>
            <div className="title">
              <span>
                <p className="eyebrow">
                  AI 动作解说
                </p>

                <h2>动作分段摘要</h2>
              </span>

              <Badge className="ai">
                {selectedDance.narration
                  ? "已保存解说"
                  : "暂无解说"}
              </Badge>
            </div>

            <ul className="motions">
              {parseNarration(
                selectedDance.dance_id,
                selectedDance.narration,
              ).segments.length > 0 ? (
                parseNarration(
                  selectedDance.dance_id,
                  selectedDance.narration,
                ).segments.map((segment, index) => (
                  <li key={`${selectedDance.dance_id}-${index}`}>
                    <time>{segment.time}</time>
                    {segment.text}
                  </li>
                ))
              ) : (
                <li>该样本还没有保存动作解说。</li>
              )}
            </ul>

            <label className="narration-editor">
              <span>编辑或粘贴该样本的 AI 解说（每行一段，可写“时间｜内容”）</span>
              <textarea
                value={narrationDraft}
                onChange={(event) => setNarrationDraft(event.target.value)}
                rows={5}
                placeholder="例如：00:00–00:05｜双臂向两侧舒展，重心保持稳定。"
              />
            </label>
            <div className="narration-save">
              <Button
                type="button"
                onClick={() => void saveNarration()}
                disabled={narrationSaving}
              >
                {narrationSaving ? "正在保存…" : "保存当前样本解说"}
              </Button>
              {narrationMessage && <small role="status">{narrationMessage}</small>}
            </div>

            <small className="muted">
              解说内容对应 {selectedDance.dance_id}，不代替专业舞蹈教学判断。
            </small>
          </Card>
        </section>
      )}
    </div>
  );
}

function Library({
  records,
  selectedDanceId,
  loading,
  error,
  onSelectDance,
  onCompare,
}: {
  records: DanceRecord[];
  selectedDanceId: string;
  loading: boolean;
  error: string;
  onSelectDance: (danceId: string) => void;
  onCompare: (danceId: string) => void;
}) {
  const [query, setQuery] =
    useState("");

  return (
    <div className="stack">
      <Head
        k="数字资源库"
        t="把动作、资料与授权记录放在一起"
        p={`当前读取 ${records.length} 条数据库记录；核验状态和视频均来自后端数据。`}
      />

      <label className="search">
        <Search />

        <input
          value={query}
          onChange={(event) =>
            setQuery(event.target.value)
          }
          placeholder="搜索样本、民族或动作"
        />
      </label>

      {error && (
        <p role="alert" className="muted">
          {error}
        </p>
      )}

      {loading && (
        <p className="muted">正在读取数据库记录…</p>
      )}

      <section className="resources">
        {records
          .filter((record) =>
            [
              record.dance_id,
              record.name,
              record.ethnic_group || "",
              record.region || "",
              record.review_status_text || "",
            ]
              .join(" ")
              .toLowerCase()
              .includes(query.trim().toLowerCase()),
          )
          .map((record) => (
            <article key={record.dance_id}>
              <div className="cover">
                <Footprints />
                <code>{record.dance_id}</code>
              </div>

              <div>
                <p>
                  <Badge
                    className={
                      record.review_status === "verified"
                        ? "verified"
                        : "pending"
                    }
                  >
                    {record.review_status_text || "待核验"}
                  </Badge>

                  <span>
                    {record.has_pose_2d
                      ? "姿态数据已就绪"
                      : "姿态数据待处理"}
                  </span>
                </p>

                <h2>{record.name}</h2>

                <small>
                  {[record.ethnic_group, record.region, record.description]
                    .filter(Boolean)
                    .join(" · ") || "尚未补充舞蹈资料"}
                </small>

                <div className="resource-actions">
                  <Button
                    type="button"
                    variant={
                      selectedDanceId === record.dance_id
                        ? "default"
                        : "outline"
                    }
                    onClick={() => onSelectDance(record.dance_id)}
                  >
                    {selectedDanceId === record.dance_id
                      ? "当前样本"
                      : "设为当前样本"}
                  </Button>

                  <Button
                    type="button"
                    variant="outline"
                    disabled={!record.has_pose_2d}
                    onClick={() => onCompare(record.dance_id)}
                    title={
                      record.has_pose_2d
                        ? "选择此标准动作并进入动作比对"
                        : "需先为该样本生成二维姿态数据"
                    }
                  >
                    用此动作进行比对
                  </Button>
                </div>
              </div>
            </article>
          ))}
        {!loading && !error && records.length === 0 && (
          <p className="muted">数据库中还没有舞蹈记录。</p>
        )}
      </section>
    </div>
  );
}

function Analysis({
  records,
  selectedDance,
  onSelectDance,
}: {
  records: DanceRecord[];
  selectedDance: DanceRecord | null;
  onSelectDance: (danceId: string) => void;
}) {
  const [source, setSource] =
    useState("");

  const [name, setName] =
    useState("");

  const [job, setJob] =
    useState<JobState | null>(null);

  const videoRef =
    useRef<HTMLVideoElement>(null);

  const poseData =
    usePoseData(job);

  const busy = Boolean(
    job &&
      [
        "uploading",
        "queued",
        "processing",
      ].includes(job.status),
  );

  const metrics = job?.metrics;

  const series = (
    metrics?.right_shoulder_angle
      ?.series || [
      28,
      42,
      36,
      70,
      58,
      102,
      84,
      118,
      91,
      132,
      105,
      141,
      119,
    ]
  ).filter(
    (value): value is number =>
      value !== null,
  );

  const points = series
    .map((value, index) => {
      const x =
        series.length === 1
          ? 0
          : (index /
              (series.length - 1)) *
            480;

      const y =
        142 -
        (Math.min(180, value) /
          180) *
          118;

      return `${x},${y}`;
    })
    .join(" ");

  const upload = async (
    selectedFile?: File,
  ) => {
    if (!selectedFile) {
      return;
    }

    if (
      selectedFile.size >
      300 * 1024 * 1024
    ) {
      setJob({
        status: "failed",
        progress: 0,
        message: "视频不能超过 300 MB",
      });

      return;
    }

    setName(selectedFile.name);

    setSource(
      URL.createObjectURL(selectedFile),
    );

    setJob({
      status: "uploading",
      progress: 1,
      message: "正在上传到本地姿态服务",
    });

    const body = new FormData();
    body.append("video", selectedFile);
    if (selectedDance) {
      body.append("dance_id", selectedDance.dance_id);
    }
    body.append(
      "compare_with_reference",
      selectedDance?.has_pose_2d ? "true" : "false",
    );

    try {
      const response = await fetch(
        `${API}/api/jobs`,
        {
          method: "POST",
          body,
        },
      );

      const state =
        (await response.json()) as JobState;

      if (!response.ok) {
        throw new Error(
          state.message || "上传失败",
        );
      }

      if (!state.id) {
        throw new Error(
          "后端没有返回任务编号",
        );
      }

      setJob(state);

      await pollJob(
        state.id,
        setJob,
      );
    } catch (error: unknown) {
      setJob({
        status: "failed",
        progress: 0,
        message:
          error instanceof TypeError
            ? "无法连接本地姿态服务，请先运行 start_pose_service.ps1"
            : getErrorMessage(error),
      });
    }
  };

  return (
    <div className="stack">
      <Head
        k="动作分析"
        t="上传学习者视频，生成二维与三维姿态"
        p="本机依次运行 RTMPose、遮挡修复与 MotionAGFormer，并输出可追溯的动作指标。"
      />

      <Card>
        <p className="eyebrow">标准动作</p>
        <h2>选择本次比对的示范样本</h2>
        <label className="search">
          <Footprints />
          <select
            value={selectedDance?.dance_id || ""}
            onChange={(event) => {
              onSelectDance(event.target.value);
              setJob(null);
            }}
          >
            <option value="" disabled>
              请选择数据库中的舞蹈记录
            </option>
            {records.map((record) => (
              <option
                key={record.dance_id}
                value={record.dance_id}
              >
                {record.dance_id} · {record.ethnic_group || "民族待补充"} · {record.name}
                {record.has_pose_2d ? "（可比对）" : "（姿态待处理）"}
              </option>
            ))}
          </select>
        </label>
        <small className="muted">
          {selectedDance
            ? selectedDance.has_pose_2d
              ? `本次结果将与 ${selectedDance.dance_id} 的二维姿态进行比对。`
              : `当前样本 ${selectedDance.dance_id} 尚无二维姿态，本次会生成用户视频姿态但不计算比对指标。`
            : "请先添加舞蹈记录后再选择标准动作。"}
        </small>
      </Card>

      <section className="learner-upload">
        <div>
          <p className="eyebrow">
            学习者视频
          </p>

          <h2>
            上传视频并启动姿态处理
          </h2>

          <p>
            视频仅保存在本机任务目录，
            不会覆盖资源库原始数据。
            建议先使用 10–30 秒单人全身视频。
          </p>

          <label>
            <UploadCloud />
            选择本地视频

            <input
              hidden
              type="file"
              accept="video/mp4,video/webm,.mp4,.webm"
              disabled={busy}
              onChange={(event) =>
                upload(
                  event.target.files?.[0],
                )
              }
            />
          </label>

          {name && (
            <small>
              当前文件：{name}
            </small>
          )}
        </div>

        {source ? (
          <video
            ref={videoRef}
            src={source}
            controls
            playsInline
          />
        ) : (
          <div className="drop">
            <UploadCloud />
            <b>尚未上传用户视频</b>
            <small>
              支持 MP4、WebM，最大 300 MB
            </small>
          </div>
        )}
      </section>

      {job && (
        <section
          className={`job-state ${job.status}`}
        >
          <div>
            <b>
              {job.status === "completed"
                ? "处理完成"
                : job.status === "failed"
                  ? "处理失败"
                  : job.message}
            </b>

            <span>
              {job.status === "completed"
                ? "二维、三维坐标和指标已生成"
                : job.message}
            </span>
          </div>

          <Progress
            value={job.progress || 0}
          />

          <code>
            {job.progress || 0}%
          </code>
        </section>
      )}

      {job?.status === "completed" && (
        <section className="result-videos">
          {poseData ? (
            <>
              <Pose2DCanvas
                videoRef={videoRef}
                data={poseData}
              />

              <Pose3DCanvas
                videoRef={videoRef}
                data={poseData}
              />
            </>
          ) : (
            <div className="vid-empty">
              <Activity />
              <b>正在载入姿态坐标</b>
              <small>
                正在读取 pose_data.json
              </small>
            </div>
          )}
        </section>
      )}

      <section className="analysis">
        <Card c="wide chart">
          <div className="title">
            <span>
              <p className="eyebrow">
                关节角度
              </p>

              <h2>右肩展开角度</h2>
            </span>

            <b>
              峰值{" "}
              {metrics
                ?.right_shoulder_angle
                ?.peak ?? 148}
              °
            </b>
          </div>

          <svg viewBox="0 0 480 150">
            <polyline
              points={points}
              fill="none"
              stroke="#37d4c3"
              strokeWidth="3"
            />
          </svg>
        </Card>

        <Card>
          <p className="eyebrow">
            处理质量
          </p>

          <h2>
            {metrics
              ? `${metrics.detection_rate}%`
              : "等待上传"}
          </h2>

          <div className="orbit">
            <i />
            <i />
            <i />
            <b />
          </div>

          <p className="muted">
            {metrics
              ? `人体检出率 · 平均置信度 ${metrics.mean_confidence}`
              : "完成处理后显示检出率与置信度。"}
          </p>
        </Card>

        <Card>
          <p className="eyebrow">
            视频结构
          </p>

          <h2>
            {metrics
              ? `${metrics.frames} 帧`
              : "动作时序"}
          </h2>

          <div className="bars">
            {[
              42,
              64,
              53,
              86,
              70,
              48,
              76,
              58,
              39,
              67,
            ].map((height, index) => (
              <i
                key={index}
                style={{
                  height: `${height}%`,
                }}
              />
            ))}
          </div>

          <p className="muted">
            {metrics
              ? `${metrics.duration_seconds} 秒 · ${metrics.fps} FPS`
              : "完成处理后显示帧数、时长与节奏。"}
          </p>
        </Card>

        <article className="compare">
          <div>
            <Badge className="ai">
              对比结果
            </Badge>

            <h2>
              {selectedDance
                ? `学习者与 ${selectedDance.dance_id} 示范片段`
                : "用户视频动作分析"}
            </h2>

            <p>
              {metrics?.comparison?.note ||
                "上传完成后按时间归一化，对齐关节轨迹与右肩角度。"}
            </p>
          </div>

          <div>
            <span>
              <CheckCircle2 />
              时间对齐：
              {metrics?.comparison
                ?.aligned_frames ??
                "待处理"}{" "}
              帧
            </span>

            <span>
              <CheckCircle2 />
              归一化关节误差：
              {metrics?.comparison
                ?.mean_joint_error_normalized ??
                "—"}
            </span>

            <span>
              <CheckCircle2 />
              右肩平均角度差：
              {metrics?.comparison
                ?.mean_right_shoulder_angle_delta ??
                "—"}
              {metrics?.comparison
                ? "°"
                : ""}
            </span>

            <span>
              <CheckCircle2 />
              结果仅作可测量反馈
            </span>
          </div>
        </article>
      </section>
    </div>
  );
}

function About() {
  const cards = [
    [
      Database,
      "当前数据",
      [
        "原始视频：21 段",
        "完整结果：8 段",
        "专业复核：待开展",
      ],
    ],
    [
      ShieldCheck,
      "提交前检查",
      [
        "肖像与视频授权",
        "代码与模型来源",
        "AI 使用说明",
      ],
    ],
    [
      Users,
      "内容分级",
      [
        "权威资料可核验",
        "AI 整理附来源",
        "待专业人员复核",
      ],
    ],
  ] as const;

  return (
    <div className="stack">
      <Head
        k="项目与合规"
        t="让每一个结果都能追溯"
        p="技术、数据、文化资料和 AI 使用过程均保留来源与状态记录。"
      />

      <section className="pipeline">
        {[
          [
            "01",
            "视频采集",
            "来源与授权",
          ],
          [
            "02",
            "二维提取",
            "RTMPose",
          ],
          [
            "03",
            "质量修复",
            "遮挡与平滑",
          ],
          [
            "04",
            "三维估计",
            "相对坐标",
          ],
          [
            "05",
            "AI 标注",
            "客观描述",
          ],
          [
            "06",
            "互动传播",
            "展示与讲解",
          ],
        ].map((item) => (
          <div key={item[0]}>
            <span>{item[0]}</span>
            <b>{item[1]}</b>
            <small>{item[2]}</small>
          </div>
        ))}
      </section>

      <section className="about">
        {cards.map(
          ([Icon, title, lines]) => (
            <Card key={title}>
              <Icon />
              <h2>{title}</h2>

              <ul>
                {lines.map((line) => (
                  <li key={line}>
                    {line}
                  </li>
                ))}
              </ul>
            </Card>
          ),
        )}
      </section>
    </div>
  );
}

export default function Home() {
  const [view, setView] =
    useState<View>("studio");
  const [records, setRecords] = useState<DanceRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [recordsError, setRecordsError] = useState("");
  const [selectedDanceId, setSelectedDanceId] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function loadRecords() {
      try {
        const response = await fetch(`${API}/api/dances`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`舞蹈资源读取失败（${response.status}）`);
        }
        const data = (await response.json()) as DanceRecord[];
        setRecords(data);
        setSelectedDanceId((current) =>
          current && data.some((record) => record.dance_id === current)
            ? current
            : data[0]?.dance_id ?? "",
        );
        setRecordsError("");
      } catch (error) {
        if (!controller.signal.aborted) {
          setRecordsError(getErrorMessage(error));
        }
      } finally {
        if (!controller.signal.aborted) {
          setRecordsLoading(false);
        }
      }
    }

    void loadRecords();
    return () => controller.abort();
  }, []);

  const selectedDance =
    records.find((record) => record.dance_id === selectedDanceId) ?? null;

  function compareDance(danceId: string) {
    setSelectedDanceId(danceId);
    setView("analysis");
  }

  return (
    <main className="shell">
      <aside>
        <div className="brand">
          <Logo />

          <div>
            <b>舞迹智存</b>
            <small>
              DANCE HERITAGE LAB
            </small>
          </div>
        </div>

        <nav>
          {nav.map(
            ([id, title, Icon]) => (
              <button
                className={
                  view === id
                    ? "active"
                    : ""
                }
                onClick={() => setView(id)}
                key={id}
              >
                <Icon />
                <span>{title}</span>
              </button>
            ),
          )}
        </nav>

        <footer>
          <small>项目进度</small>
          <b>原型验证期</b>
          <Progress value={64} />

          <p>
            数媒竞赛 · 民族文化创新表达
          </p>
        </footer>
      </aside>

      <section className="main">
        <header className="top">
          <div className="mobile-brand">
            <Logo />
            <b>舞迹智存</b>
          </div>

          <p>
            民族舞蹈数字化保护平台
          </p>

          <Badge variant="outline">
            <Database />
            {records.filter((record) => record.has_video).length} 段原始视频
          </Badge>
        </header>

        <div className="content">
          {view === "studio" ? (
            <Studio
              selectedDance={selectedDance}
              onNarrationSaved={(danceId, narration) =>
                setRecords((current) => current.map((record) =>
                  record.dance_id === danceId ? { ...record, narration } : record,
                ))
              }
            />
          ) : view === "library" ? (
            <Library
              records={records}
              selectedDanceId={selectedDanceId}
              loading={recordsLoading}
              error={recordsError}
              onSelectDance={setSelectedDanceId}
              onCompare={compareDance}
            />
          ) : view === "analysis" ? (
            <Analysis
              records={records}
              selectedDance={selectedDance}
              onSelectDance={setSelectedDanceId}
            />
          ) : (
            <About />
          )}
        </div>

        <nav className="mobile-nav">
          {nav.map(
            ([id, title, Icon]) => (
              <button
                className={
                  view === id
                    ? "active"
                    : ""
                }
                onClick={() => setView(id)}
                key={id}
              >
                <Icon />
                <small>
                  {title.slice(0, 4)}
                </small>
              </button>
            ),
          )}
        </nav>
      </section>
    </main>
  );
}
