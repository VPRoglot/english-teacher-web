import { test as base, expect, type Browser, type Page } from "@playwright/test";

import { BASE_URL } from "./env";

/** Сообщения браузера о нарушении Content Security Policy (nginx отдаёт CSP на каждый ответ). */
const CSP_PATTERN = /Content Security Policy|Refused to/;

/** Собирает CSP-нарушения страницы из консоли и необработанных ошибок. */
function watchCsp(page: Page, sink: string[]): void {
  page.on("console", (message) => {
    const text = message.text();
    if (CSP_PATTERN.test(text)) sink.push(`console.${message.type()}: ${text}`);
  });
  page.on("pageerror", (error) => {
    const text = `${error.name}: ${error.message}`;
    if (CSP_PATTERN.test(text)) sink.push(`pageerror: ${text}`);
  });
}

function assertNoCsp(violations: string[]): void {
  expect(violations, `Нарушения CSP:\n${violations.join("\n")}`).toEqual([]);
}

type Who = "anonymous" | { storageState: string };

type Fixtures = {
  /**
   * Новая страница в отдельном контексте браузера (второй участник сценария: посетитель,
   * родитель, ребёнок). По умолчанию анонимная. Те же проверки CSP, что у `page`.
   */
  openPage: (who?: Who) => Promise<Page>;
};

async function newContextPage(browser: Browser, who: Who): Promise<Page> {
  const context = await browser.newContext({
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
    timezoneId: "Europe/Moscow",
    viewport: { width: 1280, height: 720 },
    storageState: who === "anonymous" ? { cookies: [], origins: [] } : who.storageState,
  });
  return context.newPage();
}

export const test = base.extend<Fixtures>({
  page: async ({ page }, use) => {
    const violations: string[] = [];
    watchCsp(page, violations);
    await use(page);
    assertNoCsp(violations);
  },

  openPage: async ({ browser }, use, testInfo) => {
    const opened: Page[] = [];
    const violations: string[] = [];
    await use(async (who = "anonymous") => {
      const page = await newContextPage(browser, who);
      watchCsp(page, violations);
      opened.push(page);
      return page;
    });
    for (const [index, page] of opened.entries()) {
      // Скриншот второй страницы при падении: у встроенного `page` он делается автоматически.
      if (testInfo.status !== testInfo.expectedStatus && !page.isClosed()) {
        await testInfo.attach(`openPage-${index + 1}`, {
          body: await page.screenshot({ fullPage: true }),
          contentType: "image/png",
        });
      }
      await page.context().close();
    }
    assertNoCsp(violations);
  },
});

export { expect };

/** Пояс репетитора по умолчанию: формы админки вводят местное время в нём. */
export const TUTOR_TIME_ZONE = "Europe/Moscow";

/** Дата `YYYY-MM-DD` через `days` дней от сегодня в поясе репетитора. */
export function localDate(days: number): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TUTOR_TIME_ZONE }).format(
    Date.now() + days * 86_400_000,
  );
}

/** Карточка ребёнка на странице семьи в админке. */
export function childCard(page: Page, name: string) {
  return page
    .locator('[data-slot="card"]')
    .filter({ has: page.locator('[data-slot="card-title"]').getByText(name, { exact: true }) });
}

/** Страница семьи в админке: через карточку заявки, ставшей семьёй. */
export async function openFamily(page: Page, leadParentName: string): Promise<void> {
  await page.goto("/admin/leads");
  await page.getByRole("link", { name: leadParentName }).click();
  await page.getByRole("link", { name: "Открыть семью" }).click();
  await expect(page).toHaveURL(/\/admin\/families\/[0-9a-f-]+$/);
}

/** Вход через форму /login; ждёт ухода со страницы входа. */
export async function login(page: Page, loginName: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email или логин").fill(loginName);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}
