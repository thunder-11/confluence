import { useEffect, useRef, useState } from "react";
import { Maximize2, Minus, Plus } from "lucide-react";
import type { Snapshot, Config } from "./types";
import { colors } from "./types";
export type KnowledgeMode = "union" | "agent" | "coordinator" | "truth";
interface Props {
  snapshot?: Snapshot;
  mode?: KnowledgeMode;
  selected?: number;
  onSelect?: (id: number) => void;
  paths?: boolean;
  editConfig?: Config;
  onPaint?: (cell: number) => void;
  compact?: boolean;
}
export default function GridCanvas({
  snapshot: s,
  mode = "union",
  selected = 0,
  onSelect,
  paths = true,
  editConfig,
  onPaint,
  compact = false,
}: Props) {
  const canvas = useRef<HTMLCanvasElement>(null),
    host = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 530 }),
    [zoom, setZoom] = useState(1),
    [pan, setPan] = useState({ x: 0, y: 0 });
  const dragging = useRef<{
    x: number;
    y: number;
    px: number;
    py: number;
  } | null>(null);
  const geometry = useRef({ unit: 1, x: 0, y: 0, w: 64, h: 64 });
  const displayAgents =
    s?.agents.flatMap((a) => {
      if (mode === "agent" && a.id !== selected) {
        const known = s.agents[selected]?.knownAgents?.find(
          (k) => k.id === a.id,
        );
        return known
          ? [
              {
                ...a,
                position: known.position,
                status: known.status,
                path: [],
                task: -1,
              },
            ]
          : [];
      }
      if (mode === "coordinator") {
        const known = s.coordinatorAgents?.find((k) => k.id === a.id);
        return known
          ? [
              {
                ...a,
                position: known.position,
                status: known.status,
                path: [],
                task: known.task,
              },
            ]
          : [];
      }
      return [a];
    }) || [];
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver((entries) => {
      const b = entries[0].contentRect;
      setSize({ w: b.width, h: b.height });
    });
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    c.width = size.w * dpr;
    c.height = size.h * dpr;
    ctx.scale(dpr, dpr);
    ctx.fillStyle = "#191d1c";
    ctx.fillRect(0, 0, size.w, size.h);
    const w = editConfig?.width || s?.width || 64,
      h = editConfig?.height || s?.height || 64;
    const unit = Math.min((size.w - 48) / w, (size.h - 48) / h) * zoom;
    const ox = (size.w - w * unit) / 2 + pan.x,
      oy = (size.h - h * unit) / 2 + pan.y;
    geometry.current = { unit, x: ox, y: oy, w, h };
    const cells =
      editConfig?.map ||
      (mode === "truth"
        ? s?.truth
        : mode === "agent"
          ? s?.agents[selected]?.map
          : mode === "coordinator"
            ? s?.coordinatorMap
            : s?.unionMap);
    if (!cells) {
      ctx.fillStyle = "#b2b9b5";
      ctx.font = "14px IBM Plex Sans";
      ctx.textAlign = "center";
      ctx.fillText("Preparing the environment…", size.w / 2, size.h / 2);
      return;
    }
    for (let p = 0; p < cells.length; p++) {
      const x = ox + (p % w) * unit,
        y = oy + Math.floor(p / w) * unit;
      if (x + unit < 0 || y + unit < 0 || x > size.w || y > size.h) continue;
      ctx.fillStyle =
        cells[p] === -1 ? "#222725" : cells[p] === 1 ? "#69756f" : "#e4ede7";
      ctx.fillRect(x, y, unit, unit);
      if (unit >= 4) {
        ctx.strokeStyle = cells[p] === -1 ? "#2a302d" : "#cdd7d0";
        ctx.lineWidth = 0.35;
        ctx.strokeRect(x, y, unit, unit);
      }
    }
    const center = (p: number) => ({
      x: ox + ((p % w) + 0.5) * unit,
      y: oy + (Math.floor(p / w) + 0.5) * unit,
    });
    const zones =
      editConfig?.zones ||
      (mode === "truth"
        ? s?.truthZones
        : mode === "agent"
          ? s?.agents[selected]?.knownZones
          : mode === "coordinator"
            ? s?.coordinatorZones
            : s?.unionZones) ||
      [];
    zones.forEach((priority, p) => {
      if (priority <= 0 || cells[p] !== 0) return;
      const { x, y } = center(p);
      ctx.strokeStyle = "#aa8437";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(
        x - unit * 0.38,
        y - unit * 0.38,
        unit * 0.76,
        unit * 0.76,
      );
    });
    const stations = editConfig
      ? editConfig.chargingStations.map((p) => p.y * w + p.x)
      : s?.stations || [];
    for (const p of stations) {
      const { x, y } = center(p);
      ctx.fillStyle = "#6ca885";
      ctx.fillRect(x - unit * 0.39, y - unit * 0.39, unit * 0.78, unit * 0.78);
      if (unit > 7) {
        ctx.fillStyle = "#183f2c";
        ctx.font = `bold ${Math.max(7, unit * 0.65)}px IBM Plex Sans`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("ϟ", x, y);
      }
    }
    const ts = editConfig
      ? editConfig.targets?.flatMap((v, p) =>
          v ? [{ cell: p, discovered: true, tick: 0 }] : [],
        ) || []
      : s?.targets || [];
    for (const t of ts) {
      const known =
        mode === "agent"
          ? s?.agents[selected]?.knownTargets?.includes(t.cell)
          : mode === "coordinator"
            ? s?.coordinatorTargets?.includes(t.cell)
            : t.discovered;
      if (!editConfig && mode !== "truth" && !known) continue;
      const { x, y } = center(t.cell);
      ctx.beginPath();
      ctx.moveTo(x, y - unit * 0.35);
      ctx.lineTo(x + unit * 0.35, y);
      ctx.lineTo(x, y + unit * 0.35);
      ctx.lineTo(x - unit * 0.35, y);
      ctx.closePath();
      ctx.fillStyle = t.discovered ? "#cfaa5b" : "#8d7546";
      ctx.fill();
    }
    if (editConfig) {
      for (const a of editConfig.starts) {
        const { x, y } = center(a.y * w + a.x);
        ctx.fillStyle = colors[a.agentId % colors.length];
        ctx.beginPath();
        ctx.arc(x, y, unit * 0.42, 0, Math.PI * 2);
        ctx.fill();
      }
      return;
    }
    if (paths && s)
      for (const a of displayAgents) {
        if (mode === "agent" && a.id !== selected) continue;
        const region = a.regions?.find((r) => r.id === a.assignedRegion);
        if (region) {
          ctx.fillStyle = colors[a.id % colors.length];
          ctx.globalAlpha = 0.25;
          for (const p of region.cells) {
            const { x, y } = center(p);
            ctx.fillRect(x - unit * 0.5, y - unit * 0.5, unit, unit);
          }
          ctx.globalAlpha = 1;
        }
        if (a.path.length < 2) continue;
        ctx.strokeStyle = colors[a.id % colors.length];
        ctx.globalAlpha = a.id === selected ? 0.9 : 0.4;
        ctx.lineWidth = Math.max(1.3, unit * 0.16);
        ctx.beginPath();
        a.path.forEach((p, i) => {
          const { x, y } = center(p);
          if (i) ctx.lineTo(x, y);
          else ctx.moveTo(x, y);
        });
        ctx.stroke();
        ctx.globalAlpha = 1;
        if (a.task >= 0) {
          const { x, y } = center(a.task);
          ctx.strokeStyle = colors[a.id % colors.length];
          ctx.lineWidth = 1.5;
          ctx.strokeRect(
            x - unit * 0.6,
            y - unit * 0.6,
            unit * 1.2,
            unit * 1.2,
          );
        }
      }
    if (s)
      for (const a of displayAgents) {
        const { x, y } = center(a.position);
        const showLabel =
          unit > 9 || displayAgents.length <= 4 || a.id === selected;
        const radius = Math.max(showLabel ? 7 : 4, unit * 0.43);
        ctx.fillStyle =
          a.status === "ACTIVE" ? colors[a.id % colors.length] : "#676b68";
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();
        if (a.id === selected) {
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = 1.8;
          ctx.beginPath();
          ctx.arc(x, y, radius + 2.5, 0, Math.PI * 2);
          ctx.stroke();
        }
        if (showLabel) {
          ctx.fillStyle = "#fff";
          ctx.font = `500 ${Math.max(10, unit * 0.6)}px IBM Plex Sans`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(a.id + 1), x, y + 0.5);
        }
        if (a.status !== "ACTIVE") {
          ctx.strokeStyle = "#fff";
          ctx.beginPath();
          ctx.moveTo(x - 3, y - 3);
          ctx.lineTo(x + 3, y + 3);
          ctx.moveTo(x + 3, y - 3);
          ctx.lineTo(x - 3, y + 3);
          ctx.stroke();
        }
      }
  }, [s, mode, selected, paths, editConfig, size, zoom, pan]);
  function cellAt(e: React.PointerEvent) {
    const b = canvas.current!.getBoundingClientRect(),
      g = geometry.current;
    const x = Math.floor((e.clientX - b.left - g.x) / g.unit),
      y = Math.floor((e.clientY - b.top - g.y) / g.unit);
    return x >= 0 && y >= 0 && x < g.w && y < g.h ? y * g.w + x : -1;
  }
  return (
    <div ref={host} className={"grid-canvas " + (compact ? "compact" : "")}>
      <canvas
        ref={canvas}
        aria-label={
          editConfig
            ? "Custom map editor"
            : "Interactive agent exploration grid"
        }
        onPointerDown={(e) => {
          const p = cellAt(e);
          if (onPaint && p >= 0) {
            onPaint(p);
            canvas.current?.setPointerCapture(e.pointerId);
            return;
          }
          if (s) {
            const a = displayAgents.find((a) => a.position === p);
            if (a) {
              onSelect?.(a.id);
              return;
            }
          }
          dragging.current = {
            x: e.clientX,
            y: e.clientY,
            px: pan.x,
            py: pan.y,
          };
          canvas.current?.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (onPaint && e.buttons === 1) {
            const p = cellAt(e);
            if (p >= 0) onPaint(p);
          } else if (dragging.current) {
            const d = dragging.current;
            setPan({ x: d.px + e.clientX - d.x, y: d.py + e.clientY - d.y });
          }
        }}
        onPointerUp={() => {
          dragging.current = null;
        }}
        onPointerCancel={() => {
          dragging.current = null;
        }}
        onWheel={(e) => {
          setZoom((z) =>
            Math.min(5, Math.max(0.6, z * (e.deltaY < 0 ? 1.1 : 0.9))),
          );
        }}
      />
      {!compact && (
        <>
          <div className="canvas-caption">
            <span className="live-dot" />
            {editConfig
              ? "Map editor"
              : mode === "truth"
                ? "Evaluator ground truth"
                : mode === "agent"
                  ? `Agent ${String(selected + 1).padStart(2, "0")} · local knowledge`
                  : mode === "coordinator"
                    ? "Coordinator · delivered knowledge"
                    : "Collective knowledge"}
            <span className="canvas-meta">
              {editConfig?.width || s?.width} ×{" "}
              {editConfig?.height || s?.height}
            </span>
          </div>
          <div className="zoom-controls">
            <button
              aria-label="Zoom out"
              onClick={() => setZoom((z) => Math.max(0.6, z - 0.25))}
            >
              <Minus size={15} />
            </button>
            <span>{Math.round(zoom * 100)}%</span>
            <button
              aria-label="Zoom in"
              onClick={() => setZoom((z) => Math.min(5, z + 0.25))}
            >
              <Plus size={15} />
            </button>
            <button
              aria-label="Fit grid"
              onClick={() => {
                setZoom(1);
                setPan({ x: 0, y: 0 });
              }}
            >
              <Maximize2 size={14} />
            </button>
          </div>
          <div className="compass">N ↑</div>
        </>
      )}
    </div>
  );
}
