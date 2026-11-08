"use client";

import Image from "next/image";
import {
  Activity, Aperture, ArrowDownRight, ArrowLeft, ArrowRight, BookOpen,
  Check, ChevronRight, CircleHelp, Compass, Feather, FlaskConical, Focus, HeartHandshake,
  Layers3, LockKeyhole, Menu, MessageCircle, Orbit, Pencil, Sparkles, Star, X,
} from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import {
  type ExperienceCard, type HypothesisFields, type Reflection, type SupportChoice, type SupportOutcome,
  chooseSupport, demoAgent, demoSample, hypothesisKeys, hypothesisLabels,
  maxHypothesisLength, maxInputLength, reviseReflection, saveExperience, supportChoices,
} from "@/lib/agent";
import { CinematicHome } from "./cinematic-home";
import { CaseForgeView } from "./support-views";
import { CinematicCanvas, CinematicArchive } from "./cinematic-reflections";
import { CinematicSignals } from "./cinematic-signals";
import { WorldMedia } from "./world-media";
import { useSupportJourney } from "./use-support-journey";
import { projectReflection } from "../lib/support-presentation";
import type { MemoryReference, SupportResponse } from "../lib/support-types";
import type { AccountSession } from "../lib/account-client";
import { projectProductCard } from "../lib/product-client";
import "./world-pages.css";
import "./agent-connection.css";

const nav = [
  { id: "universe", label: "心象宇宙", icon: Orbit },
  { id: "agent", label: "拾光对话", icon: MessageCircle },
  { id: "canvas", label: "心象画布", icon: Layers3 },
  { id: "signals", label: "身心状态", icon: Activity },
  { id: "archive", label: "成长档案", icon: BookOpen },
] as const;
type MainView = (typeof nav)[number]["id"];
type View = MainView | "caseforge";
const choices = ["keep", "release", "next"] as const;
const choiceIcons = { keep: Star, release: Feather, next: Compass };
const scene = {
  idle: { title: "拾光 · 静水湾", text: "一位在静水湾收集微光的旅伴。", tag: "静水湾", index: "01" },
  proposed: { title: "拾光 · 水面起了涟漪", text: "它把听见的片段摆在水面，等你重新命名。", tag: "等你确认", index: "02" },
  confirmed: { title: "拾光 · 水面清澈了", text: "你给出的理解，让拾光知道该怎样陪你。", tag: "理解已确认", index: "03" },
  keep: { title: "拾光 · 把光留在这里", text: "拾光在湾里留下一盏灯，照着你想带走的部分。", tag: "留下一盏灯", index: "04" },
  release: { title: "拾光 · 让水带走一点", text: "拾光把那片涟漪送向远处，陪你腾出一点空间。", tag: "水面渐静", index: "04" },
  next: { title: "拾光 · 岸边亮了一步", text: "拾光只照亮身前的一小步，什么时候走由你决定。", tag: "照亮下一步", index: "04" },
};

function readView(): View {
  const key = window.location.hash.slice(1);
  return key === "caseforge" || nav.some((item) => item.id === key) ? key as View : "universe";
}

function SceneWave({ state }: { state: keyof typeof scene }) {
  if (state === "idle") return null;
  return <div className="wave-layer" aria-hidden="true" key={state}>
    {[0, 1, 2].map((ring) => <i key={ring} className="scene-wave" data-choice={state} />)}
  </div>;
}

type LoveStoneProps = { liveEnabled: boolean; account?: AccountSession; accountControl?: ReactNode };

export function LoveStone(props: LoveStoneProps) {
  return <LoveStoneWorkspace key={props.account?.user?.id ?? "guest"} {...props} />;
}

function LoveStoneWorkspace({ liveEnabled: productEnabled, account, accountControl }: LoveStoneProps) {
  const [demoMode, setDemoMode] = useState(!productEnabled);
  const liveEnabled = productEnabled && !demoMode;
  const authenticated = !!account?.user && !!account.csrf_token;
  const [view, setView] = useState<View>("universe");
  const journey = useSupportJourney(liveEnabled && authenticated, account);
  const backend = liveEnabled && journey.health?.runtime.psychology_enabled === true;
  const fixture = backend && journey.health?.runtime.psychology_demo_mode === true;
  const connectionReady = !liveEnabled || (authenticated && !!journey.health && backend);
  const [understandingId, setUnderstandingId] = useState<string | null>(null);
  const previousSession = useRef<string | null>(null);
  const [input, setInput] = useState("");
  const [consent, setConsent] = useState(false);
  const [useMemories, setUseMemories] = useState(false);
  const [draft, setDraft] = useState<Reflection | null>(null);
  const [draftMemories, setDraftMemories] = useState<MemoryReference[]>([]);
  const [fields, setFields] = useState<HypothesisFields | null>(null);
  const [outcome, setOutcome] = useState<SupportOutcome | null>(null);
  const [cards, setCards] = useState<ExperienceCard[]>([]);
  const [localPending, setPending] = useState(false);
  const pending = localPending || journey.pending || !!journey.action;
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [supportTexts, setSupportTexts] = useState({ keep: "", release: "", next: "" });
  const [remember, setRemember] = useState(false);
  const saveOperation = useRef<{ fingerprint: string; id: string } | null>(null);
  const [privacy, setPrivacy] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const focusDestination = useRef(false);
  const request = useRef<AbortController | null>(null);
  const main = useRef<HTMLElement>(null);
  const confirmRef = useRef<HTMLHeadingElement>(null);
  const inputField = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const field = inputField.current;
    if (!field || view !== "agent") return;
    field.style.height = "46px";
    field.style.height = `${Math.min(field.scrollHeight, 180)}px`;
  }, [input, view]);

  useEffect(() => {
    if (focusDestination.current) {
      main.current?.focus({ preventScroll: true });
      focusDestination.current = false;
    }
  }, [view]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (menuOpen) {
        setMenuOpen(false);
        document.getElementById("world-menu-toggle")?.focus();
      } else if (privacy) {
        setPrivacy(false);
        document.getElementById("world-privacy-toggle")?.focus();
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [menuOpen, privacy]);

  useEffect(() => {
    const sync = () => setView(readView());
    sync();
    window.addEventListener("hashchange", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      request.current?.abort();
    };
  }, []);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 60);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  useEffect(() => {
    if (!("IntersectionObserver" in window) || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(({ target, isIntersecting }) => {
        if (!isIntersecting) return;
        target.classList.remove("waiting");
        observer.unobserve(target);
      });
    }, { threshold: .08 });
    main.current?.querySelectorAll("[data-reveal]").forEach((element) => {
      if (element.getBoundingClientRect().top < window.innerHeight) return;
      element.classList.add("waiting");
      observer.observe(element);
    });
    return () => observer.disconnect();
  }, [view]);

  function go(next: View) {
    setMenuOpen(false);
    if (next === view) return;
    focusDestination.current = true;
    setPrivacy(false);
    window.location.hash = next;
    setView(next);
    window.scrollTo({ top: 0 });
  }

  // A restored backend understanding populates the existing four-layer canvas.
  useEffect(() => {
    const session = journey.state?.session;
    if (!session || previousSession.current === session.session_id) return;
    previousSession.current = session.session_id;
    const latest = [...(journey.state?.understandings ?? [])].sort((a, b) => b.understanding.updated_at.localeCompare(a.understanding.updated_at))[0];
    const restored = latest ? projectReflection({ understanding: latest, currentInput: "", reply: session.messages.filter((m) => m.role === "assistant").at(-1)?.content ?? "" }) : null;
    setDraft(restored); setDraftMemories([]); setFields(restored?.hypotheses ?? null);
    setUnderstandingId(latest?.understanding.understanding_id ?? null);
    setOutcome(null); setSaved(false); setConsent(false);
  }, [journey.state?.session.session_id]);

  useEffect(() => {
    if (!backend || journey.state?.session.messages.length) return;
    setDraft(null); setDraftMemories([]); setFields(null); setUnderstandingId(null); setOutcome(null); setSaved(false); setConsent(false);
    setSupportTexts({ keep: "", release: "", next: "" }); setRemember(false);
    saveOperation.current = null;
  }, [backend, journey.state?.session.session_id, journey.state?.session.revision]);

  const linkedUnderstanding = journey.state?.understandings.find((entry) => entry.understanding.understanding_id === understandingId);
  const currentRevision = !understandingId || (!!linkedUnderstanding && ["proposed", "confirmed"].includes(linkedUnderstanding.understanding.status) && linkedUnderstanding.understanding.revision === draft?.revision);
  const latestRoute = journey.response?.session_id === journey.state?.session.session_id && journey.response && journey.response.revision > (journey.state?.session.revision ?? -1)
    ? journey.response.psychology?.result.route : journey.state?.support_route;
  const safety = backend && !!latestRoute && latestRoute !== "routine_support";

  function reloadUnderstanding() {
    const latest = linkedUnderstanding ? projectReflection({ understanding: linkedUnderstanding, currentInput: draft?.input ?? "", reply: draft?.reply ?? "" }) : null;
    setDraft(latest); setFields(latest?.hypotheses ?? null);
    setUnderstandingId(latest ? linkedUnderstanding!.understanding.understanding_id : null);
    setOutcome(null); setSaved(false);
  }

  function applyResponse(result: SupportResponse, text: string) {
    setDraftMemories(result.memory_refs ?? []);
    if (!result.generated_understanding) {
      setDraft(null); setFields(null); setOutcome(null); setUnderstandingId(null);
      setInput((current) => current.trim() === text.trim() ? "" : current);
      if (result.psychology?.result.route === "routine_support") setError("已收到回应，但未收到可确认的四栏理解，请稍后重试。");
      return;
    }
    const next = projectReflection({ understanding: result.generated_understanding, currentInput: text, reply: result.reply });
    if (!next) return;
    setDraft(next); setFields(next.hypotheses); setUnderstandingId(next.id); setOutcome(null); setSaved(false);
    setSupportTexts({ keep: "", release: "", next: "" }); setRemember(false); saveOperation.current = null;
    setInput((current) => current.trim() === text.trim() ? "" : current);
    requestAnimationFrame(scrollToDraft);
  }

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !input.trim() || !connectionReady || (liveEnabled && !consent)) return;
    const controller = new AbortController();
    request.current = controller;
    const text = input.trim();
    const includeMemories = useMemories;
    setUseMemories(false);
    setError(""); setPending(true); setConsent(false);
    try {
      if (liveEnabled) {
        if (!authenticated) throw new Error("请先登录自己的账号，再使用真实支持。");
        if (!backend) throw new Error("支持服务暂时未连接，请重新连接后再试。");
        if (!await journey.ensureSession() || request.current !== controller) return;
        const result = await journey.send({ content: text, request_id: crypto.randomUUID(), model_consent: true, use_memories: includeMemories });
        if (result && request.current === controller) applyResponse(result, text);
      } else {
        const result = await demoAgent.reflect({ text, previous: cards[0] }, controller.signal);
        if (request.current !== controller) return;
        const shown = result;
        if (!shown) return;
        setDraft(shown); setFields(shown.hypotheses); setUnderstandingId(null); setOutcome(null); setSaved(false);
        setInput((current) => current.trim() === text ? "" : current);
        requestAnimationFrame(scrollToDraft);
      }
    } catch (issue) {
      if (!controller.signal.aborted && request.current === controller) setError(issue instanceof Error ? issue.message : "暂时没有收到回复，请重试。");
    } finally {
      if (request.current === controller) { setPending(false); request.current = null; }
    }
  }

  async function retry(same: boolean) {
    if (!consent || !journey.lastAttempt || pending) return;
    if (same && !!journey.lastAttempt.use_memories !== useMemories) return;
    const text = journey.lastAttempt.content;
    const controller = new AbortController();
    request.current = controller;
    setConsent(false); setError(""); setPending(true);
    try { const result = await journey.retry(same, useMemories); if (result && request.current === controller) applyResponse(result, text); }
    catch (issue) { if (request.current === controller) setError(issue instanceof Error ? issue.message : "重试未完成，请稍后再试。"); }
    finally { if (request.current === controller) { setPending(false); request.current = null; } }
  }

  function cancel() {
    if (backend) { request.current = null; setPending(false); if (journey.pending) void journey.stop(); return; }
    request.current?.abort(); request.current = null; setPending(false);
    setError("已停止这次请求。之前完成的内容仍然保留。");
  }

  function scrollToDraft() {
    confirmRef.current?.focus({ preventScroll: true });
    confirmRef.current?.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }

  const dirty = !!draft && !!fields && hypothesisKeys.some((key) => draft.hypotheses[key] !== fields[key]);
  const confirmed = !!draft && draft.status !== "proposed" && !dirty && (!liveEnabled || (backend && !!linkedUnderstanding && linkedUnderstanding.understanding.status === "confirmed" && currentRevision));
  const sceneKey = confirmed && outcome ? outcome.choice : confirmed ? "confirmed" : draft ? "proposed" : "idle";
  const currentScene = scene[sceneKey];

  async function confirm() {
    if (!draft || !fields || pending || !currentRevision || (backend && journey.state?.session.status !== "ACTIVE")) return;
    setError("");
    if (!liveEnabled) {
      try { const result = reviseReflection(draft, fields); setDraft(result); setFields(result.hypotheses); setOutcome(null); setSaved(false); }
      catch (issue) { setError(issue instanceof Error ? issue.message : "当前理解未能确认。"); }
      return;
    }
    if (!backend || !authenticated) { setError("请先连接自己的账号支持服务，再确认理解。"); return; }
    setPending(true);
    try {
      if (!hypothesisKeys.some((key) => fields[key].trim())) throw new Error("请至少保留一栏内容，再确认当前理解。");
      const summary = hypothesisKeys.map((key) => `${hypothesisLabels[key]} · ${Array.from(fields[key].trim()).slice(0, 200).join("")}`).join("\n");
      const confirmedView = await journey.commitUnderstanding(summary, linkedUnderstanding, {
        facts: fields.facts.trim(), interpretation: fields.interpretation.trim(), emotions: fields.emotion.trim(), needs: fields.needs.trim(),
      });
      if (!confirmedView) return;
      const result = projectReflection({ understanding: confirmedView, currentInput: draft.input, reply: draft.reply, createdAt: draft.createdAt });
      if (!result) return;
      setDraft(result); setFields(result.hypotheses); setUnderstandingId(confirmedView.understanding.understanding_id); setOutcome(null); setSaved(false);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "当前理解未能确认。"); }
    finally { setPending(false); }
  }

  function selectSupport(choice: SupportChoice) {
    if (!draft || !confirmed || safety) return;
    setOutcome(liveEnabled ? {
      choice, reflectionId: draft.id, reflectionRevision: draft.revision,
      response: `你选择了「${supportChoices[choice].label}」。用自己的话，为这段经历留一点记录。`,
      action: "",
    } : chooseSupport(draft, choice));
    setSaved(false);
  }

  async function save() {
    if (!draft || !outcome || !confirmed) return;
    if (liveEnabled) {
      if (!backend || !authenticated) return;
      if (!linkedUnderstanding || !journey.state || !supportTexts[outcome.choice].trim()) return;
      const body = {
        session_id: journey.state.session.session_id,
        understanding_id: linkedUnderstanding.understanding.understanding_id,
        expected_revision: linkedUnderstanding.understanding.revision,
        choice: outcome.choice, keep_text: supportTexts.keep.trim(), release_text: "",
        next_step: supportTexts.next.trim(), remember_for_future: remember,
      };
      const fingerprint = JSON.stringify(body);
      if (saveOperation.current?.fingerprint !== fingerprint) saveOperation.current = { fingerprint, id: crypto.randomUUID() };
      const card = await journey.saveCard({ ...body, operation_id: saveOperation.current.id });
      if (card) setSaved(true);
      return;
    }
    const card = saveExperience(draft, outcome);
    setCards((current) => [card, ...current.filter((item) => item.id !== card.id)]);
    setSaved(true);
  }

  async function clearSession() {
    if (liveEnabled && journey.state && !await journey.clear()) return;
    request.current?.abort();
    request.current = null;
    setPending(false);
    setUnderstandingId(null);
    setInput("");
    setConsent(false);
    setDraft(null);
    setDraftMemories([]);
    setFields(null);
    setOutcome(null);
    setCards([]);
    setError("");
    setSaved(false);
    setPrivacy(false);
    go("universe");
  }

  function switchMode() {
    request.current?.abort(); request.current = null; setPending(false);
    setDraft(null); setDraftMemories([]); setFields(null); setOutcome(null); setUnderstandingId(null); setSaved(false); setError(""); setConsent(false); setUseMemories(false);
    setSupportTexts({ keep: "", release: "", next: "" }); setRemember(false); saveOperation.current = null;
    setDemoMode((current) => !current);
  }

  const visibleCards = liveEnabled ? journey.cards.map(projectProductCard) : cards;
  const memoryReferences = draft ? draftMemories : journey.response?.memory_refs ?? [];
  const visibleError = error || (liveEnabled ? journey.error : "");

  if (view === "universe") return <><CinematicHome onNavigate={go} mainRef={main} />{accountControl && <div className="account-home-control">{accountControl}</div>}</>;

  return (
    <div className={`shell ${view === "caseforge" ? "" : "world-shell"} world-${view}`}>
      <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); main.current?.focus(); }}>跳到主要内容</a>
      <header className="site-header" data-scrolled={scrolled}>
        <div className="header-inner">
          <button type="button" className="brand" aria-label="LoveStone 首页" onClick={() => go("universe")}>
            <span className="brand-mark"><Image src="/mark.svg" width={33} height={33} alt="" priority /></span>
            <span>Love<span>Stone</span></span>
          </button>
          <nav id="world-navigation" aria-label="主导航" className="nav-glass" data-open={menuOpen}>
            {nav.map(({ id, label, icon: Icon }) => (
              <button type="button" key={id} aria-current={view === id ? "page" : undefined} onClick={() => go(id)}>
                <Icon size={15} aria-hidden="true" /><span>{label}</span>
              </button>
            ))}
          </nav>
          <div className="world-header-actions">
            {accountControl}
            <button id="world-privacy-toggle" type="button" className="mode-badge" onClick={() => setPrivacy(!privacy)} aria-expanded={privacy} aria-controls="privacy-info">
              <i /> 演示说明 <CircleHelp size={14} aria-hidden="true" />
            </button>
            <button id="world-menu-toggle" type="button" className="world-menu-toggle" onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-controls="world-navigation" aria-label={menuOpen ? "关闭导航" : "打开导航"}>
              {menuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </header>

      <main id="main-content" ref={main} tabIndex={-1} className="content">
        {privacy && <section id="privacy-info" className="privacy-drawer" aria-label="演示与隐私说明">
          <LockKeyhole size={20} aria-hidden="true" />
          <div><strong>{liveEnabled ? "你的支持空间" : "独立演示空间"}</strong><p>{liveEnabled ? "当前对话用于支持回应。只有主动保存的经历卡进入账号，卡片可单独删除或撤回未来使用。设备用途另行选择。" : "本地模拟理解，使用虚构内容。演示卡片仅保留在本页内存，刷新后清除。"}</p></div>
          <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => void clearSession()}>清空当前记录</button>
          {backend && journey.state?.session.status === "ACTIVE" && <button type="button" className="text-button" disabled={pending} onClick={() => void journey.end()}>结束当前旅程</button>}
          <button type="button" className="icon-button" aria-label="关闭演示说明" onClick={() => setPrivacy(false)}><X size={18} /></button>
        </section>}

        <div key={view} className="view-enter">
          {view === "agent" && <section className="agent-view" aria-labelledby="agent-title">
            <div className="agent-intro-screen">
              <WorldMedia src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260328_115001_bcdaa3b4-03de-47e7-ad63-ae3e392c32d4.mp4" poster="/images/agent-bg.jpg" shift />
              <div className="agent-intro-shade" aria-hidden="true" />
              <div className="agent-intro-content">
                <span className="agent-intro-kicker">LOVESTONE / PERSONAL AGENT</span>
                <h1 id="agent-title" lang="en">A space to be heard.</h1>
                <p className="agent-intro-subtitle">和拾光说说话。<span>不必先整理好自己。</span></p>
                {productEnabled && <div className="input-meta">
                  <strong>{liveEnabled ? "账号支持" : "独立本地演示"}</strong>
                  <button type="button" className="text-button" disabled={pending} onClick={switchMode}>{liveEnabled ? "切换到本地演示" : "切换到账号支持"}</button>
                </div>}
                {liveEnabled && !authenticated && <p className="inline-status" role="status">登录自己的账号后，可以生成理解、确认和保存经历卡。也可以主动选择独立本地演示。</p>}
                <form className="agent-composer-form" onSubmit={generate}>
                  <label htmlFor="story-input" className="sr-only">说说发生了什么</label>
                  <div className="agent-composer">
                    <textarea ref={inputField} id="story-input" rows={1} placeholder="此刻，有什么想说的吗？" maxLength={maxInputLength} value={input} disabled={pending || (liveEnabled && !authenticated)} onChange={(e) => setInput(e.target.value)} />
                    {pending ? <button type="button" className="agent-send" onClick={cancel} aria-label="停止这次请求"><X size={20} /></button>
                      : <button type="submit" className="agent-send" disabled={!input.trim() || (liveEnabled && !consent) || !connectionReady} aria-label="生成理解草稿"><ArrowRight size={22} /></button>}
                  </div>
                  <div className="input-meta">
                    <button type="button" className="text-button" disabled={pending} onClick={() => setInput(demoSample)}><Sparkles size={14} /> 使用虚构示例</button>
                    <span>{input.length} / {maxInputLength}</span>
                  </div>
                  {liveEnabled && authenticated && <label className="consent-box"><input type="checkbox" checked={useMemories} disabled={pending}
                    onChange={(event) => { setUseMemories(event.target.checked); setConsent(false); }} /><span>这次回应使用我已允许未来使用的经历卡记忆。关闭后继续发送会清除本次对话上下文。</span></label>}
                  {liveEnabled && <label className="consent-box"><input type="checkbox" checked={consent} disabled={pending || !authenticated} onChange={(e) => setConsent(e.target.checked)} /><span>{fixture ? "使用这次虚构输入与当前旅程，生成模拟回应。" : `同意将本次内容、当前会话${useMemories ? "和我已允许的经历卡记忆" : ""}发送给模型，生成这次回应。设备用途另行选择。`}</span></label>}
                  <p className="agent-data-note"><LockKeyhole size={12} /> {!liveEnabled ? "本地模拟理解 · 请仅输入虚构内容 · 刷新即清除" : !authenticated ? "登录后使用账号支持" : !connectionReady ? "正在连接支持服务" : fixture ? "模拟回应 · 无真实设备连接 · 仅使用虚构内容" : "理解由你核对 · 回应未经专业审核"}</p>
                  {pending && <p className="inline-status" role="status">拾光正在准备回应…</p>}
                  {visibleError && <p className="inline-status" role="alert">{visibleError}</p>}
                  {liveEnabled && authenticated && !connectionReady && <button type="button" className="text-button" disabled={pending} onClick={() => void journey.refreshAll()}>重新连接</button>}
                  {backend && journey.failedAttempt && !pending && <div className="input-meta"><button type="button" className="text-button" disabled={!consent || !!journey.lastAttempt?.use_memories !== useMemories} onClick={() => void retry(true)}>重取本次结果</button><button type="button" className="text-button" disabled={!consent} onClick={() => void retry(false)}>重新尝试</button></div>}
                </form>
                {backend && journey.response && !draft && <div className="reply"><span><Aperture size={17} />拾光 · 当前回应</span><p>{journey.response.reply}</p></div>}
                {backend && (draft || journey.response) && <details className="agent-history">
                  <summary>本轮提供给模型的经历卡（{memoryReferences.length}）</summary>
                  {memoryReferences.length ? memoryReferences.map((reference) => {
                    const card = journey.cards.find((entry) => entry.card_id === reference.card_id);
                    return <p key={reference.card_id}><strong>{reference.title || (card ? card.fields.facts.slice(0, 60) || "已确认经历卡" : reference.card_id)}</strong> · 版本 {reference.revision}</p>;
                  }) : <p>本轮没有提供经历卡记忆。</p>}
                </details>}
                {backend && !!journey.state?.session.messages.length && <details className="agent-history"><summary>查看本次旅程对话</summary>{journey.state.session.messages.map((message, index) => <p key={index}><strong>{message.role === "user" ? "你" : "拾光"}：</strong>{message.content}</p>)}</details>}
                {liveEnabled && <details className="agent-support-access" open={safety || undefined}><summary><HeartHandshake size={14} />现实支持入口</summary><p>{journey.support.message}</p><ul>{journey.support.actions.map((action) => <li key={action}>{action}</li>)}</ul><small>随时可用，无需先确认画布；不会自动联系他人。</small></details>}
                <p className="agent-intro-promise">拾光会把听见的轻轻放在你面前。<br />哪些理解贴近你，怎样继续，都由你决定。</p>
                <button type="button" className="agent-manifesto" onClick={draft ? scrollToDraft : () => setPrivacy(true)}>{draft ? "继续整理这段经历" : "关于这个空间"} <ArrowRight size={14} /></button>
              </div>
              <div className="agent-orbit-actions" aria-label="继续探索">
                <button type="button" aria-label="回到心象宇宙" onClick={() => go("universe")}><Orbit size={20} /><span>心象宇宙</span></button>
                <button type="button" aria-label="打开心象画布" onClick={() => go("canvas")}><Layers3 size={20} /><span>心象画布</span></button>
                <button type="button" aria-label="打开成长档案" onClick={() => go("archive")}><BookOpen size={20} /><span>成长档案</span></button>
              </div>
            </div>
            {draft && fields && <div className="agent-layout">
              <div className="agent-main">
                {draft && fields && <>
                  <section className="flow-panel reflection-panel" aria-labelledby="draft-title">
                    <div className="panel-head"><span className="step-index">02</span><div><h2 id="draft-title" tabIndex={-1} ref={confirmRef}>看看拾光听见了什么</h2><p>包括「事实」在内，都可以重写、留空或确认。</p></div></div>
                    <div className="reply"><span><Aperture size={17} /> 拾光 · {fixture ? "模拟回应" : draft.source === "fastapi" ? "对话回应，未经专业审核" : "演示回复，未经你确认"}</span><p>{draft.reply}</p></div>
                    <div className="draft-note"><Pencil size={14} /> {liveEnabled ? "这是拾光的待确认理解。包括事实在内，每一栏都可以纠正或留空。" : "模拟理解 · 可修改的假设 · 非诊断"}</div>
                    {backend && !currentRevision && <p role="status">这份理解的来源或版本已变化。<button type="button" className="text-button" disabled={pending} onClick={reloadUnderstanding}>载入当前版本重新核对</button></p>}
                    <div className="field-grid">
                      {hypothesisKeys.map((key) => <label key={key}>
                        <span>{hypothesisLabels[key]}</span>
                        <textarea maxLength={backend ? 1000 : maxHypothesisLength} disabled={pending} value={fields[key]} onChange={(e) => setFields({ ...fields, [key]: e.target.value })} />
                      </label>)}
                    </div>
                    <div className="flow-actions">
                      <button type="button" className="btn btn-secondary" disabled={pending || confirmed || !currentRevision || (backend && journey.state?.session.status !== "ACTIVE")} onClick={() => void confirm()}><Check size={16} /> {confirmed ? "理解已确认" : "确认当前理解"}</button>
                      <small aria-live="polite">{dirty ? "有未确认的修改" : confirmed ? "拾光会用你确认的版本来回应" : "确认后可选择怎样被支持"}</small>
                    </div>
                  </section>

                  {confirmed && !safety && <section className="flow-panel support-panel" aria-labelledby="support-title">
                    <div className="panel-head"><span className="step-index">03</span><div><h2 id="support-title">此刻，希望怎么继续？</h2><p>{liveEnabled ? "为这段经历选择一个方向，用你自己的话记录。" : "你选的方式会改变拾光的回应，以及静水湾接下来的样子。"}</p></div></div>
                    <div className="support-grid" aria-label="支持选择">
                      {choices.map((choice) => { const Icon = choiceIcons[choice]; return <button key={choice} type="button" aria-pressed={outcome?.choice === choice} onClick={() => selectSupport(choice)} disabled={pending}>
                        <Icon size={18} aria-hidden="true" /><strong>{supportChoices[choice].label}</strong><small>{supportChoices[choice].description}</small>
                      </button>; })}
                    </div>
                    {outcome && <div key={outcome.choice} className="outcome" aria-live="polite">
                      <p>{outcome.response}</p>{!backend && <p className="outcome-action"><ArrowDownRight size={16} /> {outcome.action}</p>}
                    </div>}
                    {outcome && backend && <>
                      <div className="field-grid">
                        {choices.map((choice) => <label key={choice}><span>{supportChoices[choice].label}</span><textarea
                          value={supportTexts[choice]} maxLength={maxHypothesisLength} disabled={pending || saved}
                          placeholder={choice === "keep" ? "我想带走的一点理解" : choice === "release" ? "我愿意暂时放下的部分" : "我准备尝试的一小步"}
                          onChange={(event) => { setSupportTexts({ ...supportTexts, [choice]: event.target.value }); setSaved(false); }}
                        /></label>)}
                      </div>
                      <p className="draft-note">放下的文字仅在当前页面使用，不保存到经历卡。</p>
                      <label className="consent-box"><input type="checkbox" checked={remember} disabled={pending || saved} onChange={(event) => { setRemember(event.target.checked); setSaved(false); }} /><span>允许这张经历卡用于我未来的支持对话。之后可在成长档案中撤回。</span></label>
                    </>}
                    {outcome && <div className="flow-actions">
                      <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={pending || saved || (backend && !supportTexts[outcome.choice].trim())}>{saved ? <Check size={16} /> : <BookOpen size={16} />}{saved ? "已保存经历卡" : "保存经历卡"}</button>
                      {saved ? <button type="button" className="text-button" onClick={() => go("archive")}>查看成长档案 <ArrowRight size={15} /></button> : <small>{backend ? "填写当前所选方向，再主动保存到自己的账号。" : "仅留在本页内存，刷新后清除"}</small>}
                    </div>}
                  </section>}
                </>}
              </div>
              <aside className="agent-side" aria-label="拾光与静水湾">
                <div className="side-art" data-scene={sceneKey}>
                  <Image src="/quiet-cove.webp" alt="" fill sizes="(max-width: 830px) 100vw, 335px" />
                  <SceneWave state={sceneKey} />
                  <div className="side-art-content"><span><span className="live-dot" /> {currentScene.tag}</span><h2>{currentScene.title}</h2><p aria-live="polite">{currentScene.text}</p></div>
                </div>
                <div className="side-note"><HeartHandshake size={19} /><div><strong>这一步，由你决定。</strong><p>拾光的回应仅供自我反思。你可以修改任何理解，也可以停在这里。</p></div></div>
                <button type="button" className="text-button back-to-cove" onClick={() => go("universe")}><ArrowLeft size={15} /> 回到静水湾</button>
              </aside>
            </div>}
          </section>}

          {view === "canvas" && <CinematicCanvas draft={backend && !currentRevision ? null : draft} onOpenAgent={() => go("agent")} />}
          {view === "signals" && <CinematicSignals journey={liveEnabled && authenticated ? journey : undefined} onOpenAgent={() => go("agent")} />}
          {view === "archive" && <>
            <CinematicArchive cards={visibleCards} persisted={liveEnabled && authenticated} onOpenAgent={() => go("agent")} />
            {liveEnabled && <section className="flow-panel" aria-label="账号经历卡管理">
              <div className="panel-head"><div><h2>我的已保存经历</h2><p>卡片跟随你的账号保存，未来使用由你逐张选择。</p></div></div>
              {!authenticated ? <p>登录自己的账号后查看经历卡。</p> : <>
                <button type="button" className="text-button" disabled={pending} onClick={() => void journey.refreshCards().catch((issue) => setError(issue instanceof Error ? issue.message : "卡片暂时无法读取。"))}>刷新经历卡</button>
                {visibleError && <p role="alert">{visibleError}</p>}
                {journey.notice && <p role="status">{journey.notice}</p>}
                {!journey.cards.length && <p>还没有已保存的经历卡。确认一段理解，再选择如何继续。</p>}
                {journey.cards.map((card) => <article className="outcome" key={card.card_id}>
                  <h3>{card.fields.facts.slice(0, 60) || "一段已确认的经历"}</h3>
                  <p>{card.keep_text && `留下 · ${card.keep_text}`}</p>
                  <p>{card.release_text && `放下 · ${card.release_text}`}</p>
                  <p>{card.next_step && `向前 · ${card.next_step}`}</p>
                  <label className="consent-box"><input type="checkbox" checked={card.remember_for_future} disabled={pending}
                    onChange={(event) => void journey.setCardMemory(card, event.target.checked)} /><span>允许用于未来支持对话</span></label>
                  <button type="button" className="text-button" disabled={pending} onClick={() => void journey.removeCard(card)}>删除这张经历卡</button>
                </article>)}
              </>}
            </section>}
          </>}
          {view === "caseforge" && <CaseForgeView />}
        </div>
      </main>
      <footer className="site-footer"><div className="footer-inner">
        <span><Focus size={15} /> LoveStone <span className="footer-divider" /> 感受由你命名</span>
        <button type="button" className="text-button" onClick={() => go(view === "caseforge" ? "universe" : "caseforge")}>
          <FlaskConical size={14} /> {view === "caseforge" ? "返回心象宇宙" : "CaseForge · 内部研发"} <ChevronRight size={14} />
        </button>
      </div></footer>
    </div>
  );
}
