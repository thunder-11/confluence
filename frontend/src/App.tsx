import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Grid2X2,
  Info,
  LayoutDashboard,
  Menu,
  Network,
  Pause,
  Play,
  Plus,
  Radio,
  RotateCcw,
  Settings2,
  ShieldCheck,
  SkipForward,
  Square,
  Target,
  Terminal,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import GridCanvas from "./GridCanvas";
import WorkspaceSwitcher from "./WorkspaceSwitcher";
import { applyStatePatch } from "./patch";
import { demos, demoConfig } from "./demos";
import type { Demo } from "./demos";
import { AgentAnalytics, EventLog, ExperimentAnalytics } from "./Diagnostics";
import type { KnowledgeMode } from "./GridCanvas";
import {
  api,
  colors,
  defaultConfig,
  strategies,
  strategyNames,
  terminal,
} from "./types";
import type {
  Agent,
  Batch,
  Config,
  Event,
  RunRow,
  Scenario,
  Snapshot,
  Strategy,
} from "./types";

type Page = "studio" | "overview" | "builder" | "compare" | "experiments" | "demos";
const pageNames: Record<Page, string> = {
  studio: "Simulation studio",
  overview: "Overview",
  builder: "Scenario builder",
  compare: "Compare strategies",
  experiments: "Experiments",
  demos: "Demo scenarios",
};
const format = (n: number | undefined, d = 0) =>
  n === undefined
    ? "—"
    : n.toLocaleString(undefined, { maximumFractionDigits: d });
const text = (s: string) => s.toLowerCase().replaceAll("_", " ");
const coordinate = (p: number, w: number) =>
  p < 0 ? "Unassigned" : `(${p % w}, ${Math.floor(p / w)})`;
const presetFamilies: NonNullable<Config["scenarioFamily"]>[] = [
  "normal",
  "unknown",
  "communication",
  "failure",
  "dynamic",
  "resources",
];
const presetNames = [
  "Normal exploration",
  "Unknown environment",
  "Communication breakdown",
  "Agent failure",
  "Dynamic obstacles",
  "Resource constraints",
];

function Mark() {
  return (
    <svg
      width="30"
      height="30"
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M4 5L15 16L4 27M14 5L25 16L14 27"
        stroke="currentColor"
        strokeWidth="3"
      />
      <path d="M25 16H30" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}
function Badge({ value }: { value: string }) {
  return (
    <span
      className={
        "badge " +
        (value === "RUNNING" || value === "ACTIVE"
          ? "positive"
          : value === "FAILED"
            ? "negative"
            : "")
      }
    >
      {text(value)}
    </span>
  );
}
function Metric({
  label,
  value,
  unit,
  note,
}: {
  label: string;
  value: string;
  unit?: string;
  note?: string;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <div>
        {value}
        <small>{unit}</small>
      </div>
      {note && <p>{note}</p>}
    </div>
  );
}
function Chart({
  data,
  dataKey = "coverage",
  height = 165,
}: {
  data: Record<string, number>[];
  dataKey?: string;
  height?: number;
}) {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 0, left: -20 }}
        >
          <CartesianGrid vertical={false} stroke="#edf0ee" />
          <XAxis
            dataKey="tick"
            minTickGap={55}
            tick={{ fontSize: 11, fill: "#68726c" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={dataKey === "coverage" ? [0, 100] : ["auto", "auto"]}
            tick={{ fontSize: 11, fill: "#68726c" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              border: "1px solid #e8eaec",
              borderRadius: 6,
              fontSize: 12,
            }}
            labelFormatter={(v) => `Tick ${v}`}
          />
          <Line
            type="linear"
            dataKey={dataKey}
            stroke="#1b6c80"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>(() => {
      const route = location.hash.slice(1);
      if (Object.hasOwn(pageNames, route)) return route as Page;
      const saved = localStorage.getItem("confluence.page");
      return saved && saved in pageNames ? (saved as Page) : "studio";
    }),
    [menu, setMenu] = useState(false),
    [scenario, setScenario] = useState<Scenario>(),
    [snapshot, setSnapshot] = useState<Snapshot>(),
    [runId, setRunId] = useState(""),
    [status, setStatus] = useState("READY");
  const [strategy, setStrategy] = useState<Strategy>("adaptive"),
    [planner, setPlanner] = useState("reservations"),
    [pathfinder, setPathfinder] = useState("astar"),
    [selected, setSelected] = useState(0),
    [mode, setMode] = useState<KnowledgeMode>("union"),
    [paths, setPaths] = useState(true),
    [speed, setSpeed] = useState(10);
  const [readOnly, setReadOnly] = useState(false);
  const [events, setEvents] = useState<Event[]>([]),
    [series, setSeries] = useState<Record<string, number>[]>([]),
    [recent, setRecent] = useState<RunRow[]>([]),
    [scenarios, setScenarios] = useState<Scenario[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [connected, setConnected] = useState(false),
    [configOpen, setConfigOpen] = useState(false),
    [preset, setPreset] = useState(0);
  const [replayTick, setReplayTick] = useState<number | null>(null),
    [replaySnapshot, setReplaySnapshot] = useState<Snapshot>();
  const [replayEvents, setReplayEvents] = useState<Event[]>([]);
  const [chartMetric, setChartMetric] = useState("coverage");
  const [batch, setBatch] = useState<Batch>(),
    [batchRows, setBatchRows] = useState<
      { id: string; name: string; status: string }[]
    >([]),
    [seeds, setSeeds] = useState("100, 101, 102"),
    [experimentTicks, setExperimentTicks] = useState(1000);
  const [studyScenarioId, setStudyScenarioId] = useState("");
  const [experimentName, setExperimentName] = useState("");
  const [studyStrategies, setStudyStrategies] = useState<Strategy[]>([...strategies]);
  const started = useRef(false),
    snapshotRef = useRef(snapshot),
    statusRef = useRef(status);
  snapshotRef.current = snapshot;
  statusRef.current = status;
  const refresh = useCallback(async () => {
    const [r, s, b] = await Promise.all([
      api<RunRow[]>("/runs"),
      api<Scenario[]>("/scenarios"),
      api<typeof batchRows>("/experiments"),
    ]);
    setRecent(r);
    setScenarios(s);
    setBatchRows(b);
  }, []);
  const perform = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);
  const adopt = (r: {
    id: string;
    snapshot: Snapshot;
    status: string;
    readOnly?: boolean;
  }) => {
    setReadOnly(Boolean(r.readOnly));
    localStorage.setItem("confluence.run", r.id);
    setRunId(r.id);
    setSnapshot(r.snapshot);
    setStatus(r.status);
    setEvents([]);
    setSeries([{ tick: r.snapshot.tick, ...r.snapshot.metrics }]);
    setReplayTick(null);
    setReplaySnapshot(undefined);
    setSelected(0);
  };
  const stopActive = async () => {
    const active = await api<RunRow[]>("/runs");
    for (const row of active)
      if (!row.batch_id && !terminal(row.status)) {
        await api(`/runs/${row.id}/commands`, { command: "stop" });
        if (row.id === runId) setStatus("STOPPED");
      }
  };
  const create = async (c: Config, name = "Rooms & corridors") => {
    await stopActive();
    const clean = { ...c };
    delete clean.map;
    delete clean.targets;
    delete clean.zones;
    clean.starts = [];
    clean.chargingStations = [];
    const chosenStrategy = c.strategy || strategy,
      chosenPlanner = c.planner || planner,
      chosenPathfinder = c.pathfinder || pathfinder;
    setStrategy(chosenStrategy);
    setPlanner(chosenPlanner);
    setPathfinder(chosenPathfinder);
    const s = await api<Scenario>("/scenarios/generate", {
      name,
      config: clean,
    });
    setScenario(s);
    const r = await api<{ id: string; snapshot: Snapshot; status: string }>(
      "/runs",
      {
        scenarioId: s.id,
        strategy: chosenStrategy,
        planner: chosenPlanner,
        pathfinder: chosenPathfinder,
      },
    );
    adopt(r);
    await refresh();
  };
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    perform(async () => {
      await refresh();
      const rows = await api<RunRow[]>("/runs");
      const batches =
        await api<{ id: string; status: string }[]>("/experiments");
      const savedRun = localStorage.getItem("confluence.run");
      const current =
        rows.find(
          (r) =>
            !r.batch_id && ["READY", "RUNNING", "PAUSED"].includes(r.status),
        ) ||
        rows.find((r) => r.id === savedRun) ||
        rows.find((r) => !r.batch_id) ||
        rows[0];
      const savedBatch = localStorage.getItem("confluence.batch");
      const knownBatch =
        batches.find((b) => b.status === "RUNNING") ||
        batches.find((b) => b.id === savedBatch);
      if (knownBatch) setBatch(await api(`/experiments/${knownBatch.id}`));
      if (current) {
        const r = await api<RunRow & { snapshot: Snapshot }>(
          `/runs/${current.id}`,
        );
        setScenario(await api<Scenario>(`/scenarios/${r.scenario_id}`));
        adopt({
          id: r.id,
          snapshot: r.snapshot,
          status: r.status,
          readOnly: Boolean(r.batch_id),
        });
        setStrategy(r.strategy);
        setPlanner(r.planner);
        setSeries(
          (
            await api<{ series: Record<string, number>[] }>(
              `/runs/${r.id}/metrics`,
            )
          ).series,
        );
        setEvents(await api(`/runs/${r.id}/events?recent=true&limit=100`));
      } else if (!knownBatch) await create(defaultConfig);
    });
  }, [perform, refresh]);
  useEffect(() => {
    localStorage.setItem("confluence.page", page);
    if (location.hash !== `#${page}`) history.pushState(null, "", `#${page}`);
    document.title = `${pageNames[page]} · CONFLUENCE`;
    window.scrollTo({ top: 0 });
    setMenu(false);
  }, [page]);
  useEffect(() => {
    const followRoute = () => {
      const route = location.hash.slice(1);
      if (Object.hasOwn(pageNames, route)) setPage(route as Page);
    };
    const closeOnEscape = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    window.addEventListener("hashchange", followRoute);
    window.addEventListener("popstate", followRoute);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("hashchange", followRoute);
      window.removeEventListener("popstate", followRoute);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, []);
  useEffect(() => {
    if (batch) localStorage.setItem("confluence.batch", batch.id);
  }, [batch?.id]);
  useEffect(() => {
    if (!runId) return;
    let disposed = false,
      ws: WebSocket | undefined,
      timer: number;
    let retries = 0;
    const connect = () => {
      if (disposed) return;
      let wireState: Snapshot | undefined;
      let wireSequence = -1;
      ws = new WebSocket(
        `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/v1/runs/${runId}/stream`,
      );
      ws.onopen = () => {
        setConnected(true);
        retries = 0;
      };
      ws.onmessage = (e) => {
        const message = JSON.parse(e.data);
        const p = message.payload;
        if (message.type === "snapshot") wireState = p.snapshot;
        else if (
          message.type === "delta" &&
          wireState &&
          p.baseSequence === wireSequence &&
          message.sequence === wireSequence + 1
        )
          wireState = applyStatePatch(wireState, p.patch) as Snapshot;
        else {
          wireState = undefined;
          void api<Snapshot>(`/runs/${runId}/snapshot`)
            .then(setSnapshot)
            .catch((e) => setError(e.message));
          ws?.close();
          return;
        }
        wireSequence = message.sequence;
        const state = wireState!;
        setSnapshot(state);
        setStatus(p.status);
        setEvents((old) => [...old, ...(p.events || [])].slice(-400));
        setSeries((old) => {
          const next = [
            ...old.filter((x) => x.tick !== state.tick),
            { tick: state.tick, ...state.metrics },
          ];
          return next.length > 1000 ? next.filter((_, i) => i % 2 === 0) : next;
        });
      };
      ws.onclose = () => {
        setConnected(false);
        if (!disposed && !terminal(statusRef.current) && retries++ < 5)
          timer = window.setTimeout(connect, 1000 * retries);
      };
    };
    connect();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [runId]);
  useEffect(() => {
    if (!batch || batch.status !== "RUNNING") return;
    const timer = setInterval(
      () =>
        api<Batch>(`/experiments/${batch.id}`)
          .then(setBatch)
          .catch((e) => setError(e.message)),
      2000,
    );
    return () => clearInterval(timer);
  }, [batch?.id, batch?.status]);
  useEffect(() => {
    if (replayTick === null || !runId) return;
    let disposed = false;
    const timer = setTimeout(
      () =>
        Promise.all([
          api<Snapshot>(`/runs/${runId}/snapshot?tick=${replayTick}`),
          api<Event[]>(
            `/runs/${runId}/events?recent=true&limit=100&throughTick=${replayTick}`,
          ),
        ])
          .then(([s, log]) => {
            if (!disposed) {
              setReplaySnapshot(s);
              setReplayEvents(log);
            }
          })
          .catch((e) => setError(e.message)),
      80,
    );
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [replayTick, runId]);
  const command = async (cmd: string) => {
    if (cmd === "reset") await stopActive();
    const r = await api<{ id: string; snapshot: Snapshot; status: string }>(
      `/runs/${runId}/commands`,
      { command: cmd, speed },
    );
    if (cmd === "reset") adopt(r);
    else {
      setStatus(r.status);
      setSnapshot(r.snapshot);
      setReplayTick(null);
      setReplaySnapshot(undefined);
    }
    await refresh();
  };
  const run = () =>
    perform(async () => {
      if (readOnly) {
        setPage("compare");
        return;
      }
      if (replayTick !== null) {
        setReplayTick(null);
        return;
      }
      if (terminal(status)) {
        await command("reset");
        return;
      }
      await command(
        status === "RUNNING"
          ? "pause"
          : status === "PAUSED"
            ? "resume"
            : "start",
      );
    });
  const chooseStrategy = (value: Strategy) =>
    perform(async () => {
      setStrategy(value);
      if (!scenario) return;
      await stopActive();
      adopt(
        await api("/runs", {
          scenarioId: scenario.id,
          strategy: value,
          planner,
          pathfinder,
        }),
      );
    });
  const loadRun = (id: string) =>
    perform(async () => {
      if (id === runId) {
        setPage("studio");
        return;
      }
      if (runId && !readOnly && statusRef.current === "RUNNING")
        await api(`/runs/${runId}/commands`, { command: "pause" });
      const r = await api<RunRow & { snapshot: Snapshot }>(`/runs/${id}`);
      if (r.batch_id) setBatch(await api(`/experiments/${r.batch_id}`));
      setScenario(await api(`/scenarios/${r.scenario_id}`));
      adopt({
        id: r.id,
        snapshot: r.snapshot,
        status: r.status,
        readOnly: Boolean(r.batch_id),
      });
      setStrategy(r.strategy);
      setPlanner(r.planner);
      setPage("studio");
      setSeries(
        (await api<{ series: Record<string, number>[] }>(`/runs/${id}/metrics`))
          .series,
      );
      setEvents(
        (await api<Event[]>(`/runs/${id}/events?recent=true&limit=100`)).slice(
          -100,
        ),
      );
    });
  const generatePreset = async (index: number) => {
    const c = structuredClone(defaultConfig);
    c.scenarioFamily = presetFamilies[index];
    if (index === 1) {
      c.sensorRadius = 1;
      c.obstacleDensity = 0.55;
    }
    c.seed = scenario?.config.seed || "42";
    if (index === 2) {
      c.communication.delayMaxTicks = 5;
      c.communication.dropProbability = 0.1;
      c.faultSchedule = [];
    }
    if (index === 3) c.faultSchedule = [];
    if (index === 4) c.faultSchedule = [];
    if (index === 5) c.energy.capacity = 100000;
    await create(c, presetNames[index]);
  };
  const launchDemo = (demo: Demo) => perform(async () => {
    await stopActive();
    const s = await api<Scenario>("/scenarios", { name: `Demo · ${demo.name}`, config: demoConfig(demo) });
    setScenario(s);
    setStrategy(demo.strategy);
    setPlanner("reservations");
    setPathfinder("astar");
    setMode("union");
    setPaths(true);
    setSpeed(20);
    const r = await api<{ id: string; snapshot: Snapshot; status: string }>("/runs", {
      scenarioId: s.id, strategy: demo.strategy, planner: "reservations", pathfinder: "astar",
    });
    adopt(r);
    await api(`/runs/${r.id}/commands`, { command: "set_speed", speed: 20 });
    await refresh();
    setPage("studio");
  });
  const inject = (type: string) =>
    perform(async () => {
      if (!snapshot) return;
      let fault: Record<string, unknown> = { tick: snapshot.tick + 1 };
      if (type === "agent_failure")
        fault = { ...fault, type, agentId: selected };
      if (type === "partition")
        fault = {
          ...fault,
          type,
          endTick: snapshot.tick + 101,
          split: Math.max(1, Math.floor(snapshot.agents.length / 2)),
        };
      if (type === "block_cell") {
        const agent = snapshot.agents[selected];
        let p = agent.path.find(
          (p) =>
            !snapshot.agents.some((a) => a.position === p) &&
            !snapshot.stations.includes(p),
        );
        if (p === undefined)
          p = snapshot.unionMap.findIndex(
            (v, i) =>
              v === 0 &&
              !snapshot.agents.some((a) => a.position === i) &&
              !snapshot.stations.includes(i),
          );
        if (p < 0 || p === undefined)
          throw new Error("No observed unoccupied cell is available");
        fault = {
          ...fault,
          type,
          x: p % snapshot.width,
          y: Math.floor(p / snapshot.width),
          unblockTick: snapshot.tick + 101,
        };
      }
      await api(`/runs/${runId}/faults`, { ...fault, nextTick: true });
    });
  const launchExperiment = (comparison = false) =>
    perform(async () => {
      const chosenScenario = scenarios.find((s) => s.id === (studyScenarioId || scenario?.id)) || scenario;
      if (!chosenScenario) throw new Error("Create or load a scenario first");
      await stopActive();
      const r = await api<{ id: string }>("/experiments", {
        name: comparison ? `${chosenScenario.name} · strategy comparison` : experimentName.trim() || `${chosenScenario.name} · allocation study`,
        scenarioId: chosenScenario.id,
        strategies: comparison ? strategies : studyStrategies,
        seeds: comparison ? [chosenScenario.config.seed] : seeds
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        maxTicks: experimentTicks,
      });
      setBatch(await api(`/experiments/${r.id}`));
      setPage(comparison ? "compare" : "experiments");
      await refresh();
    });
  const shown = replayTick === null ? snapshot : replaySnapshot || snapshot;
  const agent = shown?.agents[selected] || shown?.agents[0];
  const importantEvents = (replayTick === null ? events : replayEvents)
    .filter(
      (e) =>
        e.tick <= (shown?.tick || 0) &&
        !["message_delivered", "message_dropped", "decision"].includes(e.type),
    )
    .slice(-6)
    .reverse();
  const m = shown?.metrics || {};
  const currentDemo = demos.find((demo) => scenario?.name === `Demo · ${demo.name}`);
  return (
    <div className="app-shell">
      {menu && <button className="nav-backdrop" aria-label="Close navigation" onClick={() => setMenu(false)} />}
      <aside id="primary-sidebar" className={menu ? "sidebar open" : "sidebar"}>
        <a
          className="brand"
          href="#studio"
          aria-label="CONFLUENCE simulation studio"
          onClick={(e) => {
            e.preventDefault();
            setPage("studio");
          }}
        >
          <Mark />
          <div>
            CONFLUENCE<span>Exploration laboratory</span>
          </div>
        </a>
        <button
          className="mobile-close"
          onClick={() => setMenu(false)}
          aria-label="Close menu"
        >
          <X size={20} />
        </button>
        <WorkspaceSwitcher />
        <nav aria-label="Main navigation">
          {(
            [
              { id: "overview", icon: LayoutDashboard },
              { id: "studio", icon: Grid2X2 },
              { id: "demos", icon: Play },
              { id: "builder", icon: Settings2 },
              { id: "compare", icon: Workflow },
              { id: "experiments", icon: FlaskConical },
            ] as const
          ).map(({ id, icon: Icon }) => (
            <a
              key={id}
              href={`#${id}`}
              aria-label={pageNames[id]}
              aria-current={page === id ? "page" : undefined}
              title={pageNames[id]}
              className={page === id ? "nav-link active" : "nav-link"}
              onClick={(e) => {
                if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
                e.preventDefault();
                setPage(id);
                setMenu(false);
                refresh().catch(() => {});
              }}
            >
              <Icon size={17} />
              <span className="nav-label">{pageNames[id]}</span>
            </a>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="eyebrow">The mission</span>
          <p>
            Many agents.
            <br />
            One mission.
          </p>
          <span>Explore. Coordinate. Adapt.</span>
          <div className="confluence-symbol">
            <svg width="140" height="70" viewBox="0 0 140 70" fill="none">
              <path
                d="M1 8C45 8 35 35 75 35H138M1 35H138M1 62C45 62 35 35 75 35"
                stroke="#94a7a1"
              />
              <circle cx="20" cy="9" r="3" fill="#177b72" />
              <circle cx="45" cy="35" r="3" fill="#3975bc" />
              <circle cx="20" cy="61" r="3" fill="#b98122" />
            </svg>
          </div>
        </div>
        <div className="sidebar-bottom">
          <span className={"connection-dot " + (connected ? "online" : "")} />
          <div>
            {connected ? "Engine connected" : "Local application"}
            <small>C++20 · Protocol v1</small>
          </div>
          <Info size={15} />
        </div>
      </aside>
      <div className="app-content">
        <header className="topbar">
          <button
            className="mobile-menu"
            aria-label={menu ? "Collapse navigation" : "Expand navigation"}
            aria-expanded={menu}
            aria-controls="primary-sidebar"
            onClick={() => setMenu(!menu)}
          >
            <Menu size={20} />
          </button>
          <span>
            Workspace <ChevronRight size={13} />{" "}
            <strong>{pageNames[page]}</strong>
          </span>
          <div>
            <span className="local-indicator" />
            Local execution
            <span className="topbar-divider" />
            v1.0
          </div>
        </header>
        <main className="sheet">
          {error && (
            <div role="alert" className="error-banner">
              <Info size={17} />
              <span>{error}</span>
              <button className="text-button" onClick={() => location.reload()}>
                Reconnect
              </button>
              <button aria-label="Dismiss message" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {page === "studio" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="breadcrumb">Laboratory / Live simulation</div>
                  <h1>
                    Simulation studio{" "}
                    <Badge value={replayTick !== null ? "REPLAY" : status} />
                  </h1>
                  <p>
                    Watch independent decisions become collective discovery.
                  </p>
                </div>
                <div className="studio-heading-actions">
                  <button className="button" onClick={() => setPage("demos")}><Play size={15} />Demo scenarios</button>
                  <button className="button" disabled={busy} onClick={() => setConfigOpen(true)}><Settings2 size={15} />Configure scenario</button>
                </div>
              </div>
              {currentDemo && <div className="demo-cue"><strong>{currentDemo.timeline}</strong><span>{currentDemo.watch}</span></div>}
              <div className="mission-bar">
                <div>
                  <span className="scenario-symbol">
                    <Grid2X2 size={18} />
                  </span>
                  <div>
                    <strong>{scenario?.name || "Preparing environment"}</strong>
                    <span>
                      {scenario?.config.width || 64} ×{" "}
                      {scenario?.config.height || 64} grid <b>·</b>{" "}
                      {snapshot?.agents.length || 4} agents <b>·</b> Seed{" "}
                      <code>{scenario?.config.seed || "42"}</code>
                    </span>
                  </div>
                </div>
                <div className="mission-facts">
                  <span>
                    <small>Allocation</small>
                    {strategyNames[strategy]}
                  </span>
                  <span>
                    <small>Path planner</small>
                    {planner === "cbs" ? "Bounded CBS" : "Space-time A*"}
                  </span>
                  <span>
                    <small>Logical time</small>
                    <code>
                      {String(shown?.tick || 0).padStart(5, "0")}
                    </code>{" "}
                    ticks
                  </span>
                </div>
              </div>
              <div className="metrics-strip">
                <Metric
                  label="Exploration coverage"
                  value={format(m.coverage, 1)}
                  unit="%"
                  note={`${format(m.observedCells)} of ${format(m.reachableCells)} reachable cells`}
                />
                <Metric
                  label="Targets discovered"
                  value={format(m.targetsFound)}
                  unit={`/ ${format(m.targetCount)}`}
                  note="Found through local sensing"
                />
                <Metric
                  label="Distance travelled"
                  value={format(m.distance)}
                  unit="steps"
                  note={`${format((m.repeatedVisitRatio || 0) * 100, 1)}% repeated visits`}
                />
                <Metric
                  label="Movement safety"
                  value={format(m.collisions)}
                  unit="collisions"
                  note={`${format(m.preventedConflicts)} conflicts prevented`}
                />
              </div>
              <div className="studio-layout">
                <section className="simulation-panel">
                  <div className="panel-toolbar">
                    <div className="panel-tabs">
                      <button className="selected">Environment</button>
                      <button onClick={() => setPage("compare")}>
                        Comparison <ArrowRight size={12} />
                      </button>
                    </div>
                    <select
                      aria-label="Knowledge view"
                      value={mode}
                      onChange={(e) => setMode(e.target.value as KnowledgeMode)}
                    >
                      <option value="union">Collective knowledge</option>
                      <option value="agent">Selected agent knowledge</option>
                      <option value="coordinator">Coordinator knowledge</option>
                      <option value="truth">Evaluator ground truth</option>
                    </select>
                  </div>
                  <GridCanvas
                    snapshot={shown}
                    mode={mode}
                    selected={selected}
                    onSelect={setSelected}
                    paths={paths}
                  />
                  <div className="map-legend">
                    <span>
                      <i className="swatch unknown" />
                      Unknown
                    </span>
                    <span>
                      <i className="swatch explored" />
                      Explored
                    </span>
                    <span>
                      <i className="swatch obstacle" />
                      Obstacle
                    </span>
                    <span>
                      <i className="swatch target" />
                      Target
                    </span>
                    <span>
                      <i className="swatch zone" />
                      Priority
                    </span>
                    <span>
                      <Zap size={12} />
                      Charging
                    </span>
                    <label>
                      <input
                        type="checkbox"
                        checked={paths}
                        onChange={(e) => setPaths(e.target.checked)}
                      />
                      Paths
                    </label>
                  </div>
                  <div className="playback">
                    <div className="playback-actions">
                      <button
                        className="button primary"
                        disabled={busy || !runId}
                        onClick={run}
                      >
                        {status === "RUNNING" ? (
                          <Pause size={15} />
                        ) : (
                          <Play size={15} />
                        )}{" "}
                        {readOnly
                          ? "Comparison results"
                          : replayTick !== null
                            ? "Return to live"
                            : terminal(status)
                              ? "New run"
                              : status === "RUNNING"
                                ? "Pause"
                                : status === "PAUSED"
                                  ? "Resume exploration"
                                  : "Start exploration"}
                      </button>
                      <button
                        className="icon-button"
                        title="Single step"
                        aria-label="Single step"
                        disabled={
                          busy ||
                          readOnly ||
                          !runId ||
                          status === "RUNNING" ||
                          terminal(status)
                        }
                        onClick={() => perform(() => command("step"))}
                      >
                        <SkipForward size={17} />
                      </button>
                      <button
                        className="icon-button"
                        title="Stop"
                        aria-label="Stop simulation"
                        disabled={
                          busy || readOnly || !runId || terminal(status)
                        }
                        onClick={() => perform(() => command("stop"))}
                      >
                        <Square size={15} />
                      </button>
                      <button
                        className="icon-button"
                        title="Reset"
                        aria-label="Reset simulation"
                        disabled={
                          busy || readOnly || !runId || status === "RUNNING"
                        }
                        onClick={() => perform(() => command("reset"))}
                      >
                        <RotateCcw size={16} />
                      </button>
                    </div>
                    <label className="speed-label">
                      Speed{" "}
                      <input
                        aria-label="Simulation speed"
                        type="range"
                        min="1"
                        max="50"
                        value={speed}
                        disabled={readOnly}
                        onChange={(e) => {
                          const value = +e.target.value;
                          setSpeed(value);
                          if (runId && !readOnly)
                            api(`/runs/${runId}/commands`, {
                              command: "set_speed",
                              speed: value,
                            }).catch((e) => setError(e.message));
                        }}
                      />
                      <code>{speed} t/s</code>
                    </label>
                  </div>
                </section>
                <aside className="agent-panel">
                  <div className="panel-heading">
                    <h2>Agent inspector</h2>
                    <span>
                      {shown?.agents.filter((a) => a.status === "ACTIVE")
                        .length || 0}{" "}
                      active
                    </span>
                  </div>
                  <div className="agent-switcher">
                    {shown?.agents.map((a) => (
                      <button
                        aria-label={`Inspect agent ${a.id + 1}`}
                        className={selected === a.id ? "selected" : ""}
                        key={a.id}
                        onClick={() => setSelected(a.id)}
                      >
                        <i
                          style={{ background: colors[a.id % colors.length] }}
                        />
                        {String(a.id + 1).padStart(2, "0")}
                      </button>
                    ))}
                  </div>
                  {agent && (
                    <AgentInspector
                      agent={agent}
                      runId={runId}
                      tick={shown!.tick}
                      width={shown!.width}
                      onLocal={() => setMode("agent")}
                    />
                  )}
                  <div className="fault-controls">
                    <h3>Test resilience</h3>
                    <button
                      disabled={
                        busy ||
                        readOnly ||
                        terminal(status) ||
                        replayTick !== null ||
                        agent?.status !== "ACTIVE"
                      }
                      onClick={() => inject("agent_failure")}
                    >
                      <Activity size={14} />
                      Fail selected agent
                      <Plus size={13} />
                    </button>
                    <button
                      disabled={
                        busy ||
                        readOnly ||
                        terminal(status) ||
                        replayTick !== null
                      }
                      onClick={() => inject("partition")}
                    >
                      <Radio size={14} />
                      Partition network
                      <Plus size={13} />
                    </button>
                    <button
                      disabled={
                        busy ||
                        readOnly ||
                        terminal(status) ||
                        replayTick !== null
                      }
                      onClick={() => inject("block_cell")}
                    >
                      <Grid2X2 size={14} />
                      Block a corridor
                      <Plus size={13} />
                    </button>
                  </div>
                </aside>
              </div>
              <div className="lower-grid">
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Mission analytics</h2>
                    <select
                      aria-label="Analytics metric"
                      value={chartMetric}
                      onChange={(e) => setChartMetric(e.target.value)}
                    >
                      <option value="coverage">Coverage · %</option>
                      <option value="globalCoverage">
                        Global coverage · %
                      </option>
                      <option value="distance">Distance · steps</option>
                      <option value="nonproductiveMovement">
                        Nonproductive movement · steps
                      </option>
                      <option value="messageDeliveryRatio">
                        Message delivery ratio
                      </option>
                      <option value="energyConsumed">
                        Energy · milliunits
                      </option>
                      <option value="targetsFound">Target discoveries</option>
                      <option value="bytesAttempted">
                        Communication · bytes
                      </option>
                      <option value="expandedNodes">Search expansions</option>
                      <option value="replanning">Replanning operations</option>
                      <option value="tickMs">Engine tick · ms</option>
                      <option value="allocationMs">Allocation · ms</option>
                      <option value="planningMs">Planning · ms</option>
                      <option value="agentUtilization">
                        Agent utilization · %
                      </option>
                      <option value="mappingCoverage">
                        Observable map · %
                      </option>
                    </select>
                  </div>
                  <Chart
                    data={
                      replayTick === null
                        ? series
                        : series.filter((p) => p.tick <= (shown?.tick || 0))
                    }
                    dataKey={chartMetric}
                  />
                </section>
                <section className="panel event-panel">
                  <div className="panel-heading">
                    <h2>Mission events</h2>
                    <span>Tick / Event</span>
                  </div>
                  {importantEvents.length ? (
                    importantEvents.map((e, i) => (
                      <div className="event-row" key={`${e.sequence}-${i}`}>
                        <code>{String(e.tick).padStart(5, "0")}</code>
                        <span>
                          <i
                            className={
                              e.type.includes("failure")
                                ? "event-dot warning"
                                : "event-dot"
                            }
                          />
                          {text(e.type)}
                        </span>
                        {e.agentId !== undefined && e.agentId !== null && (
                          <small>A{e.agentId + 1}</small>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="empty-inline">
                      <Terminal size={18} />
                      <p>
                        Waiting for the first discovery.
                        <small>
                          Start exploration to record mission events.
                        </small>
                      </p>
                    </div>
                  )}
                </section>
              </div>
              <EventLog
                runId={runId}
                tick={shown?.tick || 0}
                throughTick={replayTick === null ? undefined : shown?.tick}
              />
              <div className="replay-bar">
                <div>
                  <RotateCcw size={15} />
                  <strong>Run replay</strong>
                  <span>
                    {replayTick === null
                      ? "Live state"
                      : `Recorded tick ${replayTick}`}
                  </span>
                </div>
                <input
                  aria-label="Replay tick"
                  type="range"
                  min="0"
                  max={snapshot?.tick || 0}
                  value={replayTick ?? snapshot?.tick ?? 0}
                  onChange={(e) => setReplayTick(+e.target.value)}
                />
                <button
                  onClick={() => {
                    setReplayTick(null);
                    setReplaySnapshot(undefined);
                  }}
                >
                  Live
                </button>
                <code>{shown?.stateHash?.slice(0, 10) || "—"}</code>
              </div>
            </>
          )}
          {page === "demos" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="breadcrumb">Ready for the presentation</div>
                  <h1>Demo scenarios</h1>
                  <p>Small maps. Real algorithms. Pick a scene and press Start in the studio.</p>
                </div>
                <span className="demo-size">16 × 16 grids · 2–4 agents</span>
              </div>
              <div className="demo-intro">
                <div><strong>A short route through CONFLUENCE</strong><p>Start with First discovery, then show teamwork, a disruption, and charging. Each scene opens a fresh saved run, ready to present.</p></div>
                <span>20 ticks / second<br /> · 400–600 tick limits</span>
              </div>
              <div className="demo-grid">
                {demos.map((demo, i) => (
                  <article className="demo-card" key={demo.id}>
                    <div className="demo-map" aria-hidden="true">
                      <svg viewBox="0 0 16 16">
                        {demoConfig(demo).map!.map((wall, p) => wall ? <rect key={p} x={p % 16} y={Math.floor(p / 16)} width="1" height="1" fill="#687b70" /> : null)}
                        {demoConfig(demo).starts.map((a) => <circle key={a.agentId} cx={a.x + .5} cy={a.y + .5} r=".45" fill={colors[a.agentId]} />)}
                      </svg>
                    </div>
                    <div className="demo-card-body">
                      <div className="demo-meta">Scene {i + 1} · {demo.agents} agents · up to {demo.ticks / 20}s at 20 t/s</div>
                      <h2>{demo.name}</h2>
                      <p>{demo.description}</p>
                      <div className="demo-timeline">{demo.timeline}</div>
                      <p className="demo-watch"><strong>Show this:</strong> {demo.watch}</p>
                      <div className="demo-actions"><span>{strategyNames[demo.strategy]}</span><button className="button" disabled={busy} onClick={() => launchDemo(demo)} aria-label={`Load ${demo.name}`}><Play size={14} />Load demo</button></div>
                    </div>
                  </article>
                ))}
              </div>
              <p className="muted demo-footnote">Playback time excludes setup and pauses; a scene may finish earlier. Disruption and battery scenes may end incomplete. You can change speed, pause, step, or reset from the studio.</p>
            </>
          )}
          {page === "overview" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="breadcrumb">Local workspace</div>
                  <h1>Exploration laboratory</h1>
                  <p>
                    Build a scenario. Inspect the decisions. Test the result.
                  </p>
                </div>
                <button
                  className="button primary"
                  onClick={() => setPage("demos")}
                >
                  <Play size={15} />
                  Open demo scenarios
                </button>
              </div>
              <div className="overview-mission">
                <div>
                  <Mark />
                  <h2>Many agents. One mission.</h2>
                  <p>
                    A software laboratory for exploring unknown environments
                    with algorithms you can inspect.
                  </p>
                  <button
                    className="button"
                    onClick={() => setConfigOpen(true)}
                  >
                    Create an environment
                    <ArrowRight size={15} />
                  </button>
                </div>
                <div>
                  <h3>Experiment pipeline</h3>
                  {[
                    "Generate a reproducible environment",
                    "Discover through local sensing",
                    "Allocate frontiers and plan paths",
                    "Measure, compare, and replay",
                  ].map((t, i) => (
                    <div className="pipeline-row" key={t}>
                      <code>0{i + 1}</code>
                      <span>{t}</span>
                      {i < 3 ? <ChevronDown size={14} /> : <Check size={14} />}
                    </div>
                  ))}
                </div>
              </div>
              <div className="section-heading">
                <h2>Scenario library</h2>
                <span>Six reproducible test conditions</span>
              </div>
              <div className="preset-grid">
                {presetNames.map((name, i) => (
                  <button
                    key={name}
                    disabled={busy}
                    onClick={() =>
                      perform(async () => {
                        setPreset(i);
                        await generatePreset(i);
                        setPage("studio");
                      })
                    }
                  >
                    <code>S{String(i + 1).padStart(2, "0")}</code>
                    <strong>{name}</strong>
                    <span>
                      {
                        [
                          "Reliable communication, all agents operational",
                          "Progressive discovery from incomplete maps",
                          "Delays, drops, and temporary network partitions",
                          "Unfinished work after a breakdown",
                          "Invalidate a route and inspect replanning",
                          "Finite batteries and charging stations",
                        ][i]
                      }
                    </span>
                    <ArrowRight size={17} />
                  </button>
                ))}
              </div>
              <RecentRuns rows={recent} onLoad={loadRun} />
            </>
          )}
          {page === "builder" && (
            <ScenarioBuilder
              scenario={scenario}
              busy={busy}
              onSave={async (name, config) => {
                await perform(async () => {
                  await stopActive();
                  const s = await api<Scenario>("/scenarios", { name, config });
                  setScenario(s);
                  adopt(
                    await api("/runs", {
                      scenarioId: s.id,
                      strategy,
                      planner,
                      pathfinder,
                    }),
                  );
                  await refresh();
                  setPage("studio");
                });
              }}
              onGenerate={() => setConfigOpen(true)}
            />
          )}
          {page === "compare" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="breadcrumb">Controlled evaluation</div>
                  <h1>{pageNames[page]}</h1>
                  <p>
                    Compare all five strategies on one saved scenario and seed, then inspect their paths side by side.
                  </p>
                </div>
                {batch && (
                  <a
                    className="button"
                    href={`/api/v1/experiments/${batch.id}/export`}
                    aria-disabled={batch.status === "RUNNING"}
                    title={
                      batch.status === "RUNNING"
                        ? "Finish or cancel the experiment before exporting"
                        : "Download the evidence archive"
                    }
                    onClick={(e) => {
                      if (batch.status === "RUNNING") e.preventDefault();
                    }}
                  >
                    <ArrowDownToLine size={15} />
                    Export evidence
                  </a>
                )}
              </div>
              <section className="experiment-config">
                <div>
                  <h2>One scenario, five strategies</h2>
                  <p>
                    Shared sensing, energy, A*, and reservation planning.
                  </p>
                </div>
                <label>
                  Scenario
                  <select value={studyScenarioId || scenario?.id || ""} onChange={(e) => setStudyScenarioId(e.target.value)}>
                    {!scenarios.length && <option value="">Create a scenario first</option>}
                    {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name} · seed {s.config.seed}</option>)}
                  </select>
                </label>
                <label>
                  Tick limit
                  <input
                    type="number"
                    min="1"
                    max="100000"
                    value={experimentTicks}
                    onChange={(e) => setExperimentTicks(+e.target.value)}
                  />
                </label>
                <button
                  className="button primary"
                  disabled={busy || batch?.status === "RUNNING"}
                  onClick={() => launchExperiment(true)}
                >
                  <FlaskConical size={15} />
                  Run comparison
                </button>
              </section>
              {batch ? (
                <>
                  <div className="section-heading">
                    <h2>
                      {batch.name} <Badge value={batch.status} />
                    </h2>
                    <span>
                      {batch.runs.filter((r) => terminal(r.status)).length} /{" "}
                      {batch.manifest.seeds.length *
                        batch.manifest.strategies.length}{" "}
                      runs
                      {batch.status === "RUNNING" && (
                        <button
                          className="text-button"
                          onClick={() =>
                            perform(async () => {
                              await api(`/experiments/${batch.id}/cancel`, {});
                              setBatch(await api(`/experiments/${batch.id}`));
                            })
                          }
                        >
                          Cancel batch
                        </button>
                      )}
                    </span>
                  </div>
                  <ComparisonTable batch={batch} />
                  <div className="method-note">
                    <ShieldCheck size={18} />
                    <p>
                      Paired seeds isolate allocation differences. All
                      strategies use the same sensors, communication medium,
                      energy rules, and movement arbiter. Confidence intervals
                      describe measured runs; they do not establish general
                      superiority.
                    </p>
                  </div>
                  <ExperimentAnalytics
                    key={`analytics-${batch.id}`}
                    batch={batch}
                  />
                  <ComparisonReplay key={batch.id} batch={batch} />
                </>
              ) : (
                <div className="empty-study">
                  <Workflow size={36} />
                  <h2>Make the comparison reproducible.</h2>
                  <p>
                    Run the five strategies against the same seeded maps.
                    Coverage, travel, energy, and communication are measured by
                    the C++ engine.
                  </p>
                  <div>
                    {strategies.map((s, i) => (
                      <span key={s}>
                        <code>0{i + 1}</code>
                        {strategyNames[s]}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
          {page === "experiments" && (
            <>
              <div className="page-heading">
                <div><div className="breadcrumb">Batch manager</div><h1>Experiments</h1><p>Define repeatable studies, track their runs, and keep the evidence in one place.</p></div>
                <button className="button" aria-label="Refresh experiments" title="Refresh experiments" disabled={busy} onClick={() => perform(refresh)}><RotateCcw size={15} />Refresh experiments</button>
              </div>
              <div className="experiment-manager-layout">
                <section className="experiment-definition">
                  <h2>New experiment</h2>
                  <p className="muted">Choose seeds and strategies for a sequential batch. Use Compare strategies for a quick single-seed comparison.</p>
                  <label>Experiment name<input value={experimentName} placeholder="e.g. Communication resilience study" maxLength={120} onChange={(e) => setExperimentName(e.target.value)} /></label>
                  <label>Saved scenario<select value={studyScenarioId || scenario?.id || ""} onChange={(e) => setStudyScenarioId(e.target.value)}>
                    {!scenarios.length && <option value="">Create a scenario first</option>}
                    {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.config.width} × {s.config.height}</option>)}
                  </select></label>
                  <div className="experiment-input-row">
                    <label>Seeds, separated by commas<input value={seeds} onChange={(e) => setSeeds(e.target.value)} /></label>
                    <label>Tick limit per run<input type="number" min="1" max="100000" value={experimentTicks} onChange={(e) => setExperimentTicks(+e.target.value)} /></label>
                  </div>
                  <fieldset className="experiment-strategies"><legend>Allocation strategies</legend>
                    {strategies.map((s) => <label key={s}><input type="checkbox" checked={studyStrategies.includes(s)} onChange={(e) => setStudyStrategies(e.target.checked ? strategies.filter((candidate) => candidate === s || studyStrategies.includes(candidate)) : studyStrategies.filter((candidate) => candidate !== s))} />{strategyNames[s]}</label>)}
                  </fieldset>
                  <div className="experiment-launch"><span>{seeds.split(",").map((s) => s.trim()).filter(Boolean).length} seeds × {studyStrategies.length} strategies = <strong>{seeds.split(",").map((s) => s.trim()).filter(Boolean).length * studyStrategies.length} runs</strong></span>
                    <button className="button primary" disabled={busy || batch?.status === "RUNNING" || !studyStrategies.length || !seeds.trim() || !scenarios.length} onClick={() => launchExperiment()}><FlaskConical size={15} />Start batch</button>
                  </div>
                </section>
                <section className="experiment-activity">
                  <h2>Batch activity</h2>
                  {batch ? <>
                    <div className="experiment-activity-title"><strong>{batch.name}</strong><Badge value={batch.status} /></div>
                    <p>{batch.runs.filter((r) => terminal(r.status)).length} of {batch.manifest.seeds.length * batch.manifest.strategies.length} runs finished</p>
                    <progress aria-label="Batch completion" max={batch.manifest.seeds.length * batch.manifest.strategies.length} value={batch.runs.filter((r) => terminal(r.status)).length} />
                    <dl className="experiment-facts"><div><dt>Seeds</dt><dd>{batch.manifest.seeds.join(", ")}</dd></div><div><dt>Strategies</dt><dd>{batch.manifest.strategies.length}</dd></div><div><dt>Execution</dt><dd>Sequential · native engine</dd></div></dl>
                    <div className="experiment-activity-actions">
                      <button className="button" onClick={() => setPage("compare")}><Workflow size={14} />Inspect comparison</button>
                      {batch.status === "RUNNING" ? <button className="text-button" disabled={busy} onClick={() => perform(async () => { await api(`/experiments/${batch.id}/cancel`, {}); setBatch(await api(`/experiments/${batch.id}`)); await refresh(); })}>Cancel remaining runs</button> : <a className="button" href={`/api/v1/experiments/${batch.id}/export`}><ArrowDownToLine size={14} />Export evidence</a>}
                    </div>
                    <p className="muted experiment-note">Completed runs remain saved when a batch is cancelled. Detailed charts and synchronized replay open in Compare strategies.</p>
                  </> : <div className="experiment-idle"><FlaskConical size={26} /><strong>No experiment selected</strong><p>Start a study or open one from the saved experiment list below.</p></div>}
                </section>
              </div>
              <div className="section-heading"><h2>Saved experiments</h2><span>{batchRows.length} saved batches</span></div>
              {batchRows.length ? <div className="table-wrap"><table>
                <thead><tr><th>Experiment</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>{batchRows.map((b) => <tr key={b.id}><td>{b.name}<small className="block mono">{b.id}</small></td><td><Badge value={b.status} /></td><td><div className="experiment-row-actions">
                  <button className="text-button" disabled={busy} onClick={() => perform(async () => setBatch(await api(`/experiments/${b.id}`)))}>View batch</button>
                  <button className="text-button" disabled={busy} onClick={() => perform(async () => { setBatch(await api(`/experiments/${b.id}`)); setPage("compare"); })}>Compare results <ArrowRight size={13} /></button>
                  {b.status !== "RUNNING" && <a className="text-button" href={`/api/v1/experiments/${b.id}/export`} aria-label={`Export ${b.name}`}><ArrowDownToLine size={13} />Export</a>}
                </div></td></tr>)}</tbody>
              </table></div> : <div className="experiment-empty-library"><h3>Your experiment history starts here.</h3><p>Named batches, statuses, comparison results, and downloadable evidence will appear here after you start a study.</p></div>}
            </>
          )}
          <footer className="sheet-footer">
            <span>
              <Network size={13} />
              CONFLUENCE · Adaptive multi-agent intelligence
            </span>
            <span>Deterministic simulation · Local execution</span>
          </footer>
        </main>
      </div>
      {configOpen && (
        <div className="modal-backdrop" role="presentation">
          <section
            className="config-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="config-title"
          >
            <div className="panel-heading">
              <h2 id="config-title">Configure exploration</h2>
              <button
                className="icon-button"
                aria-label="Close configuration"
                onClick={() => setConfigOpen(false)}
              >
                <X size={19} />
              </button>
            </div>
            <ConfigForm
              initial={scenario?.config || defaultConfig}
              preset={preset}
              setPreset={setPreset}
              strategy={strategy}
              setStrategy={setStrategy}
              planner={planner}
              setPlanner={setPlanner}
              pathfinder={pathfinder}
              setPathfinder={setPathfinder}
              busy={busy}
              onSubmit={(c) =>
                perform(async () => {
                  await create(c, presetNames[preset]);
                  setConfigOpen(false);
                  setPage("studio");
                })
              }
            />
          </section>
        </div>
      )}
    </div>
  );
}

function AgentInspector({
  agent: a,
  width,
  onLocal,
  runId,
  tick,
}: {
  agent: Agent;
  width: number;
  onLocal: () => void;
  runId: string;
  tick: number;
}) {
  const [tab, setTab] = useState<"state" | "decision" | "statistics">("state");
  return (
    <>
      <div className="agent-identity">
        <div
          className="agent-glyph"
          style={{ color: colors[a.id % colors.length] }}
        >
          <Network size={23} />
        </div>
        <div>
          <strong>Agent {String(a.id + 1).padStart(2, "0")}</strong>
          <span>{text(a.activity)}</span>
        </div>
        <Badge value={a.status} />
      </div>
      <div className="energy-heading">
        <span>Energy reserve</span>
        <strong>{format((100 * a.energy) / a.capacity, 1)}%</strong>
      </div>
      <div className="energy-track">
        <div
          style={{
            width: `${(100 * a.energy) / a.capacity}%`,
            background:
              a.energy / a.capacity < 0.2
                ? "#b95860"
                : colors[a.id % colors.length],
          }}
        />
      </div>
      <div className="inspector-tabs">
        <button
          className={tab === "state" ? "selected" : ""}
          onClick={() => setTab("state")}
        >
          State
        </button>
        <button
          className={tab === "decision" ? "selected" : ""}
          onClick={() => setTab("decision")}
        >
          Decision trace
        </button>
        <button
          className={tab === "statistics" ? "selected" : ""}
          onClick={() => setTab("statistics")}
        >
          Statistics
        </button>
      </div>
      {tab === "state" ? (
        <>
          <dl className="agent-details">
            <div>
              <dt>Position</dt>
              <dd>
                <code>{coordinate(a.position, width)}</code>
              </dd>
            </div>
            <div>
              <dt>Destination</dt>
              <dd>
                <code>{coordinate(a.task, width)}</code>
              </dd>
            </div>
            <div>
              <dt>Travelled</dt>
              <dd>
                {format(a.distance)} <span>steps</span>
              </dd>
            </div>
            <div>
              <dt>Planned path</dt>
              <dd>
                {Math.max(0, a.path.length - 1)} <span>steps</span>
              </dd>
            </div>
            <div>
              <dt>Communication</dt>
              <dd className={a.communication === "CONNECTED" ? "good" : ""}>
                <Radio size={12} />
                {text(a.communication)}
              </dd>
            </div>
            <div>
              <dt>Knowledge</dt>
              <dd>
                {a.map.filter((v) => v >= 0).length} <span>cells</span>
              </dd>
            </div>
            <div>
              <dt>Map revision</dt>
              <dd>{format(a.mapRevision)}</dd>
            </div>
            <div>
              <dt>Coordinator update</dt>
              <dd>
                {a.coordinatorAgeTicks === undefined
                  ? "Not recorded"
                  : a.coordinatorAgeTicks === null
                    ? "Not received"
                    : `${a.coordinatorAgeTicks} ticks ago`}
              </dd>
            </div>
          </dl>
          <button className="inspect-map" onClick={onLocal}>
            Inspect internal map
            <ArrowRight size={14} />
          </button>
          {a.energyLedger && (
            <details className="energy-ledger">
              <summary>Energy ledger · milliunits</summary>
              <p>
                Total consumed: {format(a.energySpent)} · charged:{" "}
                {format(a.energyCharged)}
              </p>
              <dl className="agent-details">
                {Object.entries(a.energyLedger).map(([action, cost]) => (
                  <div key={action}>
                    <dt>{text(action)}</dt>
                    <dd>{format(cost)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
          <details className="energy-ledger">
            <summary>Peer updates and claims · {a.claims.length}</summary>
            <dl className="agent-details">
              {(a.peerFreshness || []).map((peer) => (
                <div key={peer.agentId}>
                  <dt>Agent {peer.agentId + 1}</dt>
                  <dd>
                    {peer.ageTicks} ticks ago
                    {peer.suspected ? " · suspected" : ""}
                  </dd>
                </div>
              ))}
            </dl>
            {a.claims.slice(0, 12).map((claim) => (
              <p key={`${claim.cell}-${claim.owner}`}>
                {claim.confirmed ? "Claim" : "Bid"} · A{claim.owner + 1} ·{" "}
                {coordinate(claim.cell, width)} · expires {claim.expires}
              </p>
            ))}
            {!a.claims.length && <p>No current delivered claims.</p>}
            {a.claims.length > 12 && (
              <p>{a.claims.length - 12} more claims in the event log.</p>
            )}
          </details>
          <details className="energy-ledger">
            <summary>Recent movement rejections</summary>
            {a.recentRejections?.length ? (
              a.recentRejections
                .slice()
                .reverse()
                .map((rejection, index) => (
                  <p key={`${rejection.tick}-${index}`}>
                    Tick {rejection.tick} · {text(rejection.reason)} ·{" "}
                    {coordinate(rejection.to, width)}
                  </p>
                ))
            ) : (
              <p>No recent movement rejections.</p>
            )}
          </details>
        </>
      ) : tab === "statistics" ? (
        <AgentAnalytics runId={runId} agentId={a.id} tick={tick} />
      ) : (
        <div className="decision-list">
          {Object.keys(a.features).length > 0 && (
            <details className="decision-features" open>
              <summary>Why this task?</summary>
              <dl className="agent-details">
                {Object.entries(a.features).map(([factor, value]) => (
                  <div key={factor}>
                    <dt>{text(factor.replace(/([A-Z])/g, " $1"))}</dt>
                    <dd>{format(value, 4)}</dd>
                  </div>
                ))}
              </dl>
              <small>
                Normalized factors; score uses integer units of 0.0001. The
                allocator's rule determines selection.
              </small>
            </details>
          )}
          {Boolean(a.alternatives?.length) && (
            <details className="decision-features">
              <summary>
                Feasible alternatives · tick {a.alternativesTick}
              </summary>
              <small>
                Up to eight candidates from this agent's knowledge at
                assignment.
              </small>
              <dl className="agent-details">
                {a.alternatives!.map((option) => (
                  <div key={option.cell}>
                    <dt>{coordinate(option.cell, width)}</dt>
                    <dd>
                      {option.distance} steps · {format(option.features.score)}{" "}
                      utility
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          )}
          {a.decisions.length ? (
            a.decisions
              .slice(-4)
              .reverse()
              .map((d, i) => (
                <div key={`${d.tick}-${i}`}>
                  <small>Tick {d.tick}</small>
                  <strong>{text(d.reason)}</strong>
                  {d.features && (
                    <span>
                      Score {format(d.features.score)} · gain{" "}
                      {format(d.features.gain * 100, 1)}%
                    </span>
                  )}
                </div>
              ))
          ) : (
            <p className="muted">Decisions appear after allocation.</p>
          )}
        </div>
      )}
      <div className="assignment-note">
        <Target size={15} />
        <span>
          {a.coordinationStatus === "AWAITING_JOINT_PLAN"
            ? "Awaiting a coordinated path"
            : a.taskKind === "CHARGING"
              ? "Returning to a charging station"
              : a.taskKind === "PARKING"
                ? a.parkingReason === "CONGESTION"
                  ? "Moving aside to clear congestion"
                  : "Clearing the charging station"
                : a.task >= 0
                  ? "Assigned to an exploration frontier"
                  : "Awaiting a feasible frontier"}
          <small>
            {a.task >= 0
              ? `Lease expires at tick ${a.lease}`
              : "Uses available knowledge and energy"}
          </small>
        </span>
      </div>
    </>
  );
}

function ConfigForm({
  initial,
  preset,
  setPreset,
  strategy,
  setStrategy,
  planner,
  setPlanner,
  pathfinder,
  setPathfinder,
  busy,
  onSubmit,
}: {
  initial: Config;
  preset: number;
  setPreset: (n: number) => void;
  strategy: Strategy;
  setStrategy: (s: Strategy) => void;
  planner: string;
  setPlanner: (s: string) => void;
  pathfinder: string;
  setPathfinder: (s: string) => void;
  busy: boolean;
  onSubmit: (c: Config) => void;
}) {
  const [c, setC] = useState<Config>(() => ({
    ...structuredClone(initial),
    strategy,
    planner,
    pathfinder,
  }));
  const number = (
    key: "width" | "height" | "agentCount" | "targetCount" | "maxTicks",
    label: string,
    min: number,
    max: number,
  ) => (
    <label>
      {label}
      <input
        type="number"
        min={min}
        max={max}
        value={c[key]}
        onChange={(e) => setC({ ...c, [key]: +e.target.value })}
      />
    </label>
  );
  function choosePreset(index: number) {
    setPreset(index);
    const next = structuredClone(c);
    next.scenarioFamily = presetFamilies[index];
    next.sensorRadius = index === 1 ? 1 : 2;
    next.obstacleDensity = index === 1 ? 0.55 : 0.32;
    next.faultSchedule = [];
    next.communication = { ...defaultConfig.communication };
    next.energy.capacity = index === 5 ? 100000 : 100000000;
    if (index === 2) {
      next.communication.dropProbability = 0.1;
      next.communication.delayMaxTicks = 5;
      next.faultSchedule = [];
    }
    if (index === 3) next.faultSchedule = [];
    setC(next);
  }
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(c);
      }}
    >
      <p className="muted">
        A seed freezes the initial map. Each agent discovers its own
        environment.
      </p>
      <label>
        Scenario family
        <select value={preset} onChange={(e) => choosePreset(+e.target.value)}>
          {presetNames.map((p, i) => (
            <option key={p} value={i}>
              {p}
            </option>
          ))}
        </select>
      </label>
      <div className="form-grid">
        {number("width", "Grid width", 16, 256)}
        {number("height", "Grid height", 16, 256)}
        {number("agentCount", "Agents", 1, 32)}
        {number("targetCount", "Hidden targets", 0, 256)}
        <label>
          Random seed
          <input
            required
            pattern="[0-9]+"
            value={c.seed}
            onChange={(e) => setC({ ...c, seed: e.target.value })}
          />
        </label>
        {number("maxTicks", "Tick limit", 1, 100000)}
        <label>
          Obstacle density
          <input
            type="number"
            min=".05"
            max=".8"
            step=".01"
            value={c.obstacleDensity}
            onChange={(e) => setC({ ...c, obstacleDensity: +e.target.value })}
          />
        </label>
        <label>
          Allocation strategy
          <select
            value={c.strategy}
            onChange={(e) =>
              setC({ ...c, strategy: e.target.value as Strategy })
            }
          >
            {strategies.map((s) => (
              <option value={s} key={s}>
                {strategyNames[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Multi-agent planner
          <select
            value={c.planner}
            onChange={(e) => setC({ ...c, planner: e.target.value })}
          >
            <option value="reservations">Rolling reservations</option>
            <option value="cbs">Bounded CBS</option>
          </select>
        </label>
        <label>
          Spatial search
          <select
            value={c.pathfinder}
            onChange={(e) => setC({ ...c, pathfinder: e.target.value })}
          >
            <option value="astar">A*</option>
            <option value="bfs">BFS</option>
          </select>
        </label>
        <label>
          Sensor radius (cells)
          <input
            type="number"
            min="1"
            max="8"
            value={c.sensorRadius}
            onChange={(e) => setC({ ...c, sensorRadius: +e.target.value })}
          />
        </label>
        <label>
          Failure probability / tick
          <input
            type="number"
            min="0"
            max="1"
            step=".001"
            value={c.failureProbabilityPerTick || 0}
            onChange={(e) =>
              setC({ ...c, failureProbabilityPerTick: +e.target.value })
            }
          />
        </label>
        <label>
          Energy capacity
          <input
            type="number"
            min="10001"
            max="2000000000"
            value={c.energy.capacity}
            onChange={(e) =>
              setC({ ...c, energy: { ...c.energy, capacity: +e.target.value } })
            }
          />
        </label>
        <label>
          Communication drop probability
          <input
            type="number"
            min="0"
            max="1"
            step=".05"
            value={c.communication.dropProbability}
            onChange={(e) =>
              setC({
                ...c,
                communication: {
                  ...c.communication,
                  dropProbability: +e.target.value,
                },
              })
            }
          />
        </label>
        <label>
          Radio range (cells)
          <input
            type="number"
            min="1"
            max="1024"
            value={c.communication.rangeCells}
            onChange={(e) =>
              setC({
                ...c,
                communication: {
                  ...c.communication,
                  rangeCells: +e.target.value,
                },
              })
            }
          />
        </label>
        <label>
          Maximum delay (ticks)
          <input
            type="number"
            min="1"
            max="100"
            value={c.communication.delayMaxTicks}
            onChange={(e) =>
              setC({
                ...c,
                communication: {
                  ...c.communication,
                  delayMaxTicks: +e.target.value,
                },
              })
            }
          />
        </label>
      </div>
      {(c.width > 128 || c.height > 128 || c.agentCount > 16) && (
        <p className="warning-text">
          Experimental stress configuration. Responsiveness is not guaranteed.
        </p>
      )}
      {c.planner === "cbs" && (
        <p className="method-note small">
          CBS supports ≤32 × 32 and ≤8 agents. Unsupported or budget-limited
          instances explicitly fall back to reservations.
        </p>
      )}
      {preset === 4 && (
        <p className="muted">
          A valid corridor closure and reopening are scheduled automatically.
          Times scale with map size.
        </p>
      )}
      <div className="modal-footer">
        <span>
          <ShieldCheck size={14} />
          Algorithms execute in C++
        </span>
        <button className="button primary" type="submit" disabled={busy}>
          {busy ? "Generating…" : "Generate environment"}
          <ArrowRight size={15} />
        </button>
      </div>
    </form>
  );
}

function RecentRuns({
  rows,
  onLoad,
}: {
  rows: RunRow[];
  onLoad: (id: string) => void;
}) {
  return (
    <>
      <div className="section-heading">
        <h2>Recent simulations</h2>
        <span>{rows.length} saved runs</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Allocation</th>
              <th>Status</th>
              <th className="num">Ticks</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 8).map((r) => (
              <tr key={r.id}>
                <td>
                  <code>{r.id.slice(0, 8)}</code>
                </td>
                <td>{strategyNames[r.strategy]}</td>
                <td>
                  <Badge value={r.status} />
                </td>
                <td className="num">{format(r.tick)}</td>
                <td>
                  <button className="text-button" onClick={() => onLoad(r.id)}>
                    Inspect
                    <ArrowRight size={13} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && (
          <p className="empty-inline">
            Your first simulation will appear here.
          </p>
        )}
      </div>
    </>
  );
}

function ScenarioBuilder({
  scenario,
  busy,
  onSave,
  onGenerate,
}: {
  scenario?: Scenario;
  busy: boolean;
  onSave: (name: string, c: Config) => Promise<void>;
  onGenerate: () => void;
}) {
  const [config, setConfig] = useState<Config | undefined>(scenario?.config),
    [brush, setBrush] = useState("wall"),
    [name, setName] = useState(scenario?.name || "Custom environment"),
    [startId, setStartId] = useState(0);
  useEffect(() => {
    setConfig(scenario?.config);
    setName(scenario?.name || "Custom environment");
  }, [scenario?.id]);
  const paint = (p: number) => {
    setConfig((old) => {
      if (!old?.map) return old;
      const c = structuredClone(old),
        x = p % c.width,
        y = Math.floor(p / c.width);
      const important =
        c.starts.some((a) => a.x === x && a.y === y) ||
        c.chargingStations.some((a) => a.x === x && a.y === y);
      if (brush === "wall" && !important) {
        c.map![p] = 1;
        if (c.targets) c.targets[p] = 0;
      }
      if (brush === "free") c.map![p] = 0;
      if (brush === "target") {
        c.map![p] = 0;
        c.targets = c.targets || Array(c.width * c.height).fill(0);
        c.targets![p] = 1;
      }
      if (brush === "erase") {
        c.map![p] = 0;
        if (c.targets) c.targets[p] = 0;
        if (c.zones) c.zones[p] = 0;
        c.chargingStations = c.chargingStations.filter(
          (s) => s.x !== x || s.y !== y,
        );
      }
      if (brush === "zone") {
        c.map![p] = 0;
        c.zones = c.zones || Array(c.width * c.height).fill(0);
        c.zones[p] = 100;
      }
      if (brush === "start") {
        c.map![p] = 0;
        c.starts = c.starts.map((a) =>
          a.agentId === startId ? { ...a, x, y } : a,
        );
      }
      if (brush === "station") {
        c.map![p] = 0;
        if (!c.chargingStations.some((s) => s.x === x && s.y === y))
          c.chargingStations.push({ id: `station-${p}`, x, y });
      }
      return c;
    });
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="breadcrumb">Environment design</div>
          <h1>Scenario builder</h1>
          <p>
            Paint a map, place starts and targets, then validate its topology.
          </p>
        </div>
        <button className="button" onClick={onGenerate}>
          <RotateCcw size={15} />
          Procedural generator
        </button>
      </div>
      {config ? (
        <>
          <div className="builder-toolbar">
            <label>
              Scenario name
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <div className="brushes">
              {[
                "wall",
                "free",
                "target",
                "zone",
                "start",
                "station",
                "erase",
              ].map((b) => (
                <button
                  key={b}
                  className={brush === b ? "selected" : ""}
                  onClick={() => setBrush(b)}
                >
                  {b}
                </button>
              ))}
            </div>
            {brush === "start" && (
              <select
                aria-label="Start agent"
                value={startId}
                onChange={(e) => setStartId(+e.target.value)}
              >
                {config.starts.map((a) => (
                  <option value={a.agentId} key={a.agentId}>
                    Agent {a.agentId + 1}
                  </option>
                ))}
              </select>
            )}
            <button
              disabled={busy}
              className="button primary"
              onClick={() => onSave(name, config)}
            >
              Validate & save
              <Check size={15} />
            </button>
          </div>
          <GridCanvas editConfig={config} onPaint={paint} />
          <div className="builder-footer">
            <label>
              <input
                type="checkbox"
                checked={config.allowDisconnected}
                onChange={(e) =>
                  setConfig({ ...config, allowDisconnected: e.target.checked })
                }
              />
              Allow disconnected free regions
            </label>
            <span>
              {config.width} × {config.height} · {config.starts.length} starts ·{" "}
              {config.chargingStations.length} stations ·{" "}
              {config.targets?.filter(Boolean).length || 0} targets
            </span>
          </div>
          <p className="method-note">
            <Info size={17} />
            Walls cannot overwrite starts or charging stations. Overlapping
            starts and disconnected maps are checked before saving.
          </p>
          <details className="advanced-config">
            <summary>Fault schedule and advanced settings</summary>
            <JsonConfig
              key={scenario?.id}
              config={config}
              onChange={setConfig}
            />
          </details>
        </>
      ) : (
        <div className="empty-study">
          <Grid2X2 size={32} />
          <h2>Create an environment first.</h2>
          <button className="button" onClick={onGenerate}>
            Generate map
          </button>
        </div>
      )}
    </>
  );
}
function JsonConfig({
  config,
  onChange,
}: {
  config: Config;
  onChange: (c: Config) => void;
}) {
  const [value, setValue] = useState(
      JSON.stringify(
        {
          faultSchedule: config.faultSchedule,
          energy: config.energy,
          communication: config.communication,
          adaptiveWeights: config.adaptiveWeights,
          adaptiveCoordinatorEnabled: config.adaptiveCoordinatorEnabled ?? true,
        },
        null,
        2,
      ),
    ),
    [err, setErr] = useState("");
  return (
    <div>
      <p className="muted">
        Edit faults, energy, and communication. The server validates all values
        when saving.
      </p>
      <textarea
        aria-label="Advanced scenario configuration"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button
        className="button"
        onClick={() => {
          try {
            const p = JSON.parse(value);
            onChange({
              ...config,
              faultSchedule: p.faultSchedule,
              energy: p.energy,
              communication: p.communication,
              adaptiveWeights: p.adaptiveWeights,
              adaptiveCoordinatorEnabled: p.adaptiveCoordinatorEnabled ?? true,
            });
            setErr("Applied to draft");
          } catch {
            setErr("Invalid JSON");
          }
        }}
      >
        Apply to draft
      </button>
      <span>{err}</span>
    </div>
  );
}

function ComparisonTable({ batch }: { batch: Batch }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Allocation strategy</th>
            <th className="num">Runs</th>
            <th className="num">Coverage</th>
            <th className="num">Distance</th>
            <th className="num">Energy</th>
            <th className="num">Communication</th>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => {
            const stats = batch.summary[s];
            return (
              <tr key={s}>
                <td>
                  <strong>{strategyNames[s]}</strong>
                  <small className="block">
                    {s === "adaptive"
                      ? "Proposed policy · under evaluation"
                      : s === "hungarian"
                        ? "Optimal fixed-matrix matching"
                        : s === "decentralized"
                          ? "Delivered peer bids and claims"
                          : s === "independent"
                            ? "Ignores other assignments"
                            : "Lowest-cost feasible pairs"}
                  </small>
                </td>
                <td className="num">{stats?.coverage?.n || 0}</td>
                <td className="num">
                  {stats?.coverage?.mean === undefined
                    ? "—"
                    : `${format(stats.coverage.mean, 1)}%`}
                  <small className="block">
                    {stats?.coverage?.n === 1
                      ? "Single measured run"
                      : stats?.coverage?.ci95
                        ? `95% CI ${format(stats.coverage.ci95[0], 1)}–${format(stats.coverage.ci95[1], 1)}`
                        : (stats?.coverage?.n || 0) > 1
                          ? "Interval after completion"
                          : "Awaiting measured runs"}
                  </small>
                </td>
                <td className="num">
                  {format(stats?.distance?.mean, 1)}
                  <small className="block">steps</small>
                </td>
                <td className="num">
                  {format(stats?.energyConsumed?.mean)}
                  <small className="block">milliunits</small>
                </td>
                <td className="num">
                  {stats?.bytesAttempted?.mean === undefined
                    ? "—"
                    : format(stats.bytesAttempted.mean / 1024, 1)}
                  <small className="block">KiB attempted</small>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ComparisonReplay({ batch }: { batch: Batch }) {
  const completed = batch.runs.filter((r) => terminal(r.status));
  const [left, setLeft] = useState(""),
    [right, setRight] = useState(""),
    [tick, setTick] = useState(0),
    [states, setStates] = useState<(Snapshot | undefined)[]>([]),
    [err, setErr] = useState("");
  useEffect(() => {
    if (completed.length && !left) setLeft(completed[0].id);
    if (completed.length > 1 && !right) setRight(completed[1].id);
  }, [completed.length]);
  useEffect(() => {
    if (!left) return;
    let disposed = false;
    const timer = setTimeout(
      () =>
        Promise.all([
          api<Snapshot>(`/runs/${left}/snapshot?tick=${tick}`),
          right
            ? api<Snapshot>(`/runs/${right}/snapshot?tick=${tick}`)
            : Promise.resolve(undefined),
        ])
          .then((s) => {
            if (!disposed) setStates(s);
          })
          .catch((e) => setErr(e.message)),
      100,
    );
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [left, right, tick]);
  if (!completed.length) return null;
  const max = Math.max(
    ...completed
      .filter((r) => r.id === left || r.id === right)
      .map((r) => r.tick),
  );
  return (
    <section className="comparison-replay">
      <div className="section-heading">
        <h2>Side-by-side replay</h2>
        <span>Recorded state · tick {tick}</span>
      </div>
      <div className="compare-panes">
        {[left, right].map((id, i) => (
          <section key={i}>
            <select
              aria-label={
                i === 0 ? "Left comparison run" : "Right comparison run"
              }
              value={id}
              onChange={(e) => (i === 0 ? setLeft : setRight)(e.target.value)}
            >
              <option value="">Select run</option>
              {completed.map((r) => (
                <option key={r.id} value={r.id}>
                  {strategyNames[r.strategy]} · seed {r.seed} · {text(r.status)}
                </option>
              ))}
            </select>
            <GridCanvas compact snapshot={states[i]} />
            <div className="compare-readout">
              <span>
                Tick <strong>{format(states[i]?.tick)}</strong>
              </span>
              <span>
                Coverage{" "}
                <strong>{format(states[i]?.metrics.coverage, 1)}%</strong>
              </span>
              <span>
                Distance <strong>{format(states[i]?.metrics.distance)}</strong>
              </span>
            </div>
          </section>
        ))}
      </div>
      <input
        aria-label="Comparison replay tick"
        type="range"
        min="0"
        max={max || 1}
        value={tick}
        onChange={(e) => setTick(+e.target.value)}
      />
      {err && <p role="alert">{err}</p>}
    </section>
  );
}
