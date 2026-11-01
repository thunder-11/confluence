export type Strategy =
  | "independent"
  | "greedy"
  | "hungarian"
  | "decentralized"
  | "adaptive";
export const strategies: Strategy[] = [
  "independent",
  "greedy",
  "hungarian",
  "decentralized",
  "adaptive",
];
export const strategyNames: Record<Strategy, string> = {
  independent: "Independent",
  greedy: "Greedy matching",
  hungarian: "Hungarian assignment",
  decentralized: "Decentralized auction",
  adaptive: "Adaptive cooperative",
};
const primaryColors = [
  "#177b72",
  "#3975bc",
  "#b98122",
  "#b95860",
  "#7458a0",
  "#697a3a",
  "#b26735",
  "#477c8e",
];
export const colors = Array.from(
  { length: 32 },
  (_, i) => primaryColors[i] || `hsl(${(i * 137.508) % 360} 48% 39%)`,
);
export interface Fault {
  type: "agent_failure" | "agent_disable" | "partition" | "block_cell";
  tick: number;
  agentId?: number;
  x?: number;
  y?: number;
  endTick?: number;
  split?: number;
  unblockTick?: number;
  restorationTick?: number;
}
export interface Config {
  schemaVersion: 1;
  seed: string;
  width: number;
  height: number;
  agentCount: number;
  obstacleDensity: number;
  targetCount: number;
  sensorRadius: number;
  allowDisconnected: boolean;
  maxTicks: number;
  starts: { agentId: number; x: number; y: number }[];
  chargingStations: { id: string; x: number; y: number }[];
  communication: {
    rangeCells: number;
    delayMinTicks: number;
    delayMaxTicks: number;
    dropProbability: number;
    heartbeatPeriodTicks: number;
    heartbeatTimeoutTicks: number;
  };
  energy: {
    capacity: number;
    movementCost: number;
    sensingCost: number;
    waitingCost: number;
    transmitCostPerByte: number;
    receiveCostPerByte: number;
    chargingRate: number;
    reserve: number;
  };
  faultSchedule: Fault[];
  map?: number[];
  targets?: number[];
  zones?: number[];
  strategy?: Strategy;
  planner?: string;
  pathfinder?: string;
  reservationHorizon?: number;
  adaptiveWeights?: Record<string, number>;
  adaptiveCoordinatorEnabled?: boolean;
  failureProbabilityPerTick?: number;
  scenarioFamily?:
    | "normal"
    | "unknown"
    | "communication"
    | "failure"
    | "dynamic"
    | "resources"
    | "custom";
}
export const defaultConfig: Config = {
  schemaVersion: 1,
  seed: "42",
  width: 64,
  height: 64,
  agentCount: 4,
  obstacleDensity: 0.32,
  targetCount: 20,
  sensorRadius: 2,
  allowDisconnected: false,
  maxTicks: 10000,
  starts: [],
  chargingStations: [],
  communication: {
    rangeCells: 256,
    delayMinTicks: 1,
    delayMaxTicks: 1,
    dropProbability: 0,
    heartbeatPeriodTicks: 5,
    heartbeatTimeoutTicks: 15,
  },
  energy: {
    capacity: 100000000,
    movementCost: 1000,
    sensingCost: 100,
    waitingCost: 20,
    transmitCostPerByte: 1,
    receiveCostPerByte: 1,
    chargingRate: 5000,
    reserve: 10000,
  },
  faultSchedule: [],
};
export interface Scenario {
  id: string;
  name: string;
  config: Config;
  mapHash: string;
  createdAt: string;
}
export interface Decision {
  tick: number;
  reason: string;
  task?: number;
  features?: Record<string, number>;
}
export interface Agent {
  id: number;
  position: number;
  status: string;
  activity: string;
  energy: number;
  capacity: number;
  distance: number;
  task: number;
  lease: number;
  path: number[];
  map: number[];
  mapRevision: number;
  communication: string;
  decisions: Decision[];
  features: Record<string, number>;
  claims: {
    cell: number;
    owner: number;
    score: number;
    expires: number;
    confirmed?: boolean;
  }[];
  coordinatorAgeTicks?: number | null;
  peerFreshness?: { agentId: number; ageTicks: number; suspected: boolean }[];
  recentRejections?: {
    tick: number;
    from: number;
    to: number;
    reason: string;
  }[];
  energySpent: number;
  energyCharged?: number;
  knownTargets?: number[];
  knownZones?: number[];
  visitedCells?: number[];
  sensedCells?: number;
  utilization?: number;
  regions?: { id: string; cells: number[] }[];
  assignedRegion?: string;
  taskKind?: string;
  parkingReason?: string;
  energyLedger?: Record<string, number>;
  alternatives?: {
    cell: number;
    distance: number;
    features: Record<string, number>;
  }[];
  alternativesTick?: number;
  coordinationStatus?: string;
  knownAgents?: {
    id: number;
    position: number;
    status: string;
    observedTick: number;
  }[];
}
export interface Snapshot {
  coordinatorClaims?: {
    cell: number;
    owner: number;
    expiry: number;
    acknowledgedTick: number;
  }[];
  truthZones?: number[];
  unionZones?: number[];
  coordinatorZones?: number[];
  phase?: string;
  jointPlannerPhase?: string;
  coordinatorTargets?: number[];
  coordinatorAgents?: {
    id: number;
    position: number;
    status: string;
    observedTick: number;
    task: number;
  }[];
  stationQueues?: {
    cell: number;
    queue: { agentId: number; requestTick: number }[];
  }[];
  tick: number;
  status: string;
  width: number;
  height: number;
  strategy: Strategy;
  planner: string;
  truth: number[];
  coordinatorMap: number[];
  unionMap: number[];
  stations: number[];
  targets: { cell: number; discovered: boolean; tick: number }[];
  agents: Agent[];
  metrics: Record<string, number>;
  stateHash: string;
}
export interface Event {
  sequence?: number;
  tick: number;
  type: string;
  agentId?: number;
  payload: Record<string, unknown>;
}
export interface RunRow {
  measurements?: Record<
    string,
    { value: number | null; unit: string; status: string }
  >;
  id: string;
  batch_id?: string | null;
  scenario_id: string;
  strategy: Strategy;
  planner: string;
  status: string;
  tick: number;
  started_at: string;
  termination_reason?: string;
  seed?: string;
  metrics?: Record<string, number>;
}
export interface Summary {
  n: number;
  mean?: number;
  stddev?: number;
  median?: number;
  q1?: number;
  q3?: number;
  iqr?: number;
  ci95?: number[];
}
export interface Batch {
  id: string;
  name: string;
  status: string;
  runs: RunRow[];
  manifest: { seeds: string[]; strategies: Strategy[] };
  summary: Record<string, Record<string, Summary>>;
  pairedCoverageVsIndependent: Record<string, Summary>;
}
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    "/api/v1" + path,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok) {
    const fields = Array.isArray(result.details)
      ? result.details
          .slice(0, 3)
          .map(
            (e: { loc?: string[]; msg?: string }) =>
              `${e.loc?.filter((p) => p !== "body").join(".") || "configuration"}: ${e.msg}`,
          )
          .join("; ")
      : "";
    throw new Error(
      (result.message || result.detail || "Request failed") +
        (fields ? ": " + fields : ""),
    );
  }
  return result;
}
export const terminal = (s: string) =>
  ["COMPLETED", "EXHAUSTED", "TIMED_OUT", "STOPPED", "FAILED"].includes(s);
