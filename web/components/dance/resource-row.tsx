"use client";

import { useId, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DanceIcon } from "./dance-icon";

export interface ResourceRowRecord {
  dance_id: string;
  name: string;
  ethnic_group?: string | null;
  region?: string | null;
  description?: string | null;
  review_status?: string | null;
  review_status_text?: string | null;
  has_pose_2d?: boolean;
}

interface ResourceRowProps {
  record: ResourceRowRecord;
  selectedDanceId: string;
  onSelectDance: (danceId: string) => void;
  onCompare: (danceId: string) => void;
}

export function ResourceRow({
  record,
  selectedDanceId,
  onSelectDance,
  onCompare,
}: ResourceRowProps) {
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  const selected = selectedDanceId === record.dance_id;
  const description = record.description || "暂无简介";
  const canExpand = description.length > 90;
  const descriptionId = `${id}-description`;
  const titleId = `${id}-title`;
  const poseStatusId = `${id}-pose-status`;

  return (
    <article
      className="resource-row"
      data-selected={selected}
      data-expanded={expanded}
      aria-labelledby={titleId}
    >
      <div className="resource-row__surface">
        <div className="resource-row__masthead">
          <div className="resource-row__emblem" aria-hidden="true">
            <DanceIcon name="archive" size="folio" selected={selected} />
          </div>
          <div className="resource-row__identifier">
            <span className="resource-row__label">编号</span>
            <code>{record.dance_id}</code>
          </div>
          <span className="resource-row__selection" aria-hidden="true">
            {selected ? "当前样本" : ""}
          </span>
        </div>

        <div className="resource-row__body">
          <h2 id={titleId}>{record.name}</h2>
          <p
            id={descriptionId}
            className={`resource-row__description${canExpand && !expanded ? " resource-row__description--collapsed" : ""}`}
          >
            {description}
          </p>
          {canExpand && (
            <button
              type="button"
              className="resource-row__expand"
              aria-expanded={expanded}
              aria-controls={descriptionId}
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? "收起" : "展开"}
            </button>
          )}
        </div>

        <dl className="resource-row__context">
          <div>
            <dt>民族</dt>
            <dd>{record.ethnic_group || "—"}</dd>
          </div>
          <div>
            <dt>地区</dt>
            <dd>{record.region || "—"}</dd>
          </div>
        </dl>

        <div className="resource-row__status">
          <Badge
            className={record.review_status === "verified" ? "verified" : "pending"}
          >
            {record.review_status_text || "待核验"}
          </Badge>
          <span id={poseStatusId} className="resource-row__pose-status">
            {record.has_pose_2d ? "姿态就绪" : "暂无姿态 · 不可比对"}
          </span>
        </div>

        <div className="resource-row__actions">
          <Button
            type="button"
            variant={selected ? "default" : "outline"}
            aria-pressed={selected}
            onClick={() => onSelectDance(record.dance_id)}
          >
            {selected ? "已选用" : "选用"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={!record.has_pose_2d}
            onClick={() => onCompare(record.dance_id)}
            aria-describedby={!record.has_pose_2d ? poseStatusId : undefined}
            title={
              record.has_pose_2d
                ? "选为示范并比对"
                : "需先生成二维姿态"
            }
          >
            动作比对
          </Button>
        </div>
      </div>
    </article>
  );
}
