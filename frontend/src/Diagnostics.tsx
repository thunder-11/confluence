import { useEffect, useState, useRef } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { api } from "./types";
import type { Event } from "./types";
import { strategies, strategyNames } from "./types";
import type { Batch, Strategy } from "./types";

export function AgentAnalytics({
  runId,
  agentId,
  tick,
}: {
  runId: string;
  agentId: number;
  tick: number;
}) {
  const [series, setSeries] = useState<Record<string, number>[]>([]),
    [metric, setMetric] = useState("energy"),
    [error, setError] = useState("");
  const sample = Math.floor(tick / 5);
  useEffect(() => {
    let disposed = false;
    api<{ series: Record<string, number>[] }>(
      `/runs/${runId}/agents/${agentId}/metrics`,
    )
      .then((r) => {
        if (!disposed) {
          setSeries(r.series);
          setError("");
        }
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      });
    return () => {
      disposed = true;
    };
  }, [runId, agentId, sample]);
  return (
    <div className="agent-analytics">
      <label>
        History metric
        <select value={metric} onChange={(e) => setMetric(e.target.value)}>
          <option value="energy">Energy · milliunits</option>
          <option value="energySpent">Energy consumed</option>
          <option value="distance">Travel · steps</option>
          <option value="knownCells">Knowledge · cells</option>
          <option value="pathLength">Planned path · steps</option>
        </select>
      </label>
      <div style={{ height: 155, width: "100%" }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={series.filter((p) => p.tick <= tick)}
            margin={{ top: 15, right: 6, left: -28, bottom: 0 }}
          >
            <XAxis
              dataKey="tick"
              tick={{ fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              minTickGap={30}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={65}
            />
            <Tooltip
              labelFormatter={(v) => `Tick ${v}`}
              contentStyle={{ fontSize: 11 }}
            />
            <Line
              dataKey={metric}
              stroke="#177b72"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {error && <p role="alert">{error}</p>}
      <small>
        Persisted engine observations. Values are sampled for display.
      </small>
    </div>
  );
}

export function EventLog({
  runId,
  tick,
  throughTick,
}: {
  runId: string;
  tick: number;
  throughTick?: number;
}) {
  const [open, setOpen] = useState(false),
    [category, setCategory] = useState("all"),
    [events, setEvents] = useState<Event[]>([]),
    [follow, setFollow] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [hasOlder, setHasOlder] = useState(true);
  const sample = Math.floor(tick / 5);
  const requestId = useRef(0);
  const activeKey = useRef("");
  activeKey.current = runId + ":" + category + ":" + throughTick;
  async function fetchEvents(older = false) {
    if (!runId) return;
    const request = ++requestId.current;
    const key = activeKey.current;
    setBusy(true);
    setError("");
    const cursor =
      older && events.length
        ? Math.min(...events.map((e) => e.sequence || 0))
        : undefined;
    try {
      const result = await api<Event[]>(
        `/runs/${runId}/events?recent=true&limit=100&category=${category}${throughTick === undefined ? "" : `&throughTick=${throughTick}`}${cursor === undefined ? "" : `&beforeSequence=${cursor}`}`,
      );
      if (request !== requestId.current || key !== activeKey.current) return;
      setEvents((old) =>
        older ? [...old, ...result.reverse()].slice(0, 1000) : result.reverse(),
      );
      setHasOlder(result.length === 100);
    } catch (e) {
      if (request === requestId.current && key === activeKey.current)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (request === requestId.current) setBusy(false);
    }
  }
  useEffect(() => {
    if (open && follow) void fetchEvents();
  }, [open, runId, category, follow, sample, throughTick]);
  useEffect(() => {
    setEvents([]);
    setFollow(true);
    setHasOlder(true);
  }, [runId, category, throughTick]);
  return (
    <section className="event-log">
      <button
        className="event-log-toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}Full
        event log<span>Decisions, messages, failures, and planning traces</span>
      </button>
      {open && (
        <>
          <div className="event-log-controls">
            <select
              aria-label="Event category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="all">All events</option>
              <option value="decisions">Allocation decisions</option>
              <option value="communication">Communication</option>
              <option value="failures">Failure and recovery</option>
              <option value="resources">Charging and energy</option>
              <option value="discoveries">Target discoveries</option>
              <option value="planning">Planning and obstacles</option>
            </select>
            <label>
              <input
                type="checkbox"
                checked={follow}
                onChange={(e) => setFollow(e.target.checked)}
              />
              {throughTick === undefined ? "Follow live" : "Follow replay"}
            </label>
            <button
              className="icon-button"
              disabled={busy}
              aria-label="Refresh event log"
              onClick={() => void fetchEvents()}
            >
              <RefreshCw size={14} />
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
          <div className="event-log-rows">
            {events.length ? (
              events.map((e) => (
                <details key={e.sequence}>
                  <summary>
                    <code>{String(e.tick).padStart(5, "0")}</code>
                    <strong>{e.type.replaceAll("_", " ")}</strong>
                    <span>
                      {e.agentId === undefined || e.agentId === null
                        ? "System"
                        : `Agent ${e.agentId + 1}`}
                    </span>
                  </summary>
                  <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                </details>
              ))
            ) : (
              <p className="empty-inline">No events in this category.</p>
            )}
          </div>
          <div className="event-log-footer">
            <span>{events.length} events loaded</span>
            <button
              className="text-button"
              disabled={busy || !hasOlder || events.length >= 1000}
              onClick={() => {
                setFollow(false);
                void fetchEvents(true);
              }}
            >
              Load older events
            </button>
          </div>
        </>
      )}
    </section>
  );
}

const metricLabels: Record<string, string> = {
  coverage: "Exploration coverage",
  globalCoverage: "Global free-space coverage",
  mappingCoverage: "Observable map coverage",
  distance: "Travel distance",
  nonproductiveMovement: "Nonproductive movement",
  productiveMovement: "Productive movement",
  unclassifiedMovement: "Movement awaiting observation",
  energyPerObservedFreeCell: "Energy per observed free cell",
  messagesAttempted: "Messages attempted",
  messagesDelivered: "Messages delivered",
  messageDeliveryRatio: "Message delivery ratio",
  duplicateClaims: "Overlapping leased assignments",
  duplicateClaimTicks: "Duplicate claim pair-ticks",
  duplicateClaimEpisodes: "Duplicate claim episodes",
  energyConsumed: "Energy consumed",
  energyCharged: "Energy charged",
  bytesAttempted: "Communication attempted",
  bytesDelivered: "Communication delivered",
  targetsFound: "Targets discovered",
  targetDiscoveryRestrictedTicks: "Restricted target discovery time",
  repeatedVisitRatio: "Repeated visit ratio",
  collisions: "Committed collisions",
  preventedConflicts: "Prevented conflicts",
  replanning: "Replanning operations",
  assignmentChurn: "Assignment changes",
  assignmentRecoveryTicks: "Assignment recovery time",
  progressRecoveryTicks: "Progress recovery time",
  failureDetectionTicks: "Failure detection time",
  agentUtilization: "Agent utilization",
  tickMs: "Engine tick execution",
  allocationMs: "Allocation execution",
  planningMs: "Planning execution",
  expandedNodes: "Expanded search nodes",
};
const numeric = (value: number | undefined | null) =>
  value === undefined || value === null
    ? "—"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function ExperimentAnalytics({ batch }: { batch: Batch }) {
  const [seed, setSeed] = useState(batch.manifest.seeds[0] || "100"),
    [metric, setMetric] = useState("coverage"),
    [points, setPoints] = useState<Record<string, number>[]>([]),
    [error, setError] = useState("");
  const completed = batch.runs.filter(
    (r) => r.seed === seed && r.metrics && Object.keys(r.metrics).length > 0,
  );
  const signature = completed.map((r) => r.id).join(",");
  useEffect(() => {
    let disposed = false;
    setError("");
    Promise.all(
      completed.map(async (run) => ({
        strategy: run.strategy,
        series: (
          await api<{ series: Record<string, number | null>[] }>(
            `/runs/${run.id}/metrics`,
          )
        ).series,
      })),
    )
      .then((results) => {
        if (disposed) return;
        const samples = new Map<number, Record<string, number>>();
        for (const run of results)
          for (const point of run.series) {
            const tick = point.tick!;
            if (!samples.has(tick)) samples.set(tick, { tick });
            if (typeof point[metric] === "number")
              samples.get(tick)![run.strategy] = point[metric]!;
          }
        setPoints([...samples.values()].sort((a, b) => a.tick - b.tick));
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      });
    return () => {
      disposed = true;
    };
  }, [signature, metric]);
  const colors: Record<Strategy, string> = {
    independent: "#a0a8a2",
    greedy: "#57655c",
    hungarian: "#3975bc",
    decentralized: "#a57d28",
    adaptive: "#177b72",
  };
  return (
    <section className="experiment-analytics">
      <div className="section-heading">
        <h2>Measured trajectories</h2>
        <div className="analysis-controls">
          <select
            aria-label="Comparison chart seed"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          >
            {batch.manifest.seeds.map((value) => (
              <option key={value} value={value}>
                Seed {value}
              </option>
            ))}
          </select>
          <select
            aria-label="Comparison chart metric"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
          >
            {Object.entries(metricLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="strategy-legend">
        {strategies.map((strategy) => (
          <span key={strategy}>
            <i style={{ background: colors[strategy] }} />
            {strategyNames[strategy]}
          </span>
        ))}
      </div>
      {points.length ? (
        <div style={{ width: "100%", height: 245 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={points}
              margin={{ top: 10, left: -10, right: 20, bottom: 0 }}
            >
              <XAxis
                type="number"
                dataKey="tick"
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                minTickGap={45}
              />
              <YAxis
                domain={
                  metric.toLowerCase().includes("coverage") ||
                  metric === "agentUtilization"
                    ? [0, 100]
                    : ["auto", "auto"]
                }
                tick={{ fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                labelFormatter={(v) => `Tick ${v}`}
                formatter={(v, name) => [
                  numeric(Number(v)),
                  strategyNames[name as Strategy] || name,
                ]}
                contentStyle={{ fontSize: 12 }}
              />
              {strategies.map((strategy, index) => (
                <Line
                  key={strategy}
                  dataKey={strategy}
                  name={strategy}
                  stroke={colors[strategy]}
                  strokeWidth={strategy === "adaptive" ? 2.5 : 1.6}
                  strokeDasharray={
                    index === 0 ? "5 3" : index === 1 ? "2 3" : undefined
                  }
                  connectNulls
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="empty-inline">Trajectories appear when a run finishes.</p>
      )}
      <p className="muted">
        Each curve ends at its recorded final tick. Unmeasured recovery times
        are omitted.
      </p>
      {error && <p role="alert">{error}</p>}
      <DetailedMeasurements batch={batch} />
    </section>
  );
}

function DetailedMeasurements({ batch }: { batch: Batch }) {
  const [metric, setMetric] = useState("progressRecoveryTicks");
  const names = [
    ...new Set(
      Object.values(batch.summary).flatMap((group) => Object.keys(group)),
    ),
  ].sort();
  const unit =
    batch.runs.map((run) => run.measurements?.[metric]?.unit).find(Boolean) ||
    "";
  return (
    <>
      <div className="section-heading">
        <h2>Statistical detail</h2>
        <label className="measurement-picker">
          Metric
          <select
            aria-label="Detailed comparison metric"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
          >
            {[...new Set([metric, ...names])].map((name) => (
              <option key={name} value={name}>
                {metricLabels[name] || name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Strategy</th>
              <th className="num">Measured n</th>
              <th className="num">Mean</th>
              <th className="num">Median</th>
              <th className="num">Std. deviation</th>
              <th className="num">IQR</th>
              <th className="num">95% interval</th>
              <th className="num">Censored / N/A</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((strategy) => {
              const stats = batch.summary[strategy]?.[metric];
              const runs = batch.runs.filter(
                (run) => run.strategy === strategy,
              );
              const censored = runs.filter(
                  (run) => run.measurements?.[metric]?.status === "CENSORED",
                ).length,
                unavailable = runs.filter(
                  (run) =>
                    run.measurements?.[metric]?.status === "NOT_APPLICABLE",
                ).length;
              return (
                <tr key={strategy}>
                  <td>{strategyNames[strategy]}</td>
                  <td className="num">{stats?.n || 0}</td>
                  <td className="num">{numeric(stats?.mean)}</td>
                  <td className="num">{numeric(stats?.median)}</td>
                  <td className="num">{numeric(stats?.stddev)}</td>
                  <td className="num">{numeric(stats?.iqr)}</td>
                  <td className="num">
                    {stats?.n === 1
                      ? "Single run"
                      : stats?.ci95
                        ? `${numeric(stats.ci95[0])}–${numeric(stats.ci95[1])}`
                        : "—"}
                  </td>
                  <td className="num">
                    {censored} / {unavailable}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="method-caption">
        Unit:{" "}
        {unit === "engine"
          ? "not recorded in this older run"
          : unit || "not yet recorded"}
        . Missing measurements remain missing. Intervals use 10,000
        deterministic bootstrap resamples after the study finishes.
      </p>
    </>
  );
}
