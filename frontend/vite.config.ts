import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

/** Vite configuration: proxies API calls to the FastAPI backend on :8000. */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/sessions": "http://127.0.0.1:8000",
      "/movies": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/tests/setup.ts"],
  },
});
