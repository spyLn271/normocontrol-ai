import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts", "coverage/**"],
  },
  {
    rules: {
      "@typescript-eslint/consistent-type-imports": ["error", { fixStyle: "inline-type-imports" }],
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", ignoreRestSiblings: true },
      ],
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
  {
    // Компоненты Bklit UI ставятся из реестра shadcn как есть — линтуем, но не переписываем стиль.
    files: ["src/components/charts/**"],
    rules: {
      "@typescript-eslint/consistent-type-imports": "off",
    },
  },
];

export default config;
