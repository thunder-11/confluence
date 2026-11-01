import { defineConfig } from "@playwright/test";
import path from "node:path";
const python = path.resolve(
  "..",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
export default defineConfig({
  testDir: "e2e",
  use: { baseURL: "http://127.0.0.1:8010", headless: true },
  webServer: {
    command: `"${python}" -m uvicorn backend.main:app --host 127.0.0.1 --port 8010`,
    cwd: "..",
    url: "http://127.0.0.1:8010/api/v1/health",
    reuseExistingServer: false,
    env: {
      CONFLUENCE_DB: path.resolve("..", "data", `e2e-${process.pid}.sqlite3`),
    },
  },
  workers: 1,
});
