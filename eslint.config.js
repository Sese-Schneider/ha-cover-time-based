import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import globals from "globals";

export default [
  {
    ignores: ["node_modules/**", "coverage/**", "htmlcov/**", ".venv/**"],
  },
  js.configs.recommended,
  {
    // Honor the codebase's throwaway conventions: `_`-prefixed args/vars and
    // caught errors are intentionally unused, and a name destructured only to
    // exclude it from a `...rest` (e.g. `const { entry_id, ...fields }`) is not
    // a dead variable.
    rules: {
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
    },
  },
  {
    // The Lovelace card frontend: runs in the browser inside Home Assistant.
    files: ["custom_components/**/frontend/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
      },
    },
  },
  {
    // Frontend unit tests: happy-dom (browser globals) under Node/Vitest.
    files: ["tests/frontend/**/*.{js,mjs}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
  // Keep ESLint's opinions off anything Prettier owns (must be last).
  prettier,
];
