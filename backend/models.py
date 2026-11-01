from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Strategy = Literal["independent", "greedy", "hungarian", "decentralized", "adaptive"]


class Communication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rangeCells: int = Field(256, ge=1, le=1024)
    delayMinTicks: int = Field(1, ge=1, le=100)
    delayMaxTicks: int = Field(1, ge=1, le=100)
    dropProbability: float = Field(0, ge=0, le=1)
    heartbeatPeriodTicks: int = Field(5, ge=1, le=50)
    heartbeatTimeoutTicks: int = Field(15, ge=2, le=500)

    @model_validator(mode="after")
    def order(self):
        if self.delayMinTicks > self.delayMaxTicks:
            raise ValueError("delayMinTicks must not exceed delayMaxTicks")
        return self


class Energy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity: int = Field(100000, ge=1, le=2_000_000_000)
    movementCost: int = Field(1000, ge=1, le=1_000_000)
    sensingCost: int = Field(100, ge=0, le=1_000_000)
    waitingCost: int = Field(20, ge=0, le=1_000_000)
    transmitCostPerByte: int = Field(1, ge=0, le=100)
    receiveCostPerByte: int = Field(1, ge=0, le=100)
    chargingRate: int = Field(5000, ge=1, le=1_000_000_000)
    reserve: int = Field(10000, ge=0, le=1_000_000_000)

    @model_validator(mode="after")
    def enough(self):
        if self.reserve >= self.capacity:
            raise ValueError("reserve must be smaller than capacity")
        return self


class Point(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class Start(Point):
    agentId: int = Field(ge=0, le=31)


class Station(Point):
    id: str = Field(min_length=1, max_length=80)


class Fault(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["agent_failure", "agent_disable", "partition", "block_cell"]
    tick: int = Field(ge=0, le=100000)
    agentId: int | None = Field(None, ge=0, le=31)
    x: int | None = Field(None, ge=0)
    y: int | None = Field(None, ge=0)
    restorationTick: int | None = Field(None, ge=1)
    unblockTick: int | None = Field(None, ge=1)
    endTick: int | None = Field(None, ge=1)
    split: int | None = Field(None, ge=1, le=31)

    @model_validator(mode="after")
    def required(self):
        if (self.x is None) != (self.y is None):
            raise ValueError("coordinates require both x and y")
        if self.type.startswith("agent_") and self.agentId is None:
            raise ValueError("agent event requires agentId")
        if self.type == "block_cell" and (self.x is None or self.y is None):
            raise ValueError("block_cell requires coordinates")
        if self.type == "partition" and self.endTick is None:
            raise ValueError("partition requires endTick")
        for value in (self.restorationTick, self.unblockTick, self.endTick):
            if value is not None and value <= self.tick:
                raise ValueError("event end must be later than its start")
        return self


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1] = 1
    scenarioFamily: Literal[
        "normal",
        "unknown",
        "communication",
        "failure",
        "dynamic",
        "resources",
        "custom",
    ] = "normal"
    seed: str = "42"
    width: int = Field(64, ge=16, le=256)
    height: int = Field(64, ge=16, le=256)
    agentCount: int = Field(4, ge=1, le=32)
    obstacleDensity: float = Field(0.32, ge=0.05, le=0.8)
    targetCount: int = Field(20, ge=0, le=256)
    sensorRadius: int = Field(2, ge=1, le=8)
    allowDisconnected: bool = False
    starts: list[Start] = Field(default_factory=list)
    chargingStations: list[Station] = Field(default_factory=list)
    communication: Communication = Field(default_factory=Communication)
    energy: Energy = Field(default_factory=Energy)
    maxTicks: int = Field(10000, ge=1, le=100000)
    failureProbabilityPerTick: float = Field(0, ge=0, le=1)
    faultSchedule: list[Fault] = Field(default_factory=list, max_length=1000)
    map: list[Literal[0, 1]] | None = None
    targets: list[Literal[0, 1]] | None = None
    zones: list[int] | None = None
    strategy: Strategy = "adaptive"
    adaptiveCoordinatorEnabled: bool = True
    planner: Literal["reservations", "cbs"] = "reservations"
    pathfinder: Literal["astar", "bfs"] = "astar"
    reservationHorizon: int = Field(16, ge=4, le=64)
    adaptiveWeights: dict[str, int] = Field(
        default_factory=lambda: {
            "gain": 2500,
            "priority": 1500,
            "reliability": 1000,
            "communication": 1000,
            "distance": -1500,
            "energy": -1000,
            "uncertainty": -500,
            "workload": -400,
            "communicationCost": -300,
            "switching": -300,
        }
    )

    @model_validator(mode="after")
    def valid(self):
        if not self.seed.isdecimal() or not 0 <= int(self.seed) < 2**64:
            raise ValueError("seed must encode an unsigned 64-bit integer")
        size = self.width * self.height
        net = self.energy.chargingRate - self.energy.chargingRate // 4
        queue_cost = (
            ((self.energy.capacity + net - 1) // net)
            * (self.agentCount - 1)
            * (self.energy.waitingCost + self.energy.sensingCost)
        )
        if (
            queue_cost
            + size * (self.energy.movementCost + self.energy.sensingCost)
            + self.energy.reserve
            > 2**53 - 1
        ):
            raise ValueError(
                "derived energy estimates exceed the JSON safe-integer range"
            )
        allowed = {
            "gain",
            "priority",
            "reliability",
            "communication",
            "distance",
            "energy",
            "uncertainty",
            "workload",
            "communicationCost",
            "switching",
        }
        if set(self.adaptiveWeights) - allowed or any(
            abs(v) > 10000 for v in self.adaptiveWeights.values()
        ):
            raise ValueError(
                "invalid adaptive weight; use documented features with weights between -10000 and 10000"
            )
        for p in [*self.starts, *self.chargingStations]:
            if p.x >= self.width or p.y >= self.height:
                raise ValueError("point outside map")
        for f in self.faultSchedule:
            if f.agentId is not None and f.agentId >= self.agentCount:
                raise ValueError("fault references missing agent")
            if f.x is not None and (f.x >= self.width or f.y >= self.height):
                raise ValueError("fault outside map")
        if self.map is not None:
            if len(self.map) != size:
                raise ValueError("map size must equal width × height")
            if len(self.starts) != self.agentCount or not self.chargingStations:
                raise ValueError("custom maps require all starts and charging stations")
            if sorted(p.agentId for p in self.starts) != list(range(self.agentCount)):
                raise ValueError("agent IDs must be contiguous from zero")
            self.starts.sort(key=lambda p: p.agentId)
            positions = [p.y * self.width + p.x for p in self.starts]
            if len(set(positions)) != len(positions):
                raise ValueError("agent starts overlap")
            if len({(s.x, s.y) for s in self.chargingStations}) != len(
                self.chargingStations
            ) or len({s.id for s in self.chargingStations}) != len(
                self.chargingStations
            ):
                raise ValueError(
                    "charging stations must have distinct coordinates and IDs"
                )
            for p in [*self.starts, *self.chargingStations]:
                if self.map[p.y * self.width + p.x] != 0:
                    raise ValueError("starts and stations must occupy free cells")
            for values in (self.targets, self.zones):
                if values is not None and len(values) != size:
                    raise ValueError("target and zone arrays must match map size")
            if self.zones is not None and any(not 0 <= v <= 100 for v in self.zones):
                raise ValueError("zone priorities must be between 0 and 100")
            if self.zones is not None and any(
                v and self.map[i] for i, v in enumerate(self.zones)
            ):
                raise ValueError("zone markers must occupy free cells")
            if self.targets is not None and any(
                v and self.map[i] for i, v in enumerate(self.targets)
            ):
                raise ValueError("targets must occupy free cells")
            if self.targets is not None and sum(self.targets) > 256:
                raise ValueError("at most 256 target cells are supported")
        elif self.starts or self.chargingStations:
            raise ValueError("explicit starts/stations require a custom map")
        return self

    def engine_payload(self):
        return self.model_dump(exclude_none=True)


class CreateScenario(BaseModel):
    name: str = Field("Untitled environment", min_length=1, max_length=120)
    config: ScenarioConfig = Field(default_factory=ScenarioConfig)


class InjectFault(Fault):
    nextTick: bool = False


class CreateRun(BaseModel):
    scenarioId: str
    strategy: Strategy = "adaptive"
    planner: Literal["reservations", "cbs"] = "reservations"
    pathfinder: Literal["astar", "bfs"] = "astar"


class Command(BaseModel):
    command: Literal["start", "pause", "resume", "step", "stop", "reset", "set_speed"]
    speed: int = Field(10, ge=1, le=100)


class CreateExperiment(BaseModel):
    name: str = Field("Allocation comparison", max_length=120)
    scenarioId: str
    strategies: list[Strategy] = Field(
        default_factory=lambda: [
            "independent",
            "greedy",
            "hungarian",
            "decentralized",
            "adaptive",
        ],
        min_length=1,
        max_length=5,
    )
    seeds: list[str] = Field(
        default_factory=lambda: ["100", "101", "102"], min_length=1, max_length=100
    )
    maxTicks: int = Field(1000, ge=1, le=100000)
