import type { JobState } from "./dance-types";

export const PROCESS_STEPS = ["上传", "二维提取", "质量修复", "三维估计", "整理结果"];
const STAGES: Record<string, number> = { validating: 0, pose_2d: 1, filtering: 2, pose_3d: 3, summarizing: 4, serializing: 4 };

/** Backend percentages are milestones, not measured byte/frame progress. */
export function taskPresentation(job: JobState, disconnected = false) {
  if (disconnected) return { label: "进度未连接", step: -1, busy: false };
  if (job.status === "failed") return { label: "处理失败", step: -1, busy: false };
  if (job.status === "completed") return { label: "处理完成", step: 5, busy: false };
  if (job.status === "uploading") return { label: "上传中", step: 0, busy: true };
  if (job.status === "queued") return { label: "等待处理", step: -1, busy: true };
  const step = STAGES[job.stage || ""] ?? -1;
  return { label: step === 0 ? "检查视频" : step < 0 ? "处理中" : PROCESS_STEPS[step], step, busy: true };
}
