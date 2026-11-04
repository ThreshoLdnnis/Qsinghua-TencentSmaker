"use client";

import { useEffect, useRef, useState } from "react";
import type Hls from "hls.js";
import "./world-media.css";

type WorldMediaProps = {
  src: string;
  poster: string;
  shift?: boolean;
  position?: "center" | "right";
  className?: string;
};

export function WorldMedia({ src, poster, shift = false, position = "center", className }: WorldMediaProps) {
  const media = useRef<HTMLDivElement>(null);
  const player = useRef<HTMLVideoElement>(null);
  const [showPoster, setShowPoster] = useState(true);

  useEffect(() => {
    const wrapper = media.current;
    if (!wrapper || !player.current) return;
    const video = player.current;

    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const streaming = /\.m3u8(?:[?#]|$)/i.test(src);
    let visible = typeof IntersectionObserver === "undefined";
    let disposed = false;
    let failed = false;
    let sourceAttached = false;
    let ready = false;
    let hls: Hls | undefined;
    let hlsLoading = false;
    video.muted = true;
    setShowPoster(true);

    function shouldPlay() {
      return !disposed && !failed && visible && !document.hidden && !preference.matches;
    }

    function fallBackToPoster() {
      if (disposed || failed) return;
      failed = true;
      video.pause();
      hls?.destroy();
      hls = undefined;
      setShowPoster(true);
    }

    function attachSource() {
      sourceAttached = true;
      if (!streaming || video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = src;
        ready = true;
        return;
      }
      void import("hls.js").then(({ default: HlsClient }) => {
        if (disposed || failed) return;
        if (!HlsClient.isSupported()) {
          fallBackToPoster();
          return;
        }
        hls = new HlsClient({ autoStartLoad: false });
        hls.on(HlsClient.Events.MEDIA_ATTACHED, () => hls?.loadSource(src));
        hls.on(HlsClient.Events.MANIFEST_PARSED, () => {
          ready = true;
          syncPlayback();
        });
        hls.on(HlsClient.Events.ERROR, (_event, data) => {
          if (data.fatal) fallBackToPoster();
        });
        hls.attachMedia(video);
      }).catch(fallBackToPoster);
    }

    function syncPlayback() {
      if (!shouldPlay()) {
        video.pause();
        if (hlsLoading) {
          hls?.stopLoad();
          hlsLoading = false;
        }
        return;
      }
      if (!sourceAttached) attachSource();
      if (!ready || !video.paused) return;
      if (hls && !hlsLoading) {
        hls.startLoad();
        hlsLoading = true;
      }
      void video.play().catch(() => {
        // Keep the poster visible if the browser blocks autoplay.
      });
    }

    function onPlaying() {
      if (!shouldPlay()) {
        video.pause();
        return;
      }
      setShowPoster(false);
    }

    video.addEventListener("playing", onPlaying);
    video.addEventListener("error", fallBackToPoster);
    document.addEventListener("visibilitychange", syncPlayback);
    preference.addEventListener("change", syncPlayback);
    const observer = typeof IntersectionObserver === "undefined" ? undefined : new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting && entry.intersectionRatio >= 0.05;
      syncPlayback();
    }, { threshold: 0.05 });
    observer?.observe(wrapper);
    syncPlayback();

    return () => {
      disposed = true;
      observer?.disconnect();
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("error", fallBackToPoster);
      document.removeEventListener("visibilitychange", syncPlayback);
      preference.removeEventListener("change", syncPlayback);
      video.pause();
      hls?.destroy();
      video.removeAttribute("src");
      video.load();
    };
  }, [src]);

  return (
    <div ref={media} className={["world-media", className].filter(Boolean).join(" ")} data-position={position} data-shift={shift}>
      <div className="world-media-poster" style={{ backgroundImage: `url(${poster})` }} data-visible={showPoster} aria-hidden="true" />
      <video ref={player} className="world-media-video" poster={poster} muted loop playsInline preload="none" aria-hidden="true" />
    </div>
  );
}

export default WorldMedia;
