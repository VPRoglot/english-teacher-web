import type { Page } from "@playwright/test";

import { LEAD, PARENT, SIBLING } from "../env";
import { childCard, expect, localDate, login, openFamily, test } from "../fixtures";

const WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];

/** Ежедневное расписание ребёнку с завтрашнего дня: ближайшие занятия всегда в будущем. */
async function createDailySeries(page: Page, childName: string, time: string): Promise<void> {
  await childCard(page, childName).getByRole("button", { name: "Добавить расписание" }).click();
  const dialog = page.getByRole("dialog", { name: "Новое расписание" });
  for (const day of WEEKDAYS) {
    await dialog.getByRole("checkbox", { name: day, exact: true }).click();
  }
  await dialog.getByLabel("Время", { exact: true }).fill(time);
  await dialog.getByLabel("Начало").fill(localDate(1));
  await dialog.getByRole("button", { name: "Создать" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(/^Расписание создано: \d+/).first()).toBeVisible();
  await expect(childCard(page, childName).getByText(time)).toBeVisible();
}

test("репетитор создаёт серию, родитель видит занятия в календаре", async ({ page, openPage }) => {
  await openFamily(page, LEAD.parentName);

  // Второй ребёнок: его занятия не должен видеть первый (сценарий 7).
  await page.getByRole("button", { name: "Добавить ребёнка" }).click();
  const childDialog = page.getByRole("dialog", { name: "Добавить ребёнка" });
  await childDialog.getByLabel("Имя").fill(SIBLING.name);
  await childDialog.getByRole("button", { name: "Сохранить" }).click();
  await expect(childDialog).toBeHidden();
  await expect(childCard(page, SIBLING.name)).toBeVisible();

  await createDailySeries(page, LEAD.childName, "15:00");
  await createDailySeries(page, SIBLING.name, "17:00");

  const parent = await openPage();
  await login(parent, PARENT.email, PARENT.password);
  await parent.goto("/cabinet/calendar");
  await expect(parent.getByRole("heading", { name: "Календарь" })).toBeVisible();
  // Детей двое — заголовок события = имя ребёнка; месячная сетка включает завтрашний день.
  const events = parent.locator(".fc-event");
  await expect(events.filter({ hasText: LEAD.childName }).first()).toBeVisible();
  await expect(events.filter({ hasText: SIBLING.name }).first()).toBeVisible();
  // Месячный вид в русской локали пишет время коротко: «15» перед именем.
  await expect(events.filter({ hasText: LEAD.childName }).first()).toHaveText(/^15(:00)?\s*Петя$/);
  await expect(events.filter({ hasText: SIBLING.name }).first()).toHaveText(/^17(:00)?\s*Маша$/);
});
