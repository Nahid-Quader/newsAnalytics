import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The frontend calls /api/*; in development Vite forwards these to the FastAPI server.
const apiTarget = process.env.API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
});
