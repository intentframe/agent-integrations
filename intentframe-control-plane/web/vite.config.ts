import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // Git-tracked output — shipped with the Python package; installs skip npm when present.
    outDir: "../src/intentframe_control_plane/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:9720",
    },
  },
});
