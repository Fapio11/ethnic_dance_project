import type { JobState } from "./dance-types";

export const DANCE_API = "http://127.0.0.1:8765";

export function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException("请求已停止", "AbortError")); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException("请求已停止", "AbortError")); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, milliseconds);
    signal.addEventListener("abort", abort, { once: true });
  });
}

// Invalidating a scope aborts its I/O and also rejects late responses from transports
// that finish JSON decoding after cancellation.
export function createTaskScope() {
  let generation = 0;
  let current: AbortController | null = null;
  return {
    invalidate() { generation += 1; current?.abort(); current = null; },
    begin() {
      generation += 1;
      current?.abort();
      const controller = new AbortController();
      current = controller;
      const token = generation;
      return { signal: controller.signal, isCurrent: () => generation === token && !controller.signal.aborted };
    },
  };
}

export async function pollDanceJob(id: string, options: {
  signal: AbortSignal;
  isCurrent: () => boolean;
  onUpdate: (job: JobState) => void;
  fetcher?: typeof fetch;
  interval?: number;
}) {
  const { signal, isCurrent, onUpdate, fetcher = fetch, interval = 1600 } = options;
  while (isCurrent()) {
    await abortableDelay(interval, signal);
    if (!isCurrent()) return;
    const response = await fetcher(`${DANCE_API}/api/jobs/${encodeURIComponent(id)}`, { signal });
    if (!response.ok) throw new Error(`无法读取处理进度（${response.status}），可重新连接该任务。`);
    const state = await response.json() as JobState;
    if (!isCurrent()) return;
    onUpdate({ ...state, id: state.id || id });
    if (state.status === "completed" || state.status === "failed") return;
  }
}

// A paused or hidden video draws only when its frame changes; it never owns a
// perpetual rAF. Seeking a paused video still renders the selected pose.
export function observeVideoFrames(video: HTMLVideoElement, draw: () => void, active: boolean) {
  if (!active) return () => {};
  let frame = 0;
  const stop = () => { if (frame) cancelAnimationFrame(frame); frame = 0; };
  const visible = () => typeof document === "undefined" || !document.hidden;
  const update = () => {
    stop();
    if (!visible()) return;
    draw();
    if (!video.paused && !video.ended) frame = requestAnimationFrame(update);
  };
  const events = ["loadeddata", "seeked", "timeupdate", "play", "pause", "ended"];
  events.forEach((event) => video.addEventListener(event, update));
  if (typeof document !== "undefined") document.addEventListener("visibilitychange", update);
  update();
  return () => {
    stop();
    events.forEach((event) => video.removeEventListener(event, update));
    if (typeof document !== "undefined") document.removeEventListener("visibilitychange", update);
  };
}
