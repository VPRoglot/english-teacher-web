import { CHILD, LEAD, PARENT, SIBLING } from "../env";
import { expect, login, test } from "../fixtures";

test("ребёнок входит по логину и видит только своё расписание", async ({ openPage }) => {
  const parent = await openPage();
  await login(parent, PARENT.email, PARENT.password);

  // Занятие второго ребёнка: потом ребёнок не должен его открыть.
  await parent.getByLabel("Ребёнок").selectOption({ label: SIBLING.name });
  const parentNearest = parent
    .locator('[data-slot="card"]')
    .filter({ hasText: "Ближайшее занятие" });
  await expect(parentNearest).toContainText(SIBLING.name);
  const siblingHref = await parentNearest.getByRole("link").first().getAttribute("href");
  const siblingLessonPath = new URL(siblingHref ?? "", "https://tutor.test").pathname;
  expect(siblingLessonPath).toMatch(/^\/cabinet\/lessons\/[0-9a-f-]+$/);

  // Родитель выдаёт логин первому ребёнку.
  await parent.goto("/cabinet/children");
  const card = parent
    .locator('[data-slot="card"]')
    .filter({ has: parent.locator('[data-slot="card-title"]').getByText(LEAD.childName, { exact: true }) });
  await expect(card.getByText("Логин не выдан")).toBeVisible();
  await card.getByLabel("Логин", { exact: true }).fill(CHILD.username);
  await card.getByLabel("Пароль", { exact: true }).fill(CHILD.password);
  await card.getByRole("button", { name: "Сохранить" }).click();
  await expect(card.getByText(`Логин: ${CHILD.username}`)).toBeVisible();

  const child = await openPage();
  await login(child, CHILD.username, CHILD.password);
  await expect(child).toHaveURL(/\/cabinet$/);
  const nearest = child.locator('[data-slot="card"]').filter({ hasText: "Ближайшее занятие" });
  await expect(nearest).toContainText(LEAD.childName);
  await expect(child.getByText(SIBLING.name)).toHaveCount(0);

  // Календарь: занятия есть, имени второго ребёнка нигде нет.
  await child.goto("/cabinet/calendar");
  await expect(child.locator(".fc-event").first()).toBeVisible();
  await expect(child.getByText(SIBLING.name)).toHaveCount(0);

  // API отдаёт только занятия этого ребёнка.
  const from = new Date(Date.now() - 86_400_000).toISOString();
  const to = new Date(Date.now() + 14 * 86_400_000).toISOString();
  const response = await child.request.get("/api/me/lessons", { params: { from, to } });
  expect(response.status()).toBe(200);
  const lessons = (await response.json()) as { child_name: string }[];
  expect(lessons.length).toBeGreaterThan(0);
  expect(new Set(lessons.map((lesson) => lesson.child_name))).toEqual(new Set([LEAD.childName]));

  // Занятие второго ребёнка ребёнку недоступно.
  await child.goto(siblingLessonPath);
  await expect(child.getByText("Занятие не найдено")).toBeVisible();
});
