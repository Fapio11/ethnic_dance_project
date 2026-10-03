# Output and caption schema

## Pose arrays

- Raw/filtered 2D: `float32 [T,17,3]`, channels `(x_pixel, y_pixel, confidence)`, COCO-17 order.
- Estimated 3D: `float32 [T,17,3]`, root-relative MotionAGFormer output in Human3.6M-17 order.
- The video frame count, raw 2D `T`, filtered 2D `T`, and estimated 3D `T` must match.
- Filtered and 3D coordinate channels must be finite. Raw 2D may contain `NaN` where no person was detected.

## Caption JSON

The optional OpenAI vision step returns:

- `video_id`: stable video identifier.
- `summary`: concise overall motion summary.
- `scene`: visible setting, camera framing, and number of visible performers.
- `appearance`: visible clothing and props, without inferring identity, ethnicity, or protected traits.
- `motion_segments`: ordered segments with `start_seconds`, `end_seconds`, `description`, `upper_body`, `lower_body`, `torso_and_facing`, `tempo`, and `confidence`.
- `uncertainties`: occlusion, loose clothing, sampling gaps, left/right ambiguity, or other evidence limits.
- `quality_notes`: whether sampled frames are sufficient for the description.

Captions describe only visible evidence in sampled frames plus computed pose statistics. They must not invent named dance styles, cultural identity, audio, intent, or unseen transitions.

