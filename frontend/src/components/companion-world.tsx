"use client";

import { ArrowUpRight, BookHeart, Globe2, Sparkles, UsersRound } from "lucide-react";
import { useState } from "react";
import "./companion-world.css";

export type CompanionProfile = {
  id: string;
  name: string;
  planet: string;
  constellation: string;
  descriptor: string;
  belief: string;
  color: "rose" | "lilac" | "aqua";
  opening: string;
  values: readonly string[];
  stories: {
    family: string;
    school: string;
    society: string;
  };
};

export const companionProfiles: readonly CompanionProfile[] = [
  {
    id: "shiguang",
    name: "拾光",
    planet: "云岚星",
    constellation: "静水湾 · 第七潮汐",
    descriptor: "会把复杂的心事放到光里慢慢看",
    belief: "每个人都可以先被理解，再决定要往哪里走。",
    color: "rose",
    opening: "我想和拾光说说，今天有一件事让我停不下来。",
    values: ["先理解，再行动", "留白也是答案", "小一步也算向前"],
    stories: {
      family: "拾光的家人会在晚潮前点亮三盏灯：一盏给发生过的事，一盏给还没想明白的事，还有一盏专门留给沉默。",
      school: "云岚星的学校没有“最快长大”的课程。每周，学生会带一件还没有答案的事去上课，和同伴一起练习把它说得更准确。",
      society: "在云岚星，大家相信帮助不是把别人拉到自己的答案里，而是把一条可以回头的路灯留在对方身边。",
    },
  },
  {
    id: "weilan",
    name: "未蓝",
    planet: "弦月环",
    constellation: "北岸学校 · 候鸟区",
    descriptor: "擅长陪你把“我应该”改写成“我现在需要”",
    belief: "温柔不是放弃标准，而是让自己有力气继续。",
    color: "lilac",
    opening: "未蓝，我今天一直在想一件‘应该做到’却没做到的事。",
    values: ["需要可以被说出", "失败不等于身份", "给自己第二种解释"],
    stories: {
      family: "未蓝的家里有一面会变色的墙。每个人回家时可以留下一种颜色，家人先看见颜色，再问发生了什么。",
      school: "弦月环的孩子们会交换“第二种解释”：当一个念头说“只能这样”，同伴会帮它找到另一条不急着下结论的路。",
      society: "那里的人把公共广场叫作“可以重写的地方”。任何人都能把旧告示翻面，写下今天更贴近自己的版本。",
    },
  },
  {
    id: "qiyu",
    name: "栖雨",
    planet: "潮汐森",
    constellation: "灯塔群岛 · 第三航线",
    descriptor: "相信身体的节奏和心里的故事可以一起被听见",
    belief: "信号是线索，不是判决；真正的故事仍然属于你。",
    color: "aqua",
    opening: "栖雨，陪我回看一下这几天的起伏吧。",
    values: ["数字只做线索", "感受由自己命名", "照顾先于证明"],
    stories: {
      family: "栖雨的家人住在潮汐森边，每晚只问一句：“今天哪一个瞬间让你松了一点？”答案可以很小，也可以暂时没有。",
      school: "灯塔群岛的学校会把一天画成一条弯曲的线。孩子们不比较谁更平稳，只练习在转弯处放慢一点。",
      society: "潮汐森把“重新靠岸”看作一种能力。遇到风浪时，大家会互相指路，但不会替对方掌舵。",
    },
  },
];

type StoryKey = keyof CompanionProfile["stories"];
const storyTabs: readonly { key: StoryKey; label: string; icon: typeof UsersRound }[] = [
  { key: "family", label: "家庭", icon: UsersRound },
  { key: "school", label: "学校", icon: BookHeart },
  { key: "society", label: "社会", icon: Globe2 },
];

export function CompanionPortal({
  selected,
  onSelect,
  onInvite,
}: {
  selected: CompanionProfile;
  onSelect: (companion: CompanionProfile) => void;
  onInvite: (companion: CompanionProfile) => void;
}) {
  const [story, setStory] = useState<StoryKey>("family");
  const [invited, setInvited] = useState(false);
  const storyTab = storyTabs.find((item) => item.key === story) ?? storyTabs[0];
  const StoryIcon = storyTab.icon;

  function choose(companion: CompanionProfile) {
    setInvited(false);
    onSelect(companion);
  }

  function invite() {
    setInvited(true);
    onInvite(selected);
  }

  return (
    <section className="companion-portal" aria-labelledby="companion-portal-title">
      <div className="companion-portal-stars" aria-hidden="true"><i /><i /><i /><i /></div>
      <div className="companion-portal-header">
        <span>01 / COMPANION ARRIVAL</span>
        <small>可选择 · 演示角色设定</small>
      </div>
      <div className="companion-portal-grid">
        <div className="companion-portal-copy">
          <p className="companion-kicker"><Sparkles size={13} /> 来自一颗还未命名的星球</p>
          <h2 id="companion-portal-title">先认识一个<br /><em>愿意陪你慢慢走</em>的朋友。</h2>
          <p className="companion-description">他们有自己的家庭、学校和社会，也有一套不急着替你下结论的价值观。故事不是装饰，而是每次支持时可以回到的共同语言。</p>
          <div className="companion-values" aria-label={`${selected.name} 的价值观`}>
            {selected.values.map((value) => <span key={value}>{value}</span>)}
          </div>
        </div>
        <div className={`companion-orb companion-orb-${selected.color}`} aria-label={`${selected.name} 的星球信标`} role="img">
          <div className="companion-orb-ring companion-orb-ring-one" />
          <div className="companion-orb-ring companion-orb-ring-two" />
          <div className="companion-orb-core"><span>✦</span></div>
          <small>{selected.planet}</small>
        </div>
      </div>

      <div className="companion-picker" role="tablist" aria-label="选择一位旅伴">
        {companionProfiles.map((companion) => (
          <button key={companion.id} type="button" role="tab" aria-selected={selected.id === companion.id} onClick={() => choose(companion)}>
            <span className={`companion-dot companion-dot-${companion.color}`} />
            <span><strong>{companion.name}</strong><small>{companion.planet}</small></span>
            <ArrowUpRight size={14} aria-hidden="true" />
          </button>
        ))}
      </div>

      <div className="companion-story" aria-live="polite">
        <div className="companion-story-head">
          <div><span className="companion-story-label">{selected.name} 的世界</span><strong>{selected.constellation}</strong></div>
          <span className="companion-story-belief">“{selected.belief}”</span>
        </div>
        <div className="companion-story-tabs" role="tablist" aria-label={`${selected.name} 的故事维度`}>
          {storyTabs.map(({ key, label, icon: Icon }) => (
            <button key={key} type="button" role="tab" aria-selected={story === key} onClick={() => setStory(key)}><Icon size={14} />{label}</button>
          ))}
        </div>
        <div className="companion-story-sheet">
          <div className="companion-story-icon"><StoryIcon size={17} /></div>
          <p key={`${selected.id}-${story}`}>{selected.stories[story]}</p>
        </div>
      </div>

      <div className="companion-portal-footer">
        <span><i /> 选择会影响开场语气与后续故事线；真实模型上下文接入待开发</span>
        <button type="button" className={invited ? "is-invited" : ""} onClick={invite}>
          {invited ? `${selected.name} 已降临` : `邀请 ${selected.name} 降临`} <ArrowUpRight size={16} />
        </button>
      </div>
    </section>
  );
}
