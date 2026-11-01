# Interface validation

CONFLUENCE uses the `framed-sheet` app direction, seed 27178907, from the design-taste-frontend skill. A quiet green-gray navigation frame surrounds a white working sheet. IBM Plex Sans carries controls and prose; IBM Plex Mono is restricted to literal IDs, coordinates, ticks, and numerical inspection. Fonts are bundled locally.

The primary artifact is a real Canvas knowledge grid. The dark unknown field, progressively revealed rooms, numbered agents, frontier paths, and delivered-knowledge views are the product's visual signature. Analytics use measured engine data. Empty, failed, censored, stopped, and loading states are distinct.

The source gate reports **0 failures and 12 warnings**. Deliberate exceptions are documented: padded agent IDs are stable identities; monospace is used for technical values; shadows occur on the configuration and mobile-navigation overlays; the small contextual label belongs to the navigation frame; em dashes in missing numeric values are unavailable-data symbols. Agent identity colors extend beyond the chart palette so up to 32 agents remain distinguishable by both color and number. Comparison curves use the restrained chart palette and dash styles.

Browser QA checks the application at 1440 × 900, 768 × 1024, and 390 × 844. Page content does not overflow horizontally; wide statistical tables scroll internally. Mobile navigation opens and closes, controls wrap, inspector content stacks below the map, and canvases resize independently of engine state. A temporary viewport override is reset after verification.

The skill's separate Playwright inspector was replaced by the available computer-use browser APIs, which are required for browser interaction in this environment. Source lint, actual browser screenshots, DOM overflow measurements, and functional UI checks supply the verification evidence.
