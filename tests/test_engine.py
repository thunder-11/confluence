import asyncio
from copy import deepcopy
import pytest
from backend.engine import Engine


def execute(config, ticks=100):
    async def run():
        engine = await Engine().open()
        try:
            initial = await engine.call("initialize", config)
            states = [initial["snapshot"]]
            events = list(initial["events"])
            for _ in range(ticks):
                result = await engine.call("advance", {"ticks": 1})
                states.append(result["snapshot"])
                events.extend(result["events"])
                if states[-1]["status"] != "RUNNING":
                    break
            return initial, states, events
        finally:
            await engine.close()

    return asyncio.run(run())


def fixture_config(**overrides):
    size = 16
    cells = [
        int(x in (0, size - 1) or y in (0, size - 1))
        for y in range(size)
        for x in range(size)
    ]
    result = {
        "width": size,
        "height": size,
        "agentCount": 2,
        "map": cells,
        "targets": [0] * (size * size),
        "starts": [{"agentId": 0, "x": 2, "y": 2}, {"agentId": 1, "x": 13, "y": 13}],
        "chargingStations": [
            {"id": "s0", "x": 2, "y": 2},
            {"id": "s1", "x": 13, "y": 13},
        ],
        "energy": {"capacity": 100000000},
        "maxTicks": 1000,
    }
    result.update(overrides)
    return result


@pytest.mark.parametrize(
    "strategy", ["independent", "greedy", "hungarian", "decentralized", "adaptive"]
)
def test_strategies_explore_and_preserve_safety(strategy):
    initial, states, events = execute(fixture_config(strategy=strategy), 1000)
    assert states[-1]["status"] == "COMPLETED"
    assert states[-1]["metrics"]["coverage"] == 100
    for previous, current in zip(states, states[1:]):
        positions = [a["position"] for a in current["agents"]]
        assert len(set(positions)) == len(positions)
        assert not (
            positions[0] == previous["agents"][1]["position"]
            and positions[1] == previous["agents"][0]["position"]
        )
        assert all(a["energy"] >= 0 for a in current["agents"])
    if strategy == "decentralized":
        assert any(e["type"] == "bid" for e in events)
    if strategy in {"greedy", "hungarian"}:
        assert any(e["type"] == "assignment_acknowledged" for e in events)


def test_reproducible_generation_and_state_hashes():
    cfg = {"width": 16, "height": 16, "seed": "999", "energy": {"capacity": 100000000}}
    a, states_a, _ = execute(cfg, 60)
    b, states_b, _ = execute(cfg, 60)
    assert a["scenario"] == b["scenario"]
    assert [s["stateHash"] for s in states_a] == [s["stateHash"] for s in states_b]


def test_hidden_obstacle_cannot_change_initial_decisions():
    a = fixture_config(strategy="independent", communication={"dropProbability": 1})
    b = deepcopy(a)
    b["map"][8 * 16 + 8] = 1
    _, sa, _ = execute(a, 2)
    _, sb, _ = execute(b, 2)
    for aa, bb in zip(sa[-1]["agents"], sb[-1]["agents"]):
        assert aa["map"] == bb["map"]
        assert aa["task"] == bb["task"]
        assert aa["features"] == bb["features"]
        assert aa["alternatives"] == bb["alternatives"]
        assert aa["path"] == bb["path"]


def test_failure_and_suspicion_are_distinct():
    _, states, events = execute(
        fixture_config(
            faultSchedule=[{"type": "agent_failure", "tick": 20, "agentId": 1}],
            strategy="adaptive",
        ),
        60,
    )
    assert states[-1]["agents"][1]["status"] == "FAILED"
    failures = [e for e in events if e["type"] == "agent_failure"]
    detections = [e for e in events if e["type"] == "failure_detection"]
    assert failures and detections
    assert detections[0]["tick"] > failures[0]["tick"]


def test_partition_preserves_local_operation():
    _, states, events = execute(
        fixture_config(
            strategy="decentralized",
            faultSchedule=[
                {"type": "partition", "tick": 10, "endTick": 50, "split": 1}
            ],
        ),
        70,
    )
    assert states[45]["metrics"]["distance"] > states[10]["metrics"]["distance"]
    assert any(e["type"] == "message_dropped" for e in events)
    assert any(e["type"] == "message_delivered" and e["tick"] > 50 for e in events)


def test_dynamic_obstacle_is_observed_and_reopens():
    _, states, events = execute(
        fixture_config(
            faultSchedule=[
                {"type": "block_cell", "tick": 1, "x": 3, "y": 2, "unblockTick": 5}
            ]
        ),
        8,
    )
    assert states[1]["truth"][35] == 1
    assert states[5]["truth"][35] == 0
    assert any(e["type"] == "obstacle_unblocked" for e in events)


def test_all_agents_unavailable_terminates():
    _, states, _ = execute(
        fixture_config(
            faultSchedule=[
                {"type": "agent_failure", "tick": 1, "agentId": 0},
                {"type": "agent_failure", "tick": 1, "agentId": 1},
            ]
        ),
        5,
    )
    assert states[-1]["status"] == "EXHAUSTED"


def test_energy_accounting_no_negative_values():
    cfg = fixture_config(
        energy={
            "capacity": 15000,
            "reserve": 1000,
            "movementCost": 1000,
            "sensingCost": 100,
            "transmitCostPerByte": 0,
            "receiveCostPerByte": 0,
        }
    )
    _, states, events = execute(cfg, 100)
    assert all(0 <= a["energy"] <= a["capacity"] for s in states for a in s["agents"])
    final = states[-1]
    for agent in final["agents"]:
        assert sum(agent["energyLedger"].values()) == agent["energySpent"]
        assert agent["energyLedger"].get("movement", 0) == agent["distance"] * 1000
    assert (
        sum(a["energy"] for a in final["agents"])
        + final["metrics"]["energyConsumed"]
        - final["metrics"]["energyCharged"]
        == 30000
    )
    assert any(
        e["type"] == "decision" and e["payload"]["reason"] == "energy_return"
        for e in events
    )


def test_cbs_fallback_is_explicit():
    _, states, events = execute({"planner": "cbs", "maxTicks": 2}, 2)
    assert states[-1]["metrics"]["plannerFallbacks"] > 0
    assert any(e["type"] == "planner_fallback" for e in events)


def test_seeded_failure_probability():
    config = fixture_config(failureProbabilityPerTick=1)
    _, states, events = execute(config, 2)
    assert all(a["status"] == "FAILED" for a in states[0]["agents"])
    assert states[-1]["status"] == "EXHAUSTED"


def test_runtime_cbs_uses_delivered_joint_plans():
    cfg = {
        "width": 16,
        "height": 16,
        "agentCount": 4,
        "strategy": "independent",
        "planner": "cbs",
        "maxTicks": 600,
        "energy": {"capacity": 100000000},
    }
    _, states, events = execute(cfg, 600)
    assert states[-1]["status"] == "COMPLETED"
    assert any(e["type"] == "joint_plan_committed" for e in events)
    assert any(
        e["type"] == "message_delivered" and e["payload"]["kind"] == "joint_prepare"
        for e in events
    )
    assert any(
        e["type"] == "message_delivered" and e["payload"]["kind"] == "joint_ack"
        for e in events
    )
    for state in states:
        for agent in state["agents"]:
            assert all(agent["map"][p] == 0 for p in agent["path"])


def test_repeated_failure_episodes_are_retained():
    config = fixture_config(
        faultSchedule=[
            {"type": "agent_failure", "tick": 4, "agentId": 1, "restorationTick": 10},
            {"type": "agent_failure", "tick": 15, "agentId": 1},
        ],
        strategy="independent",
    )
    _, states, events = execute(config, 40)
    episodes = states[-1]["recovery"]
    assert len(episodes) == 2 and len({e["episodeId"] for e in episodes}) == 2
    assert [e["failureTick"] for e in episodes] == [4, 15]


def test_automatic_dynamic_scenario_contains_real_faults():
    initial, states, events = execute(
        {
            "width": 16,
            "height": 16,
            "scenarioFamily": "dynamic",
            "strategy": "independent",
            "maxTicks": 100,
            "energy": {"capacity": 100000000},
        },
        40,
    )
    assert initial["scenario"]["config"]["faultSchedule"]
    assert any(e["type"] == "obstacle_blocked" for e in events)


def test_completion_covers_observable_boundaries_and_drains_messages():
    _, states, events = execute(fixture_config(strategy="independent"), 1000)
    assert states[-1]["status"] == "COMPLETED"
    assert states[-1]["metrics"]["mappingCoverage"] == 100
    assert states[-1]["metrics"]["explorationCompletionTick"] <= states[-1]["tick"]
    assert all(a["task"] == -1 for a in states[-1]["agents"])


@pytest.mark.parametrize("density", [0.05, 0.32, 0.8])
def test_requested_interior_density_and_target_count_are_exact(density):
    initial, _, _ = execute(
        {
            "width": 32,
            "height": 32,
            "obstacleDensity": density,
            "targetCount": 20,
            "seed": "123",
        },
        0,
    )
    c = initial["scenario"]["config"]
    assert sum(v == 0 for v in c["map"]) == int(30 * 30 * (1 - density))
    assert sum(c["targets"]) == 20


def test_resource_limited_agents_recharge_and_make_progress():
    cfg = fixture_config(
        strategy="independent",
        energy={
            "capacity": 20000,
            "reserve": 2000,
            "chargingRate": 3000,
            "transmitCostPerByte": 0,
            "receiveCostPerByte": 0,
        },
    )
    cfg["starts"] = [{"agentId": 0, "x": 2, "y": 2}, {"agentId": 1, "x": 3, "y": 2}]
    cfg["chargingStations"] = [{"id": "shared", "x": 2, "y": 2}]
    _, states, events = execute(cfg, 200)
    assert any(e["type"] == "charge_complete" for e in events)
    assert any(e["type"] == "station_queue_entered" for e in events)
    assert not any(
        a["status"] == "DEPLETED" for state in states for a in state["agents"]
    )
    assert states[-1]["metrics"]["distance"] > 10


def test_tiny_capacity_exhausts_instead_of_charging_forever():
    _, states, _ = execute(
        fixture_config(
            energy={
                "capacity": 1000,
                "reserve": 100,
                "transmitCostPerByte": 0,
                "receiveCostPerByte": 0,
            }
        ),
        500,
    )
    assert states[-1]["status"] == "EXHAUSTED"


def test_cbs_communication_outage_has_bounded_fallback():
    cfg = {
        "width": 16,
        "height": 16,
        "agentCount": 2,
        "strategy": "independent",
        "planner": "cbs",
        "communication": {"dropProbability": 1},
        "energy": {"capacity": 10000000},
        "maxTicks": 80,
    }
    _, states, events = execute(cfg, 80)
    assert any(
        e["type"] == "planner_fallback" and "TIMEOUT" in e["payload"]["reason"]
        for e in events
    )
    assert states[-1]["metrics"]["distance"] > 0
    assert any(a["distance"] > 0 for a in states[5]["agents"])


def test_disconnected_target_chamber_reports_reachable_and_global_separately():
    cfg = fixture_config(agentCount=1, allowDisconnected=True, strategy="independent")
    cfg["starts"] = [{"agentId": 0, "x": 2, "y": 2}]
    cfg["chargingStations"] = [{"id": "s0", "x": 2, "y": 2}]
    for y in range(16):
        cfg["map"][y * 16 + 8] = 1
    cfg["targets"][13 * 16 + 13] = 1
    _, states, _ = execute(cfg, 1000)
    final = states[-1]
    assert final["status"] == "COMPLETED"
    assert final["metrics"]["coverage"] == 100
    assert final["metrics"]["globalCoverage"] < 100
    assert final["reachableTargetsDiscovered"] and not final["allTargetsDiscovered"]


def test_delayed_coordinator_handshake_falls_back_to_peer_auction():
    cfg = fixture_config(
        strategy="adaptive", communication={"delayMinTicks": 2, "delayMaxTicks": 5}
    )
    _, states, events = execute(cfg, 250)
    assert any(e["type"] == "coordinator_deadline_missed" for e in events)
    assert any(e["type"] == "bid" for e in events)
    assert states[-1]["metrics"]["coverage"] > 80


def test_unknown_maze_finishes_boundary_mapping_after_long_detours():
    _, states, _ = execute(
        {
            "width": 32,
            "height": 32,
            "seed": "100",
            "obstacleDensity": 0.55,
            "sensorRadius": 1,
            "strategy": "independent",
            "energy": {"capacity": 100000000},
            "maxTicks": 1500,
        },
        1500,
    )
    assert states[-1]["status"] == "COMPLETED"
    assert states[-1]["metrics"]["mappingCoverage"] == 100


def test_productivity_and_communication_metrics_reconcile_with_events():
    _, states, events = execute(fixture_config(strategy="independent"), 100)
    final = states[-1]
    metrics = final["metrics"]
    classified = [e for e in events if e["type"] == "movement_productivity"]
    assert metrics["nonproductiveMovement"] == sum(
        not e["payload"]["productive"] for e in classified
    )
    assert metrics["productiveMovement"] == sum(
        e["payload"]["productive"] for e in classified
    )
    assert (
        metrics["distance"]
        == metrics["nonproductiveMovement"]
        + metrics["productiveMovement"]
        + metrics["unclassifiedMovement"]
    )
    counters = final["communicationCounters"]
    assert metrics["messagesAttempted"] == sum(counters["attemptedMessages"].values())
    assert metrics["messagesDelivered"] == sum(counters["deliveredMessages"].values())
    assert metrics["bytesAttempted"] == sum(counters["attemptedBytes"].values())
    assert metrics["bytesDelivered"] == sum(counters["deliveredBytes"].values())
    assert metrics["messagesDelivered"] == sum(
        e["type"] == "message_delivered" for e in events
    )


def test_batched_advance_preserves_every_tick_measurement_and_final_hash():
    async def run():
        first, second = await Engine().open(), await Engine().open()
        try:
            cfg = fixture_config(strategy="independent")
            await first.call("initialize", cfg)
            await second.call("initialize", cfg)
            for _ in range(10):
                sequential = await first.call("advance", {"ticks": 1})
            batched = await second.call("advance", {"ticks": 10})
            assert [m["tick"] for m in batched["measurements"]] == list(range(1, 11))
            assert (
                batched["snapshot"]["stateHash"] == sequential["snapshot"]["stateHash"]
            )
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())


def test_adaptive_peer_only_ablation_does_not_accept_coordinator_assignments():
    _, states, events = execute(
        fixture_config(strategy="adaptive", adaptiveCoordinatorEnabled=False), 60
    )
    assert states[-1]["metrics"]["distance"] > 0
    assert any(e["type"] == "bid" for e in events)
    assert not any(e["type"] == "assignment_acknowledged" for e in events)


def test_charging_replaces_movement_and_sensing_and_agent_ledgers_balance():
    cfg = fixture_config(
        strategy="independent",
        energy={
            "capacity": 15000,
            "reserve": 1000,
            "transmitCostPerByte": 0,
            "receiveCostPerByte": 0,
        },
    )
    _, states, _ = execute(cfg, 150)
    charged = False
    for previous, current in zip(states, states[1:]):
        for old, new in zip(previous["agents"], current["agents"]):
            assert (
                new["energy"] + new["energySpent"] - new["energyCharged"]
                == new["capacity"]
            )
            if new["energyCharged"] > old["energyCharged"]:
                charged = True
                assert new["position"] == old["position"]
                assert new["energyLedger"].get("sensing", 0) == old["energyLedger"].get(
                    "sensing", 0
                )
                assert new["energyLedger"].get("movement", 0) == old[
                    "energyLedger"
                ].get("movement", 0)
    assert charged


def test_native_protocol_rejects_invalid_fault_without_crashing():
    async def run():
        engine = await Engine().open()
        try:
            await engine.call("initialize", fixture_config())
            with pytest.raises(ValueError, match="missing agent"):
                await engine.call(
                    "queue_fault", {"type": "agent_failure", "tick": 1, "agentId": 1000}
                )
            assert (await engine.call("advance", {"ticks": 1}))["snapshot"]["tick"] == 1
        finally:
            await engine.close()

    asyncio.run(run())


def test_frontier_components_are_known_free_unknown_boundaries_with_stable_ids():
    _, states, _ = execute(fixture_config(strategy="independent"), 40)
    for state in states:
        for agent in state["agents"]:
            for region in agent["regions"]:
                assert region["id"].startswith(f"a{agent['id']}-f")
                for cell in region["cells"]:
                    assert agent["map"][cell] == 0
                    x, y = cell % 16, cell // 16
                    neighbors = [
                        ny * 16 + nx
                        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
                        if 0 <= nx < 16 and 0 <= ny < 16
                    ]
                    assert any(agent["map"][p] == -1 for p in neighbors)


@pytest.mark.parametrize("strategy", ["greedy", "hungarian", "adaptive"])
def test_acknowledged_coordinator_domain_has_unique_agents_and_frontier_components(
    strategy,
):
    _, states, events = execute(fixture_config(strategy=strategy), 150)
    assert any(e["type"] == "assignment_acknowledged" for e in events)
    for state in states:
        claims = state["coordinatorClaims"]
        assert len({c["owner"] for c in claims}) == len(claims)
        assert len({c["cell"] for c in claims}) == len(claims)
        known = state["coordinatorMap"]
        frontier = set()
        neighbors = lambda p: [
            y * 16 + x
            for x, y in (
                (p % 16, p // 16 - 1),
                (p % 16 + 1, p // 16),
                (p % 16, p // 16 + 1),
                (p % 16 - 1, p // 16),
            )
            if 0 <= x < 16 and 0 <= y < 16
        ]
        for cell, value in enumerate(known):
            if value == 0 and any(known[p] == -1 for p in neighbors(cell)):
                frontier.add(cell)
        while frontier:
            group = {frontier.pop()}
            pending = list(group)
            while pending:
                for cell in neighbors(pending.pop()):
                    if cell in frontier:
                        frontier.remove(cell)
                        group.add(cell)
                        pending.append(cell)
            assert sum(c["cell"] in group for c in claims) <= 1
