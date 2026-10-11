export type PoseData = {
  fps: number;
  frames: number;
  width: number;
  height: number;
  pose_2d: number[][][];
  pose_3d: number[][][];
};

export type Metrics = {
  duration_seconds: number;
  frames: number;
  fps: number;
  detection_rate: number;
  mean_confidence: number;
  right_shoulder_angle?: { mean?: number; peak?: number; series?: Array<number | null> };
  comparison?: { note?: string; aligned_frames?: number; mean_joint_error_normalized?: number; mean_right_shoulder_angle_delta?: number } | null;
};

export type JobState = {
  id?: string;
  status: "uploading" | "queued" | "processing" | "completed" | "failed";
  progress?: number;
  stage?: string;
  message?: string;
  metrics?: Metrics;
  artifact_urls?: Record<string, string>;
};

export type DanceRecord = {
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

export type TaskReference = { danceId: string; name: string; compared: boolean } | null;
