"use client";

import { useId } from "react";
import { ChevronDown, ChevronUp, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DanceArtwork } from "@/components/dance/ornaments";

export type WorkbenchHeaderProps = {
  compact: boolean;
  onToggle: () => void;
  busy: boolean;
  onUpload: (file?: File) => void | Promise<void>;
  currentLabel?: string;
};

/** The opening scroll stays available while the media workspace is in use. */
export function WorkbenchHeader({
  compact,
  onToggle,
  busy,
  onUpload,
  currentLabel,
}: WorkbenchHeaderProps) {
  const openingId = useId();

  return (
    <section
      className="head studio-head workbench-header"
      data-compact={compact}
      aria-label="民族舞蹈数字化工作台"
    >
      <div id={openingId} className="studio-head__copy workbench-header__copy">
        <div className="workbench-header__heading">
          <h1>
            <span className="heading-phrase">舞蹈影像</span>
            <span className="heading-phrase">数字化</span>
          </h1>
        </div>

        {compact && currentLabel && (
          <p className="workbench-header__current" title={currentLabel}>
            {currentLabel}
          </p>
        )}

        <div className="studio-head__upload">
          <Button asChild>
            <label className="upload-control" aria-label="上传舞蹈视频" aria-disabled={busy}>
              <UploadCloud aria-hidden="true" />
              <span className="workbench-header__upload-full">{busy ? "处理中…" : "上传视频"}</span>
              <span className="workbench-header__upload-compact" aria-hidden="true">{busy ? "处理中" : "上传"}</span>

              <input
                className="upload-file-input"
                aria-label="上传舞蹈视频"
                disabled={busy}
                type="file"
                accept="video/mp4,video/webm,.mp4,.webm"
                onChange={(event) => {
                  const selectedFile = event.target.files?.[0];
                  event.target.value = "";
                  if (selectedFile) void onUpload(selectedFile);
                }}
              />
            </label>
          </Button>
          <p className="upload-guidance" hidden={compact}>
            MP4 / WebM · ≤300 MiB · 选后即处理
          </p>
        </div>
      </div>

      <button
        type="button"
        className="workbench-header__toggle"
        aria-expanded={!compact}
        aria-controls={openingId}
        onClick={onToggle}
      >
        {compact ? <ChevronDown aria-hidden="true" /> : <ChevronUp aria-hidden="true" />}
        {compact ? "展开舞卷" : "收起舞卷"}
      </button>

      {!compact && <DanceArtwork variant="ensemble" />}
    </section>
  );
}
