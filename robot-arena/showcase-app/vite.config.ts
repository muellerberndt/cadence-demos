import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The league's brains run in a web worker that loads Pyodide from the jsDelivr CDN; the
// wheel, the arena's Python sources and the robots' brains ship in public/pack.
export default defineConfig({
  plugins: [react()],
  server: { port: 8080 },
  worker: { format: "es" },
  build: { target: "es2022" },
});
