"use client";

import Image from "next/image";
import { ArrowUpRight, Menu, Play, Sparkles, X } from "lucide-react";
import { motion, useInView } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import "./cinematic-home.css";

export const cinematicVideo = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260306_115329_5e00c9c5-4d69-49b7-94c3-9c31c60bb644.mp4";

type Destination = "universe" | "agent" | "canvas" | "signals" | "archive" | "caseforge";
const links = [
  { id: "universe", label: "心象宇宙" },
  { id: "agent", label: "拾光对话" },
  { id: "canvas", label: "心象画布" },
  { id: "signals", label: "身心状态" },
  { id: "archive", label: "成长档案" },
] as const;
const journeys = [
  { id: "agent", title: "Listen", label: "表达" },
  { id: "canvas", title: "Reflect", label: "理解" },
  { id: "signals", title: "Feel", label: "觉察 · 模拟" },
  { id: "archive", title: "Grow", label: "成长" },
  { id: "agent", title: "Begin", label: "出发" },
] as const;
const loopSteps = [
  { index: "01", title: "Listen", label: "表达", body: "从一件具体的小事开始，不必先把自己说清楚。", destination: "agent" as const },
  { index: "02", title: "Reflect", label: "改写", body: "拾光把理解拆成事实、解释、情绪、需要，你可以逐栏改写。", destination: "canvas" as const },
  { index: "03", title: "Choose", label: "选择", body: "Keep、Release、Next 由你决定；任何理解都不是诊断。", destination: "agent" as const },
  { index: "04", title: "Grow", label: "带走", body: "只有你主动保存的经历卡，才会在未来对话中被再次参考。", destination: "archive" as const },
] as const;
const loopPreview = [
  { eyebrow: "你的一句话", title: "先从一件小事开始", chips: ["我准备好的想法没说完", "会议已经结束"], action: "Listen · 表达", helper: "把感受交给拾光，不必先整理好自己。" },
  { eyebrow: "拾光的待确认理解", title: "四层画布，逐栏可改", chips: ["事实  发生了什么", "解释  可能意味着什么", "情绪  此刻的感受", "需要  想要怎样的支持"], action: "Reflect · 理解", helper: "AI 只提出假设；每一栏都由你确认、留空或改写。" },
  { eyebrow: "你的选择", title: "把下一步交还给自己", chips: ["Keep · 留下", "Release · 放下", "Next · 向前"], action: "Choose · 选择", helper: "不是完成任务，而是选择此刻愿意带走的方向。" },
  { eyebrow: "一张属于你的经历卡", title: "只保存你主动留下的部分", chips: ["已确认的四字段", "Keep / Next 文字", "未来参考：由你开启"], action: "Grow · 带走", helper: "下一次对话只有在你允许时，才会参考这张卡片。" },
] as const;

function BlurHeading({ reduced }: { reduced: boolean }) {
  const ref = useRef<HTMLHeadingElement>(null);
  const seen = useInView(ref, { once: true, amount: .3 });
  const lines = ["A Little Space to Feel.", "A Universe Within."];
  let wordIndex = 0;
  return <h1 ref={ref} id="cinema-title" className="cinema-title" aria-label={lines.join(" ")} lang="en">
    {lines.map((line) => <span className="cinema-title-line" key={line} aria-hidden="true">
      {line.split(" ").map((word) => {
        const index = wordIndex++;
        return <motion.span className="cinema-word" key={word + index}
          initial={reduced ? false : { filter: "blur(10px)", opacity: 0, y: 50 }}
          animate={seen && !reduced ? {
            filter: ["blur(10px)", "blur(5px)", "blur(0px)"],
            opacity: [0, .5, 1], y: [50, -5, 0],
          } : reduced ? { filter: "blur(0px)", opacity: 1, y: 0 } : { filter: "blur(10px)", opacity: 0, y: 50 }}
          transition={reduced ? { duration: 0 } : { duration: .7, delay: index * .1, times: [0, .5, 1] }}
        >{word}{index < 8 ? "\u00a0" : ""}</motion.span>;
      })}
    </span>)}
  </h1>;
}

export function CinematicHome({ onNavigate, mainRef }: {
  onNavigate: (destination: Destination) => void;
  mainRef: RefObject<HTMLElement | null>;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const intro = useRef<HTMLDialogElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const [reduced, setReduced] = useState<boolean | null>(null);
  const enabled = reduced === false;
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeLoop, setActiveLoop] = useState(0);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    const media = video.current;
    if (!media) return;
    const synchronize = () => {
      if (!enabled || document.hidden) {
        media.pause();
      } else {
        void media.play().catch(() => {
          // Keep the poster if the browser blocks autoplay.
        });
      }
    };
    synchronize();
    document.addEventListener("visibilitychange", synchronize);
    return () => {
      document.removeEventListener("visibilitychange", synchronize);
      media.pause();
    };
  }, [enabled]);
  useEffect(() => {
    if (reduced || menuOpen) return;
    const timer = window.setInterval(() => setActiveLoop((current) => (current + 1) % loopSteps.length), 5200);
    return () => window.clearInterval(timer);
  }, [reduced, menuOpen]);

  function navigate(destination: Destination) {
    setMenuOpen(false);
    intro.current?.close();
    onNavigate(destination);
  }

  function showIntro() {
    setMenuOpen(false);
    intro.current?.showModal();
  }

  const reveal = (delay: number) => ({
    initial: reduced ? false as const : { filter: "blur(10px)", opacity: 0, y: 20 },
    animate: { filter: "blur(0px)", opacity: 1, y: 0 },
    transition: { duration: reduced ? 0 : .6, delay: reduced ? 0 : delay },
  });

  return <div className="cinema-home">
    <link rel="preload" as="image" href="/images/hero_bg.jpeg" type="image/jpeg" />
    <a className="skip-link" href="#main-content" onClick={(event) => {
      event.preventDefault(); mainRef.current?.focus();
    }}>跳到主要内容</a>
    <div className="cinema-media" aria-hidden="true">
      <video ref={video} className="cinema-video" src={enabled ? cinematicVideo : undefined}
        autoPlay={enabled} loop muted playsInline
        preload={enabled ? "auto" : "none"} poster="/images/hero_bg.jpeg" />
      <div className="cinema-overlay" />
      <div className="cinema-readability" />
    </div>

    <header className="cinema-nav">
      <button type="button" className="cinema-brand" aria-label="LoveStone 首页" onClick={() => navigate("universe")}>
        <Image src="/mark.svg" alt="" width={48} height={48} priority />
        <span>LoveStone</span>
      </button>
      <nav className="liquid-glass cinema-desktop-nav" aria-label="主导航">
        {links.map(({ id, label }) => <button type="button" key={id} aria-current={id === "universe" ? "page" : undefined}
          onClick={() => navigate(id)}>{label}</button>)}
        <button type="button" className="cinema-nav-cta" onClick={() => navigate("agent")}>开始旅程 <ArrowUpRight size={16} /></button>
      </nav>
      <button ref={toggle} type="button" className="liquid-glass cinema-menu-toggle" aria-expanded={menuOpen}
        aria-controls="cinema-mobile-nav" aria-label={menuOpen ? "关闭导航" : "打开导航"}
        onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={21} /> : <Menu size={21} />}</button>
      {menuOpen && <nav id="cinema-mobile-nav" className="cinema-mobile-nav liquid-glass-strong" aria-label="移动导航"
        onKeyDown={(event) => { if (event.key === "Escape") { setMenuOpen(false); toggle.current?.focus(); } }}>
        {links.map(({ id, label }) => <button key={id} type="button" onClick={() => navigate(id)}>{label}<ArrowUpRight size={15} /></button>)}
        <button type="button" className="cinema-nav-cta" onClick={() => navigate("agent")}>开始旅程 <ArrowUpRight size={16} /></button>
      </nav>}
    </header>

    <div className="cinema-foreground">
      <main id="main-content" ref={mainRef} tabIndex={-1} className="cinema-center" aria-labelledby="cinema-title">
        <motion.div className="liquid-glass cinema-badge" {...reveal(.05)}>
          <span>New</span><span>LoveStone · 你的心象宇宙，从此刻开启</span>
        </motion.div>
        <BlurHeading reduced={!!reduced} />
        <motion.p className="cinema-description" {...reveal(.8)}>
          给感受一点空间，向内探索一整个宇宙。<br />
          与拾光一起，理解此刻的自己，找到属于你的下一步。
        </motion.p>
        <motion.div className="cinema-value-bar" {...reveal(.95)} aria-label="LoveStone核心机制">
          <span>THE LOOP</span><strong>表达 → 理解 → 纠正 → 带走</strong><small>AI 提出假设，你决定什么被记住。</small>
        </motion.div>
        <motion.div className="cinema-actions" {...reveal(1.1)}>
          <motion.button type="button" className="liquid-glass-strong cinema-primary"
            whileHover={reduced ? undefined : { y: -3, scale: 1.025 }}
            whileTap={reduced ? undefined : { scale: .97 }}
            onClick={() => navigate("agent")}>开启心象旅程 <ArrowUpRight size={20} /></motion.button>
          <button type="button" className="cinema-secondary" onClick={showIntro}>认识拾光 <Play size={14} fill="currentColor" /></button>
        </motion.div>
      </main>

      <footer className="cinema-bottom">
        <motion.section className="cinema-loop" {...reveal(1.25)} aria-label="LoveStone核心闭环">
          <div className="cinema-loop-head"><span>一段支持旅程，四个由你掌握的动作</span><small>0{activeLoop + 1} / 04</small></div>
          <motion.div className="cinema-loop-preview" key={loopPreview[activeLoop].action}
            initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .28 }} aria-live="polite">
            <div className="cinema-loop-preview-copy"><span>{loopPreview[activeLoop].eyebrow}</span><strong>{loopPreview[activeLoop].title}</strong><p>{loopPreview[activeLoop].helper}</p></div>
            <div className="cinema-loop-preview-art" aria-hidden="true"><i /><i /><i /></div>
            <div className="cinema-loop-preview-chips">{loopPreview[activeLoop].chips.map((chip) => <span key={chip}>{chip}</span>)}</div>
          </motion.div>
          <div className="cinema-loop-steps">
            {loopSteps.map((step, index) => <button type="button" key={step.index} className={index === activeLoop ? "is-active" : ""}
              aria-current={index === activeLoop ? "step" : undefined}
              onMouseEnter={() => setActiveLoop(index)} onFocus={() => setActiveLoop(index)} onClick={() => navigate(step.destination)}>
              <i>{step.index}</i><span lang="en">{step.title}</span><small>{step.label}</small>
            </button>)}
          </div>
          <motion.p key={loopSteps[activeLoop].index} initial={reduced ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : .35 }}>
            {loopSteps[activeLoop].body}
          </motion.p>
        </motion.section>
        <motion.div className="cinema-journey" {...reveal(1.35)}>
          <span className="liquid-glass cinema-journey-label">每一种感受，都有值得被看见的宇宙</span>
          <nav className="cinema-journey-links" aria-label="探索 LoveStone">
            {journeys.map(({ id, title, label }) => <button type="button" key={title} onClick={() => navigate(id)} aria-label={title + " · " + label}>
              <span lang="en">{title}</span><small>{label}</small>
            </button>)}
          </nav>
        </motion.div>
        <div className="cinema-edge">
          <button type="button" className="cinema-demo-note" onClick={showIntro}>本地演示 · 感受由你命名</button>
        </div>
      </footer>
    </div>

    <dialog ref={intro} className="cinema-intro"
      aria-labelledby="intro-title" onClick={(event) => { if (event.target === event.currentTarget) intro.current?.close(); }}>
      <div className="cinema-intro-inner">
        <button type="button" className="cinema-close" aria-label="关闭拾光介绍" onClick={() => intro.current?.close()}><X size={20} /></button>
        <Image src="/quiet-cove.webp" alt="静水湾中，一颗透着暖光的晶石悬在水面上。" width={600} height={400} />
        <div className="cinema-intro-copy">
          <div className="cinema-intro-eyebrow"><Sparkles size={14} /> MEET YOUR COMPANION</div>
          <h2 id="intro-title">你好，我是拾光。</h2>
          <p>我在静水湾收集微光，也陪你整理那些还没说清的感受。先从一件小事开始；你可以改写我的理解，再选择留住什么、放下什么，或者走出一小步。</p>
          <button type="button" className="btn btn-primary" onClick={() => navigate("agent")}>和拾光聊聊 <ArrowUpRight size={17} /></button>
          <small>当前为演示体验，请使用虚构内容。理解草稿可修改、待确认；独立演示记录刷新后清除，完整产品中只有你主动保存的经历卡会进入账号。</small>
        </div>
      </div>
    </dialog>
  </div>;
}
