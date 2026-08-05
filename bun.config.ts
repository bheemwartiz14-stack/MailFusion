// TypeScript configuration for bundling
import { defineConfig } from """""""""""""
import { resolve } from "path"
import { fileURLToPath } from "url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = resolve(__filename, "..")

export default defineConfig({
  root: resolve(__dirname, "src"),
  build: {
    outDir: resolve(__dirname, "js"),
    rollupOptions: {
      input: {
        inbox: resolve(__dirname, "src/inbox.ts"),
        compose: resolve(__dirname, "src/compose.ts"),
        mailfusion: resolve(__dirname, "src/mailfusion.ts"),
      },
      output: {
        entryFileNames: "[name].js",
        format: "es",
        globals: {
          alpinejs: "Alpine",
        },
      },
    },
    target: "es2022",
    minify: true,
    sourcemap: false,
    treeshake: true,
  },
  resolve: {
    alias: {
      "^@/(.*)$": resolve(__dirname, "src/$1"),
    },
    extensions: [".tsx", ".ts", ".js"],
  },
  external: ["alpinejs"],
  plugins: [],
})