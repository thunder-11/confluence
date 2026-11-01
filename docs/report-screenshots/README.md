# CONFLUENCE report screenshots

All twelve JPEG files are **1280 × 720 (16:9)** captures of the actual locally running application. They were captured directly through the browser screenshot API, without image generation, redrawing, or shrinking a full page. Separate views are provided where the interface uses tabs or different knowledge modes.

| Figure | Image file | Suggested caption |
|---|---|---|
| 2 | figure-2-simulation-studio.jpg | Simulation Studio showing the environment, four agents, planned movement, and live exploration. |
| 3(a) | figure-3a-agent-state.jpg | Agent inspector showing position, destination, energy, communication, and local knowledge. |
| 3(b) | figure-3b-decision-trace.jpg | Agent inspector showing the allocation decision trace and score factors. |
| 3(c) | figure-3c-agent-statistics.jpg | Agent inspector showing recorded per-agent statistics. |
| 4(a) | figure-4a-agent-partial-map.jpg | Selected-agent knowledge view showing a partially observed environment. |
| 4(b) | figure-4b-evaluator-view.jpg | Evaluator view of the same environment and tick, revealing simulator ground truth. |
| 5(a) | figure-5a-resource-queue.jpg | Resource Constraints: Agent 2 queued beside the shared charging station. |
| 5(b) | figure-5b-agent-charging.jpg | Resource Constraints: Agent 1 charging while Agent 2 waits. |
| 6(a) | figure-6a-strategy-comparison.jpg | Comparison of five allocation strategies using recorded experiment outcomes. |
| 6(b) | figure-6b-comparison-analytics.jpg | Coverage trajectories and descriptive travel-distance statistics. |
| 7(a) | figure-7a-recorded-replay.jpg | Synchronized replay comparing independent and greedy exploration at tick 80. |
| 7(b) | figure-7b-experiment-export.jpg | Experiment manager showing the completed batch and evidence-export control. |

Figures 2–4 use the small Four-room team demonstration. Figure 5 uses an actual custom resource scenario with four agents, one shared charger, 18,000-milliunit capacity, 2,000 reserve, and 1,000 charging gain per tick. Transmission/reception energy costs are zero for this focused demonstration. At tick 8, Agent 1 is CHARGING and Agent 2 is QUEUED. The actual queue records are preserved in resource-capture-state.json.

Figures 6–7 show the saved batch `9ff01a3627b14192`, containing fifteen completed runs across five strategies and three seeds. These are illustrative application results, not the cancelled 900-run primary study, and do not establish adaptive-policy superiority. Figure 7(b) shows the export control; it does not represent a download-completion dialog.

Insert the separate images as subfigures when one report figure needs several interface views. Use the original files from the ZIP rather than a screenshot of the chat preview.
