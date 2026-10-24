import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// Tauri 在 dev 下走 1420，Python bridge 跑在 8899
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },

  clearScreen: false,

  server: {
    port: 1420,
    strictPort: true,
    watch: {
      // Python 侧改动不需要触发前端热更新
      ignored: ["**/core/**", "**/database/**", "**/bridge/**", "**/ui/**"],
    },
  },

  build: {
    outDir: "dist",
    // WebView2 在 Windows 10 上是 Chromium 105
    target: "chrome105",
    minify: "esbuild",
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
});