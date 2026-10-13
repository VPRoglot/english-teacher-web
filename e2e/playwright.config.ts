import { defineConfig, devices } from "@playwright/test";

import { BASE_URL, TUTOR_STATE } from "./env";

/**
 * Сценарии спеки 7.2 на production-подобном стеке (nginx + TLS на tutor.test).
 * Запуск — в контейнере `e2e` (`just e2e`). Файлы выполняются по порядку имён в одном worker:
 * сценарии делят базу и опираются на данные предыдущих.
 */
export default defineConfig({
  testDir: "tests",
  globalSetup: "./global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // Артефакты и отчёт — соседние папки внутри test-results/ (том на хост, в CI — артефакт):
  // отчёт HTML внутри outputDir Playwright считает конфликтом (он очищает свою папку).
  outputDir: "test-results/artifacts",
  reporter: [["list"], ["html", { outputFolder: "test-results/report", open: "never" }]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: BASE_URL,
    // Self-signed сертификат nginx на tutor.test.
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
    timezoneId: "Europe/Moscow",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    storageState: TUTOR_STATE,
  },
});
