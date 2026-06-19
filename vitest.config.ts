import { defineConfig } from "vitest/config";

const FRONTEND = "custom_components/cover_time_based/frontend";

export default defineConfig({
  resolve: {
    alias: [
      // Production loads lit from unpkg at runtime; rewrite that exact URL
      // (with or without the ?module query) to the npm package for tests.
      {
        find: /^https:\/\/unpkg\.com\/lit-element@2\.4\.0\/lit-element\.js(\?module)?$/,
        replacement: "lit-element",
      },
    ],
  },
  test: {
    environment: "happy-dom",
    include: ["tests/frontend/**/*.test.mjs"],
    setupFiles: ["tests/frontend/helpers/setup.mjs"],
    coverage: {
      provider: "v8",
      include: [`${FRONTEND}/*.js`],
      reporter: ["text", "html"],
      thresholds: { lines: 90, functions: 90, statements: 90, branches: 90 },
    },
  },
});
