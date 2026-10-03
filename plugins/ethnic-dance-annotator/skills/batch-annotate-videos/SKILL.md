---
name: batch-annotate-videos
description: Batch-process local or attached dance videos with the user's RTMPose and MotionAGFormer project, producing COCO-17 2D poses, filtered poses, estimated H36M-17 3D poses, visualization videos, validation logs, and optional OpenAI vision captions. Use for 批量视频标注、批量2D/3D骨架提取、舞蹈视频自动标注、姿态视频生成 or detailed dance-motion captions. Do not use for training new pose models or claiming monocular 3D as motion-capture ground truth.
---

# Batch Dance Video Annotation

Use the deterministic runner at `../../scripts/batch_annotate.py`. The default local project is `D:\ethnic_dance_project` and the expected interpreter is `D:\miniconda\envs\dance3d\python.exe`.

## Workflow

1. Resolve every attached video to an absolute local path. Accept `.mp4`, `.mov`, `.avi`, and `.mkv`; reject ambiguous or missing paths.
2. Run preflight before the first batch or after project changes:

   ```powershell
   D:\miniconda\envs\dance3d\python.exe <plugin-root>\scripts\batch_annotate.py --project D:\ethnic_dance_project --preflight
   ```

3. For local-only pose processing, run the inputs without `--caption`. For example:

   ```powershell
   D:\miniconda\envs\dance3d\python.exe <plugin-root>\scripts\batch_annotate.py --project D:\ethnic_dance_project --inputs <video1> <video2>
   ```

4. Captioning sends sampled video frames to the OpenAI API and may incur charges. Before adding `--caption`, tell the user what will be sent and obtain confirmation unless their current request already explicitly authorizes API captioning. Require `OPENAI_API_KEY`; never print, persist, or request that the key be pasted into chat.
5. For captioning, use:

   ```powershell
   D:\miniconda\envs\dance3d\python.exe <plugin-root>\scripts\batch_annotate.py --project D:\ethnic_dance_project --inputs <video1> --caption
   ```

6. Report each video's status and link its outputs. Do not report success unless shape, frame-count, finiteness, and output-file checks pass.

## Processing invariants

- Treat the input filename stem as `video_id`; only letters, digits, `_`, and `-` are retained.
- Copy external inputs into `data/raw_videos` without overwriting a different existing file.
- Reuse the project's current `extract_pose_2d_rtmpose`, `filter_pose_2d_occlusion.py`, and `extract_pose_3d_motionagformer.py` implementations by overriding their path globals at runtime. Do not edit their hard-coded `VIDEO_ID` values for batch work.
- Preserve raw RTMPose data. The filtered array is a separate artifact.
- Call the 3D result “estimated 3D pose” or `pose_3d_est`, never ground truth or motion-capture data.
- Continue past an individual video failure, log the exact stage and exception, and return a nonzero final exit code when any item fails.
- Default to resume behavior. Use `--force` only when the user explicitly asks to regenerate existing outputs.

## Expected artifacts per video

- `data/raw_videos/<video_id>.<ext>`
- `data/pose_2d/<video_id>_rtmpose.npy`
- `data/pose_2d/<video_id>_rtmpose_filtered.npy`
- `data/pose_3d_est/<video_id>_motionagformer.npy`
- `outputs/pose_visualization/<video_id>_rtmpose.mp4`
- `outputs/pose_visualization/<video_id>_rtmpose_filtered.mp4`
- `outputs/pose_visualization/<video_id>_motionagformer_3d.mp4`
- `outputs/logs/<video_id>_batch.log`
- When captioning is enabled: `data/captions/<video_id>.json` and `<video_id>.md`

Read [references/output-schema.md](references/output-schema.md) only when validating outputs, integrating metadata, or explaining caption fields.

