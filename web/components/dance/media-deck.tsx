"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type PointerEvent, type KeyboardEvent, type CSSProperties } from "react";
import { GripVertical, Pin, Maximize2, Minimize2, RotateCcw, Columns3 } from "lucide-react";
import "./media-deck.css";

const ids = ["original", "pose2d", "pose3d"] as const;
type MediaId = typeof ids[number];
const titles: Record<MediaId, string> = { original: "原始影像", pose2d: "二维骨架", pose3d: "估计三维姿态" };
const preferenceKey = "wuzhihua-media-layout-v1";
type Drag = { id: MediaId; over: MediaId | null; keyboard: boolean; x: number; y: number };

export function MediaDeck({ media, ready, active }: {
  media: Record<MediaId, ReactNode>; ready: Record<MediaId, boolean>; active: boolean;
}) {
  const [order, setOrder] = useState<MediaId[]>([...ids]);
  const [balanced, setBalanced] = useState(false);
  const [focused, setFocused] = useState<MediaId | null>(null);
  const [selected, setSelected] = useState<MediaId>("original");
  const [drag, setDrag] = useState<Drag | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const cards = useRef<Partial<Record<MediaId, HTMLDivElement>>>({});
  const before = useRef<Partial<Record<MediaId, DOMRect>> | null>(null);
  const animations = useRef<Animation[]>([]);
  const ghost = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const pointer = useRef<{ id: MediaId; pointerId: number; x: number; y: number } | null>(null);
  const deck = useRef<HTMLDivElement>(null);
  const suppressClick = useRef(false);
  const focusBeforeEnlarge = useRef<HTMLElement | null>(null);
  const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(preferenceKey) || "null");
      if (Array.isArray(stored?.order) && stored.order.length === 3 && new Set(stored.order).size === 3 && stored.order.every((id: string) => ids.includes(id as MediaId))) {
        setOrder(stored.order); setBalanced(stored.balanced === true);
      }
    } catch { /* Storage is optional. */ }
    setHydrated(true);
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try { localStorage.setItem(preferenceKey, JSON.stringify({ order, balanced })); } catch { /* Private mode still supports the workbench. */ }
  }, [order, balanced, hydrated]);

  function measure() {
    const rects: Partial<Record<MediaId, DOMRect>> = {};
    ids.forEach(id => { const card = cards.current[id]; if (card) rects[id] = card.getBoundingClientRect(); });
    animations.current.forEach(animation => animation.cancel());
    before.current = rects;
  }
  useLayoutEffect(() => {
    const previous = before.current;
    before.current = null;
    if (!previous || reduced()) return;
    animations.current = ids.flatMap(id => {
      const card = cards.current[id], first = previous[id];
      if (!card || !first) return [];
      const last = card.getBoundingClientRect();
      if (!last.width || !last.height) return [];
      return [card.animate([
        { transform: `translate(${first.left - last.left}px, ${first.top - last.top}px) scale(${first.width / last.width}, ${first.height / last.height})` },
        { transform: "translate(0, 0) scale(1, 1)" },
      ], { duration: 420, easing: "cubic-bezier(.16,1,.3,1)" })];
    });
  }, [order, balanced, focused]);
  useEffect(() => () => animations.current.forEach(animation => animation.cancel()), []);

  function cancel() {
    pointer.current = null;
    dragRef.current = null; setDrag(null);
  }
  function restore() {
    measure(); setFocused(null); setAnnouncement("已还原工作台布局");
    requestAnimationFrame(() => focusBeforeEnlarge.current?.focus({ preventScroll: true }));
  }
  useEffect(() => {
    const escape = (event: globalThis.KeyboardEvent) => {
      if (!active || event.key !== "Escape") return;
      if (dragRef.current || pointer.current) {
        event.preventDefault(); cancel(); setAnnouncement("已取消移动");
      } else if (focused) {
        event.preventDefault(); restore();
      }
    };
    window.addEventListener("keydown", escape);
    window.addEventListener("blur", cancel);
    return () => { window.removeEventListener("keydown", escape); window.removeEventListener("blur", cancel); };
    // restore reads the current layout and focus target.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, focused]);
  useEffect(() => {
    if (active) return;
    const frame = requestAnimationFrame(cancel);
    return () => cancelAnimationFrame(frame);
  }, [active]);

  function promote(id: MediaId) {
    measure();
    setOrder(current => { const next = [...current]; const at = next.indexOf(id); [next[0], next[at]] = [next[at], next[0]]; return next; });
    setSelected(id); setBalanced(false); setFocused(null);
    setAnnouncement(`${titles[id]}已设为主视图`);
  }
  function enlarge(id: MediaId) {
    if (!ready[id]) return;
    if (focused === id) { restore(); return; }
    if (!focused) focusBeforeEnlarge.current = document.activeElement as HTMLElement;
    measure(); setFocused(id); setSelected(id);
    setAnnouncement(`正在放大${titles[id]}，按 Escape 还原`);
    requestAnimationFrame(() => deck.current?.scrollIntoView({ behavior: reduced() ? "instant" : "smooth", block: "start" }));
  }
  function finish() {
    const moving = dragRef.current;
    if (moving && moving.over && moving.over !== moving.id) {
      measure();
      setOrder(current => {
        const next = [...current], from = next.indexOf(moving.id), to = next.indexOf(moving.over!);
        [next[from], next[to]] = [next[to], next[from]]; return next;
      });
      setSelected(moving.id);
      setAnnouncement(`${titles[moving.id]}已与${titles[moving.over]}交换位置`);
    } else if (moving) setAnnouncement("位置未改变");
    cancel();
  }
  function startPointer(event: PointerEvent<HTMLButtonElement>, id: MediaId) {
    if (event.button !== 0 || focused) return;
    suppressClick.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
    pointer.current = { id, pointerId: event.pointerId, x: event.clientX, y: event.clientY };
    setSelected(id);
  }
  function movePointer(event: PointerEvent<HTMLButtonElement>) {
    const start = pointer.current;
    if (!start || start.pointerId !== event.pointerId) return;
    if (!dragRef.current && Math.hypot(event.clientX - start.x, event.clientY - start.y) < 8) return;
    event.preventDefault(); suppressClick.current = true;
    const over = ids.find(id => {
      const rect = cards.current[id]?.getBoundingClientRect();
      return rect && event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
    }) || null;
    const next = { id: start.id, over, keyboard: false, x: event.clientX, y: event.clientY };
    if (!dragRef.current || dragRef.current.over !== over) setDrag(next);
    dragRef.current = next;
    if (ghost.current) ghost.current.style.transform = `translate3d(${event.clientX + 18}px,${event.clientY + 18}px,0)`;
  }
  function keyDrag(event: KeyboardEvent<HTMLButtonElement>, id: MediaId) {
    if (focused) return;
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      if (dragRef.current?.keyboard) { finish(); return; }
      const next = { id, over: id, keyboard: true, x: 0, y: 0 };
      dragRef.current = next; setDrag(next); setSelected(id);
      setAnnouncement(`已拿起${titles[id]}，方向键选择位置，回车放下，Escape 取消`);
    } else if (dragRef.current?.keyboard && ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      const direction = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1;
      const destinations = order;
      const index = destinations.indexOf(dragRef.current.over || id);
      const next = { ...dragRef.current, over: destinations[(index + direction + destinations.length) % destinations.length] };
      dragRef.current = next; setDrag(next); setAnnouncement(`目标位置：${titles[next.over]}`);
    }
  }

  const visibleOrder = focused ? [focused, ...order.filter(id => id !== focused)] : order;
  return <div className="media-deck" ref={deck} data-mode={balanced ? "balanced" : "split"} data-focused={Boolean(focused)} data-dragging={Boolean(drag)}>
    <div className="media-deck__toolbar">
      <span className="media-deck__hint"><GripVertical size={15} />{focused ? "还原布局后可拖动" : "拖动标题栏换位"}</span>
      <div className="media-deck__modes" role="group" aria-label="工作台布局">
        {focused ? <button type="button" onClick={restore}><Minimize2 size={15} />还原布局</button> : <button type="button" aria-pressed={balanced} onClick={() => { measure(); setBalanced(value => !value); }}><Columns3 size={15} />{balanced ? "主辅查看" : "均衡查看"}</button>}
        <button type="button" onClick={() => { cancel(); measure(); setOrder([...ids]); setBalanced(false); setFocused(null); setSelected("original"); setAnnouncement("已重置布局"); }}><RotateCcw size={14} />重置</button>
      </div>
    </div>
    <p className="media-deck__sr" aria-live="polite" aria-atomic="true">{announcement}</p>
    <div className="media-deck__grid">
      {ids.map((id, index) => {
        const slot = visibleOrder.indexOf(id);
        const primary = focused ? focused === id : !balanced && order[0] === id;
        return <div key={id} ref={node => { if (node) cards.current[id] = node; }} className="media-deck__card" role="region" aria-label={`${titles[id]}卡片`}
          data-media-id={id} data-slot={slot} data-primary={primary} data-selected={selected === id}
          data-lifted={drag?.id === id} data-drop-target={Boolean(drag && drag.over === id && drag.id !== id)}
          style={{ "--media-slot": slot } as CSSProperties}
          onPointerDownCapture={() => setSelected(id)} onFocusCapture={() => setSelected(id)}>
          <div className="media-deck__caption">
            <button type="button" className="media-deck__handle"
              aria-label={`移动${titles[id]}`} aria-describedby="media-deck-drag-help" disabled={Boolean(focused)} title={focused ? "还原布局后可拖动" : "按住标题栏拖动换位"}
              onPointerDown={event => startPointer(event, id)} onPointerMove={movePointer}
              onPointerUp={event => { if (pointer.current?.pointerId !== event.pointerId) return; finish(); if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
              onPointerCancel={cancel} onLostPointerCapture={() => { if (pointer.current) cancel(); }} onKeyDown={event => keyDrag(event, id)}
              onClick={event => { if (suppressClick.current) { event.preventDefault(); suppressClick.current = false; } }}>
              <span className="media-deck__number">0{index + 1}</span><GripVertical className="media-deck__grip" size={14} /><strong>{titles[id]}</strong>
            </button>
            <div className="media-deck__actions">
              {primary && <span className="media-deck__primary">{focused ? "专注" : "主视图"}</span>}
              <button type="button" aria-label={`将${titles[id]}设为主视图`} title="设为主视图" aria-pressed={order[0] === id && !balanced} onClick={() => promote(id)}><Pin size={15} /></button>
              <button type="button" aria-label={`${focused === id ? "还原" : "放大"}${titles[id]}`} title={focused === id ? "还原" : "页内放大"} aria-pressed={focused === id} disabled={!ready[id]} onClick={() => enlarge(id)}>{focused === id ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
            </div>
          </div>
          {media[id]}
        </div>;
      })}
    </div>
    <span id="media-deck-drag-help" className="media-deck__sr">拖动标题交换位置；也可按空格拿起、方向键选择目标、回车放下、Escape 取消。</span>
    {drag && !drag.keyboard && <div ref={ghost} className="media-deck__ghost" aria-hidden="true" style={{ transform: `translate3d(${drag.x + 18}px,${drag.y + 18}px,0)` }}><GripVertical size={18} /><span>{titles[drag.id]}</span><small>{drag.over && drag.over !== drag.id ? "松手交换" : "拖至目标卡片"}</small></div>}
  </div>;
}
