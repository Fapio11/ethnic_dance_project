"use client";

import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
  type CSSProperties,
} from "react";

import {
  Database,
  Pause,
  Play,
  Search,
  UploadCloud,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MediaDeck } from "@/components/dance/media-deck";
import { TaskProgress } from "@/components/dance/task-progress";
import { Brand } from "@/components/dance/brand";
import BrandIntro from "@/components/dance/intro";
import { DanceIcon } from "@/components/dance/dance-icon";
import { ResourceRow } from "@/components/dance/resource-row";
import { WorkbenchHeader } from "@/components/dance/workbench-header";
import { DataFeedback } from "@/components/dance/data-feedback";
import { useUploadSession } from "@/hooks/use-upload-session";
import { useVideoSession } from "@/hooks/use-video-session";
import { DANCE_API, observeVideoFrames } from "@/lib/dance-session-runtime";
import type { DanceRecord, JobState, PoseData } from "@/lib/dance-types";
import "@/components/dance/workbench-upgrade.css";
import "@/components/dance/cultural-ui.css";
import "@/components/dance/resource-folio.css";
import "@/components/dance/handdrawn-layout.css";
import "@/components/dance/copy-simplification.css";
import "@/components/dance/folio-system.css";

type View =
  | "studio"
  | "library"
  | "analysis"
  | "about";

type NarrationSegment = {
  time: string;
  text: string;
};

type NarrationPayload = {
  danceId: string;
  segments: NarrationSegment[];
};

const API = DANCE_API;

const nav = [
  ["studio", "数字化工作台", "stage"],
  ["library", "舞蹈资源库", "archive"],
  ["analysis", "动作分析", "movement"],
  ["about", "项目与合规", "record"],
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

type PoseResource = {
  data: PoseData | null;
  state: "loading" | "error" | "empty" | "ready";
  error: string;
  retry: () => void;
};

function usePoseData(job: JobState | null): PoseResource {
  const [loaded, setLoaded] = useState<{ url: string; data: PoseData | null; error: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const url = job?.status === "completed" ? getArtifactUrl(job, "pose_data") : "";
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    let timedOut = false;
    let disposed = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 15000);
    async function load() {
      try {
        const response = await fetch(url, { signal: controller.signal });
        if (!response.ok) throw new Error(`姿态坐标读取失败（${response.status}），请重新加载。`);
        const data = await response.json() as PoseData;
        if (!Array.isArray(data.pose_2d) || !Array.isArray(data.pose_3d) || !Number.isFinite(data.fps) || data.fps <= 0) {
          throw new Error("姿态文件格式不完整，请重新加载或重新处理该视频。");
        }
        if (!disposed && !controller.signal.aborted) setLoaded({ url, data, error: "" });
      } catch (error) {
        if (!disposed && (!controller.signal.aborted || timedOut)) setLoaded({ url, data: null, error: timedOut
          ? "姿态坐标读取超时，请重新加载。"
          : error instanceof TypeError ? "无法连接姿态文件，原片仍可观看。请重新加载坐标。" : getErrorMessage(error) });
      } finally { clearTimeout(timer); }
    }
    void load();
    return () => { disposed = true; clearTimeout(timer); controller.abort(); };
  }, [url, attempt]);
  const retry = () => { setLoaded(null); setAttempt((value) => value + 1); };
  if (!url) return { data: null, state: "empty", error: "", retry };
  if (loaded?.url !== url) return { data: null, state: "loading", error: "", retry };
  if (loaded.error) return { data: null, state: "error", error: loaded.error, retry };
  const data = loaded.data;
  return { data, state: data && (data.pose_2d.length || data.pose_3d.length) ? "ready" : "empty", error: "", retry };
}

function PoseFeedback({ resource }: { resource: PoseResource }) {
  if (resource.state === "ready") return null;
  return <DataFeedback compact state={resource.state}
    title={resource.state === "loading" ? "姿态载入中" : resource.state === "error" ? "姿态载入失败" : "暂无姿态"}
    description={resource.state === "error" ? resource.error : undefined}
    onRetry={resource.state === "error" ? resource.retry : undefined} actionLabel="重试" />;
}

function Head({
  k,
  t,
}: {
  k: string;
  t: string;
}) {
  return (
    <header className={`head catalogue-opening${k === "动作分析" ? " catalogue-opening--compact" : ""}`}>
      <div className="catalogue-opening__copy">
      <h1>{t}</h1>
      </div>
      {k === "数字资源库" && <div className="catalogue-bookmark" aria-hidden="true"><DanceIcon name="archive" selected /></div>}
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

function Vid({ t, m, s, empty = "等待处理结果", videoRef, onPlay, onPause, onTimeUpdate, onDurationChange }: {
  t: string; m: string; s: string; empty?: string;
  videoRef?: RefObject<HTMLVideoElement | null>;
  onPlay?: () => void; onPause?: () => void;
  onTimeUpdate?: (time: number) => void;
  onDurationChange?: (duration: number) => void;
}) {
  const localRef = useRef<HTMLVideoElement>(null);
  const ref = videoRef || localRef;
  const [media, setMedia] = useState<{ source: string; state: "ready" | "error"; message?: string } | null>(null);
  useEffect(() => {
    const video = ref.current;
    // SSR media may finish loading before React subscribes to loadeddata.
    if (s && video?.readyState && video.readyState >= 2) setMedia({ source: s, state: "ready" });
    else if (s && video?.error) setMedia({ source: s, state: "error", message: "原片读取失败，请重新读取原片或选择其他视频。" });
  }, [s, ref]);
  const state = media?.source === s ? media.state : "loading";
  return <figure className="vid">
    <figcaption><span><b>{t}</b>{m ? <small>{m}</small> : null}</span><em>{s ? state === "ready" ? "原片" : state === "error" ? "未载入" : "载入中" : "待处理"}</em></figcaption>
    {s ? <>
      <video ref={ref} className="sync" src={s} muted loop playsInline controls
        onLoadedData={() => setMedia({ source: s, state: "ready" })}
        onError={(event) => {
          const code = event.currentTarget.error?.code;
          setMedia({ source: s, state: "error", message: code === 3 || code === 4
            ? "浏览器无法解码此视频，请确认 MP4 / WebM 格式或选择其他视频。"
            : "无法读取原片，请检查资料服务连接或重新选择视频。" });
          onPause?.();
        }}
        onPlay={onPlay} onPause={onPause} onEnded={onPause}
        onTimeUpdate={(event) => onTimeUpdate?.(event.currentTarget.currentTime)}
        onDurationChange={(event) => onDurationChange?.(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)} />
      {state !== "ready" && <DataFeedback compact state={state}
        title={state === "error" ? "原片载入失败" : "原片载入中"}
        description={state === "error" ? media?.message : undefined}
        onRetry={state === "error" ? () => { setMedia(null); ref.current?.load(); } : undefined} actionLabel="重试" />}
    </> : <div className="vid-empty" role="status">
      <DanceIcon name={t === "原始影像" ? "stage" : t.includes("三维") ? "depth" : "movement"} size="empty" selected />
      <b>{empty}</b>
    </div>}
  </figure>;
}

function Pose2DCanvas({
  videoRef,
  data,
  active,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  data: PoseData;
  active: boolean;
}) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!active) return;

    const draw = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;

      if (
        !video ||
        !canvas ||
        video.readyState < 2 ||
        data.pose_2d.length === 0
      ) {
        return;
      }

      const context =
        canvas.getContext("2d");

      if (!context) {
        return;
      }

      const scale = Math.min(window.devicePixelRatio || 1, 2) * Math.max(1, Math.min(canvas.clientWidth / data.width, canvas.clientHeight / data.height));
      const width = Math.round(data.width * scale), height = Math.round(data.height * scale);
      if (canvas.width !== width) canvas.width = width;
      if (canvas.height !== height) canvas.height = height;
      context.setTransform(scale, 0, 0, scale, 0, 0);
      context.clearRect(0, 0, data.width, data.height);
      context.drawImage(video, 0, 0, data.width, data.height);

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

    };

    const video = videoRef.current;
    if (video) {
      const stop = observeVideoFrames(video, draw, active);
      const observer = new ResizeObserver(draw);
      if (canvasRef.current) observer.observe(canvasRef.current);
      return () => { stop(); observer.disconnect(); };
    }
  }, [active, data, videoRef]);

  return (
    <figure className="vid">
      <figcaption>
        <span>
          <b>二维骨架</b>
        </span>

        <em>同步</em>
      </figcaption>

      <canvas
        ref={canvasRef}
        className="pose-canvas"
        style={{
          background: "#07191d",
        }}
      />
    </figure>
  );
}

function Pose3DCanvas({
  videoRef,
  data,
  active,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  data: PoseData;
  active: boolean;
}) {
  const canvasRef =
    useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!active) return;
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

      const scaleFactor = Math.min(window.devicePixelRatio || 1, 2) * Math.max(1, Math.min(canvas.clientWidth / canvasWidth, canvas.clientHeight / canvasHeight));
      const pixelWidth = Math.round(canvasWidth * scaleFactor), pixelHeight = Math.round(canvasHeight * scaleFactor);
      if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
      if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
      context.setTransform(scaleFactor, 0, 0, scaleFactor, 0, 0);

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

    };

    const video = videoRef.current;
    if (video) {
      const stop = observeVideoFrames(video, draw, active);
      const observer = new ResizeObserver(draw);
      if (canvasRef.current) observer.observe(canvasRef.current);
      return () => { stop(); observer.disconnect(); };
    }
  }, [active, data, videoRef]);

    return (
    <figure className="vid">
      <figcaption>
        <span>
          <b>估计三维姿态</b>

        </span>

        <em>同步</em>
      </figcaption>

      <canvas
        ref={canvasRef}
        className="pose-canvas"
        style={{
          background: "#07191d",
        }}
      />
    </figure>
  );
}

function Studio({
  selectedDance,
  onNarrationSaved,
  active,
  selectionRevision,
}: {
  selectionRevision: number;
  selectedDance: DanceRecord | null;
  onNarrationSaved: (danceId: string, narration: string) => void;
  active: boolean;
}) {
  const [play, setPlay] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [compact, setCompact] = useState(false);
  const session = useUploadSession();
  const { source, name: file, job, busy, reset } = session;
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});
  const saveControllers = useRef(new Set<AbortController>());
  const danceId = selectedDance?.dance_id || "";
  const previousDanceId = useRef(danceId);
  const previousRevision = useRef(selectionRevision);
  const narrationDraft = drafts[danceId] ?? selectedDance?.narration ?? "";
  const narrationSaving = Boolean(saving[danceId]);
  const narrationMessage = messages[danceId] || "";
  const masterVideoRef = useRef<HTMLVideoElement>(null);
  const poseResource = usePoseData(job);
  const datasetPoseResource = usePoseData(selectedDance?.pose_data_url ? {
    status: "completed", artifact_urls: { pose_data: selectedDance.pose_data_url },
  } : null);
  const poseData = poseResource.data;
  const datasetPoseData = datasetPoseResource.data;
  const currentPoseResource = file ? poseResource : datasetPoseResource;
  const currentPose = file ? poseData : datasetPoseData;

  useEffect(() => {
    if (previousRevision.current !== selectionRevision || (previousDanceId.current && previousDanceId.current !== danceId)) {
      reset(job ? "样本已切换，旧任务可能仍在运行" : "", true);
    }
    previousDanceId.current = danceId;
    previousRevision.current = selectionRevision;
  }, [danceId, selectionRevision, job, reset]); // Navigation never changes this identity.
  useEffect(() => { const controllers = saveControllers.current; return () => controllers.forEach((controller) => controller.abort()); }, []);

  async function saveNarration() {
    if (!selectedDance || saving[danceId]) return;
    const id = selectedDance.dance_id;
    const draft = narrationDraft;
    const controller = new AbortController();
    saveControllers.current.add(controller);
    setSaving((current) => ({ ...current, [id]: true }));
    setMessages((current) => ({ ...current, [id]: "" }));
    try {
      const response = await fetch(`${API}/api/dances/${encodeURIComponent(id)}/narration`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ narration: draft }), signal: controller.signal,
      });
      const result = await response.json() as { detail?: string };
      if (controller.signal.aborted) return;
      if (!response.ok) throw new Error(result.detail || "解说保存失败，请重试。");
      onNarrationSaved(id, draft);
      setMessages((current) => ({ ...current, [id]: "已保存到当前舞蹈记录" }));
    } catch (error) {
      if (!controller.signal.aborted) setMessages((current) => ({ ...current, [id]: error instanceof TypeError ? "资料服务未连接，草稿已保留，请恢复连接后再次保存。" : getErrorMessage(error) }));
    } finally {
      saveControllers.current.delete(controller);
      if (!controller.signal.aborted) setSaving((current) => ({ ...current, [id]: false }));
    }
  }
  const metrics = job?.metrics;

  const original =
    source ||
    (selectedDance?.has_video
      ? selectedDance.video_url ||
        `${API}/api/dances/${encodeURIComponent(
          selectedDance.dance_id,
        )}/video`
      : selectedDance ? "" : "/media/qiang-demo.mp4");

  useEffect(() => {
    // The native video can load before hydration; read its current state once.
    const timer = setTimeout(() => {
      const video = masterVideoRef.current;
      if (!video) return;
      setDuration(Number.isFinite(video.duration) ? video.duration : 0);
      setCurrentTime(video.currentTime);
      setPlay(!video.paused);
    }, 0);
    return () => clearTimeout(timer);
  }, [original]);

  const toggle = () => {
    const video = masterVideoRef.current;
    if (!video) return;
    if (video.paused) void video.play().catch(() => setPlay(false));
    else video.pause();
  };
  const formatTime = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${Math.floor(seconds % 60).toString().padStart(2, "0")}`;

  const { playError } = useVideoSession(masterVideoRef, original, active, true);
  const upload = (selectedFile?: File) => {
    if (selectedFile) setCompact(true);
    return session.upload(selectedFile);
  };

  return (
    <div className="stack page-studio" data-workbench="upgraded">
      <WorkbenchHeader compact={compact} onToggle={() => setCompact((current) => !current)} busy={busy}
        onUpload={upload} currentLabel={file ? "学习者上传视频" : selectedDance?.name || "本地演示片段"} />
      {session.notice && <DataFeedback compact state="empty" title={session.notice} />}
      {session.monitorError && <DataFeedback compact state="error" title="进度未连接" description={session.monitorError} onRetry={session.retryMonitor} actionLabel="重连任务" />}
      {job?.status === "failed" && <DataFeedback compact state="error" title="处理失败" description={job.message} onRetry={() => session.retryUpload()} actionLabel="重新上传" />}

      {job && <TaskProgress job={job} name={file || "上传任务"} disconnected={Boolean(session.monitorError)} active={active} />}

      <section className="viewer" data-layout="interactive" data-pose-state={currentPoseResource.state === "ready" ? "ready" : "empty"}>
        <header>
          <div>
            <code>
              {file ? "USER" : selectedDance?.dance_id || "DEMO"}
            </code>

            <p>
              <b>
                {file
                  ? "学习者上传视频"
                  : selectedDance
                    ? `${selectedDance.ethnic_group || "民族待补充"} · ${selectedDance.name}`
                    : "演示片段"}
              </b>

              <small>
                {metrics
                  ? `${metrics.duration_seconds} 秒 · ${metrics.frames} 帧 · ${metrics.fps} FPS`
                  : duration ? `${duration.toFixed(2)} 秒 · ${selectedDance ? "示范影像" : "播放器体验"}` : "正在读取影像"}
              </small>
            </p>
          </div>


        </header>

        <div className="timeline">
          <button onClick={toggle} disabled={!original}>
            {play ? <Pause /> : <Play />}
            {play ? "暂停" : "播放"}
          </button>
          <div className="timeline__seek">
            <p>
              <span>{formatTime(currentTime)}</span>
              <b>{currentPoseResource.state === "ready" ? "姿态就绪"
                : currentPoseResource.state === "loading" ? "姿态载入中"
                : currentPoseResource.state === "error" ? "姿态载入失败"
                : busy ? "处理中" : selectedDance?.name || "演示片段"}</b>
              <span>{formatTime(duration)}</span>
            </p>
            <input type="range" aria-label="同步播放进度" min={0} max={duration || 0} step="0.05" value={Math.min(currentTime, duration)} disabled={!duration}
              style={{ "--seek-progress": `${duration ? Math.min(currentTime / duration, 1) * 100 : 0}%` } as CSSProperties}
              onChange={(event) => { const next = Number(event.target.value); if (masterVideoRef.current) masterVideoRef.current.currentTime = next; setCurrentTime(next); }} />
          </div>
        </div>

        <MediaDeck active={active} ready={{ original: Boolean(original), pose2d: Boolean(currentPose?.pose_2d.length), pose3d: Boolean(currentPose?.pose_3d.length) }} media={{
          original: (
          <Vid
            t="原始影像"
            m=""
            s={original}
            videoRef={masterVideoRef}
            onPlay={() => setPlay(true)}
            onPause={() => setPlay(false)}
            onTimeUpdate={setCurrentTime}
            onDurationChange={setDuration}
          />),
          pose2d: currentPose?.pose_2d.length ? <Pose2DCanvas videoRef={masterVideoRef} data={currentPose} active={active} />
            : <Vid t="二维骨架" m="" s="" empty={currentPoseResource.state === "loading" ? "载入中" : currentPoseResource.state === "error" ? "载入失败" : busy ? "处理中" : "暂无二维姿态"} />,
          pose3d: currentPose?.pose_3d.length ? <Pose3DCanvas videoRef={masterVideoRef} data={currentPose} active={active} />
            : <Vid t="估计三维姿态" m="" s="" empty={currentPoseResource.state === "loading" ? "载入中" : currentPoseResource.state === "error" ? "载入失败" : busy ? "处理中" : "暂无三维姿态"} />,
        }} />

        {(currentPoseResource.state === "loading" || currentPoseResource.state === "error" || job?.status === "completed") && <PoseFeedback resource={currentPoseResource} />}
        {playError && <DataFeedback compact state="empty" title={playError} />}
        {file && <Button variant="outline" type="button" onClick={() => session.reset("已返回当前样本", true)}>返回样本</Button>}
        {!file && selectedDance?.description && <div className="viewer-note"><small>{selectedDance.description}</small></div>}
      </section>

      {!file && selectedDance && (
        <section className="cols single narration-section">
          <Card c="narration-document">
            <div className="title">
              <span>
                <h2>动作解说</h2>
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
                <li>暂无解说</li>
              )}
            </ul>

            <label className="narration-editor">
              <span>编辑解说</span>
              <textarea
                value={narrationDraft}
                onChange={(event) => setDrafts((current) => ({ ...current, [danceId]: event.target.value }))}
                rows={5}
                placeholder="填写动作解说，每行一段"
              />
            </label>
            <div className="narration-save">
              <Button
                type="button"
                onClick={() => void saveNarration()}
                disabled={narrationSaving}
              >
                {narrationSaving ? "保存中…" : "保存解说"}
              </Button>
              {narrationMessage && <small role="status">{narrationMessage}</small>}
            </div>

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
  onRetry,
}: {
  records: DanceRecord[];
  selectedDanceId: string;
  loading: boolean;
  error: string;
  onSelectDance: (danceId: string) => void;
  onCompare: (danceId: string) => void;
  onRetry: () => void;
}) {
  const [query, setQuery] =
    useState("");

  const filtered = records.filter((record) => [record.dance_id, record.name, record.ethnic_group || "", record.region || "", record.review_status_text || ""]
    .join(" ").toLowerCase().includes(query.trim().toLowerCase()));

  return (
    <div className="stack page-library">
      <Head
        k="数字资源库"
        t="舞蹈资源库"
      />

      <label className="search">
        <Search />

        <input
          value={query}
          onChange={(event) =>
            setQuery(event.target.value)
          }
          aria-label="搜索舞蹈、民族或地区"
          placeholder="搜索舞蹈、民族或地区"
        />
      </label>

      {loading ? <DataFeedback state="loading" title="资料载入中" />
        : error ? <DataFeedback state="error" title="资料未连接" description={records.length ? "显示上次读取的资料" : "暂时无法读取舞蹈资料"} onRetry={onRetry} actionLabel="重试" />
        : records.length === 0 ? <DataFeedback state="empty" title="暂无资料" />
        : filtered.length === 0 ? <DataFeedback state="no-match" title="无匹配资料" onRetry={() => setQuery("")} actionLabel="清除筛选" />
        : <p className="muted" role="status">{query.trim() ? `找到 ${filtered.length} / ${records.length} 条匹配记录` : `共 ${records.length} 条舞蹈记录`}</p>}

      <section className="archive" aria-label="舞蹈资料目录">
        {filtered          .map((record) => (
            <ResourceRow key={record.dance_id} record={record}
              selectedDanceId={selectedDanceId}
              onSelectDance={onSelectDance} onCompare={onCompare} />
          ))}
      </section>

    </div>
  );
}

function Analysis({ records, selectedDance, onSelectDance, loading, error, onRetry, active, selectionRevision }: {
  records: DanceRecord[]; selectedDance: DanceRecord | null;
  onSelectDance: (danceId: string) => void;
  loading: boolean; error: string; onRetry: () => void; active: boolean; selectionRevision: number;
}) {
  const session = useUploadSession();
  const { source, name, job, busy, reference: taskReference, reset } = session;
  const videoRef = useRef<HTMLVideoElement>(null);
  const poseResource = usePoseData(job);
  const poseData = poseResource.data;
  const metrics = job?.metrics;
  const danceId = selectedDance?.dance_id || "";
  const previousDanceId = useRef(danceId);
  const previousRevision = useRef(selectionRevision);
  const { playError } = useVideoSession(videoRef, source, active);
  const [videoError, setVideoError] = useState<{ source: string; message: string } | null>(null);
  useEffect(() => {
    if ((previousRevision.current !== selectionRevision || (previousDanceId.current && previousDanceId.current !== danceId)) && job) {
      reset("示范已切换，请重新上传；原片已保留，旧任务可能仍在运行");
    }
    previousDanceId.current = danceId;
    previousRevision.current = selectionRevision;
  }, [danceId, selectionRevision, job, reset]);

  const series = metrics?.right_shoulder_angle?.series || [];

  const points = series.map((value, index) => {
    if (value === null || !Number.isFinite(value)) return "";
    const x = series.length <= 1 ? 0 : index / (series.length - 1) * 480;
    const y = 142 - Math.min(180, Math.max(0, value)) / 180 * 118;
    const previous = series[index - 1];
    return `${index === 0 || previous === null || !Number.isFinite(previous) ? "M" : "L"}${x},${y}`;
  }).join(" ");

  const upload = (selectedFile?: File) => session.upload(selectedFile, selectedDance ? {
    danceId: selectedDance.dance_id, name: selectedDance.name, compared: Boolean(selectedDance.has_pose_2d),
  } : null, true);

  return (
    <div className="stack page-analysis">
      <Head
        k="动作分析"
        t="动作分析"
      />

      {loading ? <DataFeedback compact state="loading" title="示范载入中" />
        : error ? <DataFeedback compact state="error" title="示范资料未连接" onRetry={onRetry} actionLabel="重试" />
        : records.length === 0 ? <DataFeedback compact state="empty" title="暂无示范" /> : null}
      {session.notice && <DataFeedback compact state="empty" title={session.notice} />}
      {session.monitorError && <DataFeedback compact state="error" title="进度未连接" description={session.monitorError} onRetry={session.retryMonitor} actionLabel="重连任务" />}
      {job?.status === "failed" && <DataFeedback compact state="error" title="处理失败" description={job.message} onRetry={() => session.retryUpload(true)} actionLabel="重新上传" />}

      <section className="analysis-preparation" aria-label="准备分析">
      <Card c="reference-selection">
        <h2>选择示范</h2>
        <label className="search">
          <DanceIcon name="archive" size="small" selected />
          <select
            aria-label="选择比对示范样本"
            value={selectedDance?.dance_id || ""}
            onChange={(event) => onSelectDance(event.target.value)}
          >
            <option value="">独立分析（不比对）</option>
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
              ? `比对示范：${selectedDance.dance_id}`
              : "示范暂无姿态，仅独立分析"
            : "未绑定示范，仅独立分析"}
        </small>
      </Card>

      <section className="learner-upload">
        <div>
          <h2>
            上传视频
          </h2>

          <label className="upload-control">
            <UploadCloud />
            上传并处理

            <input
              className="upload-file-input"
              aria-label="上传学习者视频"
              type="file"
              accept="video/mp4,video/webm,.mp4,.webm"
              disabled={busy}
              onChange={(event) => { void upload(event.target.files?.[0]); event.target.value = ""; }}
            />
          </label>

          <p className="upload-requirements">MP4 / WebM · ≤300 MiB · 选后即处理</p>

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
            onLoadedData={() => setVideoError(null)}
            onError={(event) => setVideoError({ source, message: [3, 4].includes(event.currentTarget.error?.code || 0)
              ? "浏览器无法解码此视频，请选择可播放的 MP4 / WebM 视频。" : "上传原片读取失败，请重新选择该文件。" })}
          />
        ) : (
          <div className="drop">
            <DanceIcon name="stage" size="empty" selected />
            <b>待上传</b>
          </div>
        )}
      </section>
      {videoError?.source === source && <DataFeedback compact state="error" title="原片无法播放" description={videoError.message}
        onRetry={() => { setVideoError(null); videoRef.current?.load(); }} actionLabel="重试" />}
      {playError && <DataFeedback compact state="empty" title={playError} />}

      </section>

      {job && <TaskProgress job={job} name={name || "独立分析"} disconnected={Boolean(session.monitorError)} active={active} />}

      {job?.status === "completed" && (
        <section className="result-videos">
          {poseData?.pose_2d.length ? <Pose2DCanvas videoRef={videoRef} data={poseData} active={active} /> : null}
          {poseData?.pose_3d.length ? <Pose3DCanvas videoRef={videoRef} data={poseData} active={active} /> : null}
          <PoseFeedback resource={poseResource} />
        </section>
      )}

      <section className="analysis">
        <Card c="wide chart">
          <div className="title">
            <span>
              <h2>右肩展开角度</h2>
            </span>

            <b>
              峰值{" "}
              {metrics
                ?.right_shoulder_angle
                ?.peak ?? "—"}
              °
            </b>
          </div>

          {series.some((value) => value !== null && Number.isFinite(value)) ? <svg viewBox="0 0 480 150" role="img" aria-label="右肩展开角度随视频时间的变化">
            <path
              d={points}
              fill="none"
              stroke="var(--teal)"
              strokeWidth="3"
            />
          </svg> : <div className="chart-empty">待处理</div>}
        </Card>

        <section className="quality-document">
          <h2>识别质量</h2>
          <dl>
            <div><dt>人体检出率</dt><dd>{metrics ? `${metrics.detection_rate}%` : "—"}</dd></div>
            <div><dt>平均置信度</dt><dd>{metrics ? metrics.mean_confidence : "—"}</dd></div>
          </dl>
        </section>

        <section className="structure-band" aria-label="视频结构">
          <h2>视频结构</h2>
          <dl>
            <div><dt>帧数</dt><dd>{metrics ? metrics.frames : "—"}<small> 帧</small></dd></div>
            <div><dt>时长</dt><dd>{metrics ? metrics.duration_seconds : "—"}<small> 秒</small></dd></div>
            <div><dt>帧率</dt><dd>{metrics ? metrics.fps : "—"}<small> FPS</small></dd></div>
          </dl>
        </section>

        <article className="compare">
          <div>
            <h2>
              {job ? taskReference?.compared ? `示范比对 · ${taskReference.danceId}` : "独立分析" : "分析结果"}
            </h2>

            <p>
              {!job ? "待处理" : taskReference?.compared ? metrics?.comparison ? "比对完成" : job.status === "completed" ? "暂无比对结果" : job.status === "failed" ? "比对未完成" : "等待比对结果" : "未进行示范比对"}
            </p>
          </div>

          <div>
            <span>
              时间对齐：
              {metrics?.comparison
                ?.aligned_frames ??
                "—"}{" "}
              帧
            </span>

            <span>
              归一化关节误差：
              {metrics?.comparison
                ?.mean_joint_error_normalized ??
                "—"}
            </span>

            <span>
              右肩平均角度差：
              {metrics?.comparison
                ?.mean_right_shoulder_angle_delta ??
                "—"}
              {metrics?.comparison
                ? "°"
                : ""}
            </span>

          </div>
        </article>
      </section>
    </div>
  );
}

function About({ records, loading, error, onRetry }: { records: DanceRecord[]; loading: boolean; error: string; onRetry: () => void }) {
  const cards = [
    [
      "archive",
      "当前数据",
      [
        `原始视频：${loading ? "载入中" : error ? records.length ? `上次读取 ${records.filter((record) => record.has_video).length} 段` : "—" : `${records.filter((record) => record.has_video).length} 段`}`,
        `二维姿态：${loading ? "载入中" : error ? records.length ? `上次读取 ${records.filter((record) => record.has_pose_2d).length} 段` : "—" : `${records.filter((record) => record.has_pose_2d).length} 段`}`,
        "专业复核：待开展",
      ],
    ],
    [
      "record",
      "提交前检查",
      [
        "肖像与视频授权",
        "代码与模型来源",
        "AI 使用说明",
      ],
    ],
    [
      "depth",
      "内容分级",
      [
        "权威资料可核验",
        "AI 整理附来源",
        "待专业人员复核",
      ],
    ],
  ] as const;

  return (
    <div className="stack page-about">
      <Head
        k="项目与合规"
        t="项目与合规"
      />

      {loading ? <DataFeedback compact state="loading" title="资料载入中" />
        : error ? <DataFeedback compact state="error" title="资料未连接" onRetry={onRetry} actionLabel="重试" />
        : records.length === 0 ? <DataFeedback compact state="empty" title="暂无资料" /> : null}

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
          </div>
        ))}
      </section>

      <section className="about-document">
        {cards.map(
          ([icon, title, lines]) => (
            <Card key={title} c="about-document__section">
              <DanceIcon name={icon} selected />
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
  const [selectionRevision, setSelectionRevision] = useState(0);
  const [replayKey, setReplayKey] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timedOut = false;
    let disposed = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 12000);

    async function loadRecords() {
      try {
        const response = await fetch(`${API}/api/dances`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`舞蹈资源读取失败（${response.status}）`);
        }
        const data = (await response.json()) as DanceRecord[];
        if (disposed || controller.signal.aborted) return;
        if (!Array.isArray(data)) throw new Error("舞蹈资源返回格式不完整，请重新连接资料。");
        setRecords(data);
        setSelectedDanceId((current) =>
          current && data.some((record) => record.dance_id === current)
            ? current
            : data[0]?.dance_id ?? "",
        );
        setRecordsError("");
      } catch (error) {
        if (!disposed && (!controller.signal.aborted || timedOut)) {
          setRecordsError(timedOut ? "资料读取超时" : error instanceof TypeError ? "无法连接本机资料服务" : getErrorMessage(error));
        }
      } finally {
        clearTimeout(timer);
        if (!disposed && (!controller.signal.aborted || timedOut)) setRecordsLoading(false);
      }
    }

    void loadRecords();
    return () => { disposed = true; clearTimeout(timer); controller.abort(); };
  }, [refreshKey]);

  const selectedDance =
    records.find((record) => record.dance_id === selectedDanceId) ?? null;

  function selectDance(danceId: string) {
    if (danceId !== selectedDanceId) setSelectionRevision((current) => current + 1);
    setSelectedDanceId(danceId);
  }
  function retryRecords() { setRecordsLoading(true); setRecordsError(""); setRefreshKey((key) => key + 1); }
  function compareDance(danceId: string) { selectDance(danceId); setView("analysis"); }

  return (
    <div className="shell" data-view={view}>
      <a className="skip-link" href="#main-content">跳至主要内容</a>
      <header className="catalogue-header">
        <div className="catalogue-bar">
          <div className="brand"><Brand compact /></div>
          <nav className="catalogue-nav" aria-label="主要导航">
            {nav.map(
              ([id, title, icon]) => (
                <button
                  className={
                    view === id
                      ? "active"
                      : ""
                  }
                  aria-current={view === id ? "page" : undefined}
                  onClick={() => { setView(id); window.scrollTo({ top: 0, behavior: "instant" }); }}
                  key={id}
                >
                  <DanceIcon name={icon} selected={view === id} />
                  <span>{title}</span>
                </button>
              ),
            )}
          </nav>
          <div className="header-utilities">
            <button type="button" className="replay-intro" onClick={() => setReplayKey((key) => key + 1)}><Play />重温开场</button>
            <Badge variant="outline" className="connection-status" role="status" aria-live="polite">
              <Database />
              {recordsLoading ? "正在连接资料" : recordsError ? "资料未连接" : `${records.filter((record) => record.has_video).length} 段原始视频`}
            </Badge>
          </div>
        </div>
      </header>

      <section className="main">
        <main id="main-content" tabIndex={-1} className="content">
          <div className="module-panel" hidden={view !== "studio"}>
            <Studio active={view === "studio"} selectedDance={selectedDance} selectionRevision={selectionRevision}
              onNarrationSaved={(danceId, narration) => setRecords((current) => current.map((record) => record.dance_id === danceId ? { ...record, narration } : record))} />
          </div>
          <div className="module-panel" hidden={view !== "library"}>
            <Library records={records} selectedDanceId={selectedDanceId} loading={recordsLoading} error={recordsError}
              onSelectDance={selectDance} onCompare={compareDance} onRetry={retryRecords} />
          </div>
          <div className="module-panel" hidden={view !== "analysis"}>
            <Analysis active={view === "analysis"} records={records} selectedDance={selectedDance} selectionRevision={selectionRevision}
              loading={recordsLoading} error={recordsError} onRetry={retryRecords} onSelectDance={selectDance} />
          </div>
          <div className="module-panel" hidden={view !== "about"}>
            <About records={records} loading={recordsLoading} error={recordsError} onRetry={retryRecords} />
          </div>
        </main>

        <nav className="mobile-nav" aria-label="手机导航">
          {nav.map(
            ([id, , icon]) => (
              <button
                className={
                  view === id
                    ? "active"
                    : ""
                }
                aria-current={view === id ? "page" : undefined}
                onClick={() => { setView(id); window.scrollTo({ top: 0, behavior: "instant" }); }}
                key={id}
              >
                <DanceIcon name={icon} selected={view === id} />
                <small>
                  {id === "studio" ? "工作台" : id === "library" ? "资源库" : id === "analysis" ? "动作分析" : "项目说明"}
                </small>
              </button>
            ),
          )}
        </nav>
      </section>
      <BrandIntro replayKey={replayKey} />
    </div>
  );
}
