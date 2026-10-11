import type { JobState } from "@/lib/dance-types";
import { PROCESS_STEPS, taskPresentation } from "@/lib/task-presentation";
import { DanceIcon } from "./dance-icon";

/** Static artwork is the fallback until the user's clean Seedance clip is supplied. */
export function TaskProgress({ job, name, disconnected = false, active = true }: {
  job: JobState; name: string; disconnected?: boolean; active?: boolean;
}) {
  const state = taskPresentation(job, disconnected);
  return <section className="task-progress" data-state={disconnected ? "disconnected" : job.status} data-active={active}
    aria-label="视频处理状态">
    <div className="task-progress__art" aria-hidden="true"><DanceIcon name="movement" selected /></div>
    <div className="task-progress__body">
      <div className="task-progress__heading"><b title={name}>{name}</b><span role="status" aria-live="polite">{state.label}</span></div>
      <ol className="task-progress__steps" aria-label="处理流程">
        {PROCESS_STEPS.map((label, index) => <li key={label} data-state={index < state.step ? "done" : index === state.step ? "current" : "pending"}
          aria-current={index === state.step ? "step" : undefined}>
          <span className="task-progress__node" aria-hidden="true" /><span>{label}</span>
        </li>)}
      </ol>
      {state.busy && <div className="task-progress__activity" role="progressbar" aria-label={state.label} aria-valuetext="处理中，完成时间未知"><span /></div>}
    </div>
  </section>;
}
