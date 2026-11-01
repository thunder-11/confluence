import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", ws: true } } },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("recharts") ||
            id.includes("d3-") ||
            id.includes("react-smooth")
          )
            return "analytics";
          if (
            id.includes("node_modules/react/") ||
            id.includes("node_modules/react-dom/")
          )
            return "react-vendor";
        },
      },
    },
  },
});
