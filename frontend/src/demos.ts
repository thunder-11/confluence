import { defaultConfig } from "./types";
import type { Config, Strategy } from "./types";

export interface Demo {
  id: string;
  name: string;
  description: string;
  watch: string;
  strategy: Strategy;
  agents: number;
  ticks: number;
  layout: "open" | "rooms";
  timeline: string;
}

export const demos: Demo[] = [
  { id: "first-discovery", name: "First discovery", description: "Two agents reveal a compact courtyard and find hidden targets.", watch: "Switch to selected-agent knowledge to see what each agent actually knows.", strategy: "independent", agents: 2, ticks: 400, layout: "open", timeline: "No disruptions · start here" },
  { id: "four-room-team", name: "Four-room team", description: "Four agents share discoveries across rooms connected by two doors per wall.", watch: "Turn on paths and inspect how greedy allocation divides the frontier tasks.", strategy: "greedy", agents: 4, ticks: 500, layout: "rooms", timeline: "Four agents · eight hidden targets" },
  { id: "radio-silence", name: "Radio silence", description: "A short network partition separates two groups, then reconnects them.", watch: "Inspect communication freshness, peer claims, and map sharing after reconnection.", strategy: "decentralized", agents: 4, ticks: 500, layout: "rooms", timeline: "Partition at tick 12 · reconnect at 42" },
  { id: "agent-recovery", name: "Agent recovery", description: "One agent fails temporarily while the rest of the team continues exploring.", watch: "Select Agent 2 before tick 20, then follow suspicion, lease expiry, and renewed work.", strategy: "adaptive", agents: 4, ticks: 600, layout: "rooms", timeline: "Agent 2 fails at tick 20 · restored at 65" },
  { id: "changing-route", name: "Changing route", description: "A doorway closes temporarily while another route remains available.", watch: "Use evaluator view to locate (8, 4); the event log records closure, postponement, and reopening.", strategy: "greedy", agents: 4, ticks: 500, layout: "rooms", timeline: "Door (8, 4) closes at tick 18 · opens at 55" },
  { id: "charging-break", name: "Charging break", description: "Two agents explore with small batteries and a nearby charger each.", watch: "Inspect the energy ledger and watch exploring change to returning and charging.", strategy: "independent", agents: 2, ticks: 600, layout: "open", timeline: "35,000 milliunit batteries · two chargers" },
];

export function demoConfig(demo: Demo): Config {
  const c = structuredClone(defaultConfig);
  Object.assign(c, { width: 16, height: 16, seed: "7", agentCount: demo.agents,
    targetCount: 8, sensorRadius: 2, maxTicks: demo.ticks,
    scenarioFamily: "custom", strategy: demo.strategy, planner: "reservations", pathfinder: "astar" });
  // Small, connected, hand-built maps. 0 = free; 1 = wall.
  c.map = Array.from({ length: 256 }, (_, p) => {
    const x = p % 16, y = Math.floor(p / 16);
    if (x === 0 || y === 0 || x === 15 || y === 15) return 1;
    if (demo.layout === "rooms" && ((x === 8 && y !== 4 && y !== 11) || (y === 8 && x !== 4 && x !== 11))) return 1;
    return 0;
  });
  const corners = [[2, 2], [13, 13], [13, 2], [2, 13]];
  c.starts = corners.slice(0, demo.agents).map(([x, y], agentId) => ({ agentId, x, y }));
  c.chargingStations = corners.slice(0, demo.agents).map(([x, y], i) => ({ id: `demo-charge-${i}`, x: x === 2 ? 3 : 12, y }));
  c.targets = Array(256).fill(0);
  for (const [x, y] of [[6, 2], [10, 2], [2, 6], [13, 6], [2, 10], [13, 10], [6, 13], [10, 13]]) c.targets[y * 16 + x] = 1;
  c.zones = Array(256).fill(0);
  c.communication.heartbeatPeriodTicks = 3;
  c.communication.heartbeatTimeoutTicks = 10;
  if (demo.id === "radio-silence") {
    c.communication.delayMaxTicks = 2;
    c.faultSchedule = [{ type: "partition", tick: 12, endTick: 42, split: 2 }];
  }
  if (demo.id === "agent-recovery") c.faultSchedule = [{ type: "agent_failure", tick: 20, agentId: 1, restorationTick: 65 }];
  if (demo.id === "changing-route") c.faultSchedule = [{ type: "block_cell", tick: 18, x: 8, y: 4, unblockTick: 55 }];
  if (demo.id === "charging-break") Object.assign(c.energy, { capacity: 35000, reserve: 5000, chargingRate: 5000, transmitCostPerByte: 0, receiveCostPerByte: 0 });
  return c;
}
