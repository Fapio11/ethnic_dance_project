"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

// The video node remains mounted between modules. Pausing for navigation or a
// hidden browser tab preserves the user's preference, while native controls
// update it. The browser may reject resume; that failure is shown to the user.
export function useVideoSession(videoRef: RefObject<HTMLVideoElement | null>, source: string, active: boolean, initiallyPlaying = false) {
  const preference = useRef(initiallyPlaying);
  const suspended = useRef(!active);
  const [playError, setPlayError] = useState("");

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !source) return;
    let disposed = false;
    const sync = () => {
      suspended.current = !active || document.hidden;
      if (suspended.current) { video.pause(); return; }
      if (preference.current && video.paused) void video.play().catch(() => {
        if (!disposed && active && !document.hidden) setPlayError("点击播放继续");
      });
    };
    const played = () => {
      if (suspended.current) { video.pause(); return; }
      preference.current = true;
      setPlayError("");
    };
    const paused = () => { if (!suspended.current && video.readyState >= 2) preference.current = false; };
    video.addEventListener("play", played);
    video.addEventListener("pause", paused);
    video.addEventListener("loadeddata", sync);
    document.addEventListener("visibilitychange", sync);
    sync();
    return () => {
      disposed = true;
      video.removeEventListener("play", played);
      video.removeEventListener("pause", paused);
      video.removeEventListener("loadeddata", sync);
      document.removeEventListener("visibilitychange", sync);
    };
  }, [active, source, videoRef]);

  return { playError };
}
