"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { JobState, TaskReference } from "@/lib/dance-types";
import { createTaskScope, DANCE_API, pollDanceJob } from "@/lib/dance-session-runtime";

export function useUploadSession() {
  const [source, setSource] = useState("");
  const [name, setName] = useState("");
  const [job, setJob] = useState<JobState | null>(null);
  const [reference, setReference] = useState<TaskReference>(null);
  const [monitorError, setMonitorError] = useState("");
  const [notice, setNotice] = useState("");
  const scope = useRef(createTaskScope());
  const fileRef = useRef<File | null>(null);

  useEffect(() => () => { if (source) URL.revokeObjectURL(source); }, [source]);
  useEffect(() => { const current = scope.current; return () => current.invalidate(); }, []);

  const reset = useCallback((message = "", releasePreview = false) => {
    scope.current.invalidate();
    setJob(null);
    setReference(null);
    setMonitorError("");
    setNotice(message);
    if (releasePreview) { setSource(""); setName(""); fileRef.current = null; }
  }, []);

  async function monitor(id: string, run: ReturnType<ReturnType<typeof createTaskScope>["begin"]>) {
    try {
      await pollDanceJob(id, { ...run, onUpdate: setJob });
    } catch (error) {
      if (!run.isCurrent()) return;
      setMonitorError(error instanceof TypeError
        ? "连接中断，任务可能仍在运行"
        : error instanceof Error ? error.message : "进度读取失败");
    }
  }

  async function upload(file?: File, taskReference: TaskReference = null, analysis = false) {
    if (!file) return;
    if (file.size > 300 * 1024 * 1024) { setNotice("视频超过 300 MiB，请换一个文件"); return; }
    const run = scope.current.begin();
    fileRef.current = file;
    setName(file.name);
    setSource(URL.createObjectURL(file));
    setReference(taskReference);
    setMonitorError("");
    setNotice("");
    setJob({ status: "uploading", message: "上传中" });
    const body = new FormData();
    body.append("video", file);
    if (analysis) {
      if (taskReference) body.append("dance_id", taskReference.danceId);
      body.append("compare_with_reference", taskReference?.compared ? "true" : "false");
    }
    try {
      const response = await fetch(`${DANCE_API}/api/jobs`, { method: "POST", body, signal: run.signal });
      const state = await response.json() as JobState & { detail?: string };
      if (!run.isCurrent()) return;
      if (!response.ok) throw new Error(state.message || state.detail || `上传失败（${response.status}）`);
      if (!state.id) throw new Error("后端没有返回任务编号，请重新上传。");
      setJob(state);
      if (state.status !== "completed" && state.status !== "failed") await monitor(state.id, run);
    } catch (error) {
      if (!run.isCurrent()) return;
      setJob({ status: "failed", progress: 0, message: error instanceof TypeError
        ? "处理服务未连接，原片已保留"
        : error instanceof Error ? error.message : "上传失败，请重新上传。" });
    }
  }

  function retryMonitor() {
    const id = job?.id;
    if (!id) return;
    setMonitorError("");
    const run = scope.current.begin();
    void monitor(id, run);
  }

  function retryUpload(analysis = false) { void upload(fileRef.current || undefined, reference, analysis); }

  return { source, name, job, reference, monitorError, notice, upload, reset, retryMonitor, retryUpload,
    busy: Boolean(job && ["uploading", "queued", "processing"].includes(job.status)) };
}
