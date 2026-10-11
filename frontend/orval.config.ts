import { defineConfig } from "orval";

// Источник — openapi.json, который выгружает backend: `just gen-api`.
export default defineConfig({
  api: {
    input: "./openapi.json",
    output: {
      client: "react-query",
      httpClient: "fetch",
      mode: "tags-split",
      target: "src/api/generated/endpoints",
      schemas: "src/api/generated/model",
      clean: true,
      override: {
        mutator: { path: "src/lib/api-fetch.ts", name: "apiFetch" },
        // apiFetch возвращает тело ответа, а не {data, status, headers}.
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
  zod: {
    input: "./openapi.json",
    output: {
      client: "zod",
      mode: "tags-split",
      target: "src/api/generated/zod",
      clean: true,
    },
  },
});
