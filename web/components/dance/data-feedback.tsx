import { DanceIcon } from "./dance-icon";
import "./data-feedback.css";

type DataFeedbackProps = {
  state: "loading" | "error" | "empty" | "no-match";
  title: string;
  description?: string;
  onRetry?: () => void;
  actionLabel?: string;
  compact?: boolean;
  className?: string;
};

/** Plain-language data status; the surrounding panel owns its ready content. */
export function DataFeedback({
  state,
  title,
  description,
  onRetry,
  actionLabel = "重试",
  compact = false,
  className = "",
}: DataFeedbackProps) {
  return (
    <div
      className={`data-feedback${compact ? " data-feedback--compact" : ""} ${className}`}
      data-state={state}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      aria-busy={state === "loading"}
    >
      <DanceIcon name={state === "no-match" ? "archive" : "record"} size="small" />
      <div className="data-feedback__copy">
        <p className="data-feedback__title">{title}</p>
        {description ? <p className="data-feedback__description">{description}</p> : null}
      </div>
      {onRetry ? (
        <button className="data-feedback__action" type="button" onClick={onRetry}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
