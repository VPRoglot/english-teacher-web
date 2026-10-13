import { mkdir } from "node:fs/promises";
import path from "node:path";

import { chromium, expect, type FullConfig } from "@playwright/test";

import { BASE_URL, TUTOR, TUTOR_STATE } from "./env";

/**
 * Репетитор уже создан раннером (`e2e/create-tutor.sh` внутри api). Здесь — только вход
 * через форму и сохранение сессии: её берут сценарии по умолчанию (`use.storageState`).
 */
export default async function globalSetup(_config: FullConfig): Promise<void> {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ baseURL: BASE_URL, ignoreHTTPSErrors: true });
    const page = await context.newPage();
    await page.goto("/login");
    await page.getByLabel("Email или логин").fill(TUTOR.email);
    await page.getByLabel("Пароль", { exact: true }).fill(TUTOR.password);
    await page.getByRole("button", { name: "Войти" }).click();
    await expect(page).toHaveURL(/\/admin$/, { timeout: 30_000 });
    await mkdir(path.dirname(TUTOR_STATE), { recursive: true });
    await context.storageState({ path: TUTOR_STATE });
  } finally {
    await browser.close();
  }
}
