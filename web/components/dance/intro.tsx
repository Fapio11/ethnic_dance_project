"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import "./intro.css";

const VIDEO_SRC = "/media/wu-zhihua-intro.mp4";
// The supplied film settles into its logo at 6.6s; its remaining 1.4s is a still hold.
const LOGO_HANDOFF_TIME = 6.65;
const LOGO_HANDOFF_MS = 180;
const LOGO_REVEAL_MS = 1500;

type FallbackReason = "reduced" | "error" | "waiting";
type IntroSession = { id: number; reducedMotion: boolean };
type PortalGeometry = { left: number; top: number; width: number; height: number; scale: number };

function restoreFocus(previous: Element | null) {
  if (previous instanceof HTMLElement && previous !== document.body && previous.isConnected) {
    previous.focus({ preventScroll: true });
    return;
  }
  const main = document.querySelector<HTMLElement>("main");
  if (!main) return;
  const previousTabIndex = main.getAttribute("tabindex");
  main.setAttribute("tabindex", "-1");
  main.focus({ preventScroll: true });
  if (previousTabIndex === null) main.removeAttribute("tabindex");
  else main.setAttribute("tabindex", previousTabIndex);
}

function IntroPlayer({ reducedMotion, onDismiss }: { reducedMotion: boolean; onDismiss: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const enterRef = useRef<HTMLButtonElement>(null);
  const holdTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const waitingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closingRef = useRef(false);
  const transitioningRef = useRef(false);
  const fadeFrameRef = useRef<number | null>(null);
  const audioBlockedRef = useRef(false);
  const [muted, setMuted] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [ending, setEnding] = useState<"handoff" | "reveal" | null>(null);
  const [portal, setPortal] = useState<PortalGeometry | null>(null);
  const [fallback, setFallback] = useState<FallbackReason | null>(reducedMotion ? "reduced" : null);

  const clearWaiting = useCallback(() => {
    if (waitingTimerRef.current !== null) clearTimeout(waitingTimerRef.current);
    waitingTimerRef.current = null;
  }, []);

  const showFallback = useCallback((reason: FallbackReason) => {
    if (closingRef.current || transitioningRef.current) return;
    clearWaiting();
    videoRef.current?.pause();
    setPlaying(false);
    setFallback(reason);
  }, [clearWaiting]);

  const dismiss = useCallback(() => {
    if (closingRef.current) return;
    closingRef.current = true;
    clearWaiting();
    videoRef.current?.pause();
    if (holdTimerRef.current !== null) clearTimeout(holdTimerRef.current);
    if (exitTimerRef.current !== null) clearTimeout(exitTimerRef.current);
    if (fadeFrameRef.current !== null) cancelAnimationFrame(fadeFrameRef.current);
    onDismiss();
  }, [clearWaiting, onDismiss]);

  const measurePortal = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    // Match visible artwork, not the transparent image canvas: film is 960²,
    // film ink bounds are [198,90,772,890], PNG alpha bounds [160,27,1083,1270].
    const width = rect.width * (574 / 960) / (923 / 1230);
    const height = rect.height * (800 / 960) / (1243 / 1278);
    const left = rect.left + rect.width * (198 / 960) - width * (160 / 1230);
    const top = rect.top + rect.height * (90 / 960) - height * (27 / 1278);
    const originX = left + width * .65;
    const originY = top + height * .63;
    const farthestCorner = Math.hypot(
      Math.max(originX, window.innerWidth - originX),
      Math.max(originY, window.innerHeight - originY),
    );
    setPortal({ left, top, width, height, scale: Math.ceil(farthestCorner / (Math.min(width, height) * .15)) + 2 });
  }, []);

  const finishFilm = useCallback(() => {
    if (closingRef.current || transitioningRef.current) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      dismiss();
      return;
    }
    transitioningRef.current = true;
    clearWaiting();
    measurePortal();
    setEnding("handoff");
    // Keep the settled film visible under a brief, aligned artwork crossfade.
    // Let only this intro's audio tail fade; shared workbench playback is untouched.
    const video = videoRef.current;
    const initialVolume = video?.volume ?? 1;
    const start = performance.now();
    const fadeAudio = (now: number) => {
      if (closingRef.current) return;
      const progress = Math.max(0, Math.min(1, (now - start) / LOGO_HANDOFF_MS));
      if (video) video.volume = initialVolume * (1 - progress);
      if (progress < 1) fadeFrameRef.current = requestAnimationFrame(fadeAudio);
      else fadeFrameRef.current = null;
    };
    fadeFrameRef.current = requestAnimationFrame(fadeAudio);
    holdTimerRef.current = setTimeout(() => {
      video?.pause();
      setEnding("reveal");
    }, LOGO_HANDOFF_MS);
    exitTimerRef.current = setTimeout(dismiss, LOGO_HANDOFF_MS + LOGO_REVEAL_MS + 40);
  }, [clearWaiting, dismiss, measurePortal]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || fallback) return;
    let frameId: number | null = null;
    const checkTime = (time: number) => {
      if (time >= LOGO_HANDOFF_TIME) finishFilm();
    };
    const onTimeUpdate = () => checkTime(video.currentTime);
    // Video-frame time keeps the handoff tied to the actual displayed frame,
    // including slow loading or tab suspension, rather than a wall-clock timer.
    const hasVideoFrameCallback = typeof video.requestVideoFrameCallback === "function";
    if (hasVideoFrameCallback) {
      const checkFrame = (_now: number, metadata: VideoFrameCallbackMetadata) => {
        checkTime(metadata.mediaTime);
        if (!closingRef.current && !transitioningRef.current) frameId = video.requestVideoFrameCallback(checkFrame);
      };
      frameId = video.requestVideoFrameCallback(checkFrame);
    } else video.addEventListener("timeupdate", onTimeUpdate);
    return () => {
      video.removeEventListener("timeupdate", onTimeUpdate);
      if (frameId !== null) video.cancelVideoFrameCallback(frameId);
    };
  }, [fallback, finishFilm]);

  useEffect(() => {
    const onResize = () => { if (transitioningRef.current) measurePortal(); };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [measurePortal]);

  useEffect(() => {
    const previousFocus = document.activeElement;
    const dialog = dialogRef.current;
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      dismiss();
    };
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleMotionChange = () => {
      if (!motionPreference.matches) return;
      if (holdTimerRef.current !== null || exitTimerRef.current !== null) dismiss();
      else showFallback("reduced");
    };
    document.addEventListener("keydown", handleEscape);
    motionPreference.addEventListener("change", handleMotionChange);
    return () => {
      document.removeEventListener("keydown", handleEscape);
      motionPreference.removeEventListener("change", handleMotionChange);
      if (holdTimerRef.current !== null) clearTimeout(holdTimerRef.current);
      if (exitTimerRef.current !== null) clearTimeout(exitTimerRef.current);
      if (fadeFrameRef.current !== null) cancelAnimationFrame(fadeFrameRef.current);
      clearWaiting();
      dialog?.close();
      restoreFocus(previousFocus);
    };
  }, [clearWaiting, dismiss, showFallback]);

  useEffect(() => {
    if (fallback) return;
    const previousOverflow = document.body.style.overflow;
    const backgroundVideos = [...document.querySelectorAll<HTMLVideoElement>("main video")].filter((video) => !video.paused);
    backgroundVideos.forEach((video) => video.pause());
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
      backgroundVideos.forEach((video) => { if (video.isConnected) void video.play().catch(() => {}); });
    };
  }, [fallback]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    // A failed or motion-reduced intro becomes a small, non-modal card.
    // The site remains usable even if the animation never loads.
    if (dialog.open) dialog.close();
    if (fallback) dialog.show();
    else dialog.showModal();
    enterRef.current?.focus({ preventScroll: true });
  }, [fallback]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || fallback) return;
    let disposed = false;
    let resumeOnVisible = false;
    // Every opening starts with sound enabled before the first play attempt.
    video.defaultMuted = false;
    video.muted = false;
    video.volume = 1;
    const play = () => {
      clearWaiting();
      waitingTimerRef.current = setTimeout(() => {
        if (!disposed && !document.hidden) showFallback("waiting");
      }, 8000);
      video.play().then(() => {
        // A gesture retry can already be playing when this effect resumes,
        // so it may not emit another playing event to clear the timeout.
        if (!disposed && !video.paused && video.readyState >= HTMLMediaElement.HAVE_FUTURE_DATA) clearWaiting();
      }).catch(async (error: unknown) => {
        if (disposed || closingRef.current || document.hidden) return;
        if (!(error instanceof DOMException) || error.name !== "NotAllowedError") {
          showFallback("error");
          return;
        }
        // Autoplay must never become a choice screen. Retry silently when audio is blocked.
        audioBlockedRef.current = true;
        video.muted = true;
        setMuted(true);
        try {
          await video.play();
          if (!disposed && !video.paused) clearWaiting();
        } catch {
          if (!disposed && !closingRef.current) showFallback("error");
        }
      });
    };
    const handleVisibility = () => {
      if (document.hidden) {
        resumeOnVisible = !video.paused;
        video.pause();
        clearWaiting();
      } else if (resumeOnVisible && !video.ended && !closingRef.current && !transitioningRef.current) {
        resumeOnVisible = false;
        play();
      }
    };
    const restoreAudioOnGesture = (event: Event) => {
      if (!event.isTrusted || !audioBlockedRef.current || video.ended || closingRef.current || transitioningRef.current) return;
      // Explicit controls own their click. Restoring sound before the music
      // button toggles would otherwise enable it and immediately mute it again.
      if (event.target instanceof Element && event.target.closest("button")) return;
      if (event instanceof KeyboardEvent && event.key !== "Enter" && event.key !== " ") return;
      audioBlockedRef.current = false;
      video.muted = false;
      setMuted(false);
      void video.play().catch(() => {
        if (disposed || closingRef.current) return;
        audioBlockedRef.current = true;
        video.muted = true;
        setMuted(true);
        void video.play().catch(() => {});
      });
    };
    if (!document.hidden) play();
    else resumeOnVisible = true;
    document.addEventListener("visibilitychange", handleVisibility);
    document.addEventListener("click", restoreAudioOnGesture, true);
    document.addEventListener("keydown", restoreAudioOnGesture, true);
    return () => {
      disposed = true;
      document.removeEventListener("visibilitychange", handleVisibility);
      document.removeEventListener("click", restoreAudioOnGesture, true);
      document.removeEventListener("keydown", restoreAudioOnGesture, true);
      clearWaiting();
      video.pause();
    };
  }, [clearWaiting, fallback, showFallback]);

  const toggleMusic = () => {
    const video = videoRef.current;
    if (!video || transitioningRef.current) return;
    audioBlockedRef.current = false;
    const nextMuted = !video.muted;
    video.muted = nextMuted;
    setMuted(nextMuted);
    if ((!nextMuted || video.paused) && !video.ended) {
      video.play().catch(() => showFallback("error"));
    }
  };

  const fallbackText = fallback === "reduced"
    ? "已为你减少动态效果。"
    : "片头暂未就绪，网站已可使用。";

  return (
    <dialog
      ref={dialogRef}
      className={`dance-intro${fallback ? " dance-intro--static" : ""}${ending ? " dance-intro--ending" : ""}${ending === "reveal" ? " dance-intro--revealing" : ""}`}
      style={{
        "--intro-reveal-scale": portal?.scale ?? 1,
        "--intro-handoff-duration": `${LOGO_HANDOFF_MS}ms`,
        "--intro-reveal-duration": `${LOGO_REVEAL_MS}ms`,
      } as CSSProperties}
      aria-labelledby="dance-intro-title"
      aria-describedby={fallback ? "dance-intro-status" : undefined}
      onCancel={(event) => { event.preventDefault(); dismiss(); }}
    >
      <link rel="preload" as="image" href="/brand/logo-intro-cutout.png" />
      {ending && portal ? (
        <div className="dance-intro__reveal" aria-hidden="true">
          <div className="dance-intro__portal" style={{ left: portal.left, top: portal.top, width: portal.width, height: portal.height }}>
            <div className="dance-intro__window" />
            <div className="dance-intro__original-logo" />
          </div>
        </div>
      ) : null}
      <div className="dance-intro__surface">
        <header className="dance-intro__header">
          <span className="dance-intro__eyebrow">民族舞数字课堂</span>
          <button className="dance-intro__skip" type="button" onClick={dismiss}>
            {fallback ? "关闭" : "跳过片头"}<span aria-hidden="true"> ×</span>
          </button>
        </header>

        <div ref={stageRef} className="dance-intro__stage">
          <div className={`dance-intro__wordmark${(playing && !fallback) || ending ? " dance-intro__wordmark--hidden" : ""}`}>
            <h2 id="dance-intro-title">舞之华</h2>
            <span>以舞相遇</span>
          </div>
          {!fallback ? (
            <video
              ref={videoRef}
              className={`dance-intro__video${playing && !fallback ? " dance-intro__video--visible" : ""}`}
              src={VIDEO_SRC}
              muted={muted}
              playsInline
              preload="auto"
              disablePictureInPicture
              aria-hidden="true"
              onPlaying={() => { clearWaiting(); setPlaying(true); }}
              onWaiting={() => {
                if (transitioningRef.current) return;
                clearWaiting();
                if (!document.hidden) waitingTimerRef.current = setTimeout(() => showFallback("waiting"), 8000);
              }}
              onEnded={finishFilm}
              onError={() => showFallback("error")}
            />
          ) : null}
        </div>

        {fallback ? <p id="dance-intro-status" className="dance-intro__status">{fallbackText}</p> : null}
        <footer className="dance-intro__footer">
          {!fallback ? (
            <button
              className="dance-intro__music"
              type="button"
              aria-label={muted ? "开启片头音乐" : "关闭片头音乐"}
              aria-pressed={!muted}
              onClick={toggleMusic}
            >
              <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M11 5 6 9H3v6h3l5 4V5Z" />
                {muted ? <path d="m16 9 5 6m0-6-5 6" /> : <><path d="M15 8a6 6 0 0 1 0 8" /><path d="M18 5a10 10 0 0 1 0 14" /></>}
              </svg>
              {muted ? "开启音乐" : "关闭音乐"}
            </button>
          ) : <span className="dance-intro__quiet">欢迎来到舞之华</span>}
          <button ref={enterRef} className="dance-intro__enter" type="button" onClick={dismiss}>
            进入网站 <span aria-hidden="true">↗</span>
          </button>
        </footer>
      </div>
    </dialog>
  );
}

export default function BrandIntro({ replayKey }: { replayKey: number }) {
  const [session, setSession] = useState<IntroSession | null>(null);
  const lastReplayRef = useRef<number | null>(null);
  const sequenceRef = useRef(0);
  const close = useCallback(() => setSession(null), []);

  useEffect(() => {
    // Defer until after hydration; a Strict Mode cleanup cancels the first setup.
    const timer = setTimeout(() => {
      const firstMount = lastReplayRef.current === null;
      const explicitReplay = firstMount ? replayKey > 0 : replayKey > lastReplayRef.current!;
      lastReplayRef.current = replayKey;
      if (!firstMount && !explicitReplay) return;
      // Show on each page load; ordinary module switches keep this component mounted.
      setSession({ id: ++sequenceRef.current, reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches });
    }, 0);
    return () => clearTimeout(timer);
  }, [replayKey]);

  return session ? <IntroPlayer key={session.id} reducedMotion={session.reducedMotion} onDismiss={close} /> : null;
}
