import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { i18nTransform } from "./i18n-vite-plugin";

// https://vite.dev/config/
export default defineConfig({
  plugins: [i18nTransform(), react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: {
    manifest: true,
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            // Group by actual load boundaries, keeping shared micro-chunks
            // from increasing cold-route requests and gzip overhead.
            { name: "bootstrap", tags: ["$initial"], priority: 20 },
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
    },
  },
});
