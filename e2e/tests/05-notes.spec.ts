import { LEAD, PARENT } from "../env";
import { expect, login, test } from "../fixtures";

const SHARED = "Повторить Present Simple: упражнения 3 и 4.";
const PRIVATE = "Приватно: обсудить с мамой темп занятий.";

test("общая заметка видна семье, приватная — нет", async ({ page, openPage }) => {
  const parent = await openPage();
  await login(parent, PARENT.email, PARENT.password);
  await parent.getByLabel("Ребёнок").selectOption({ label: LEAD.childName });
  await expect(parent).toHaveURL(/[?&]child=/);
  const nearest = parent.locator('[data-slot="card"]').filter({ hasText: "Ближайшее занятие" });
  await expect(nearest).toContainText(LEAD.childName);
  await nearest.getByRole("link").first().click();
  await expect(parent).toHaveURL(/\/cabinet\/lessons\/[0-9a-f-]+/);
  const lessonId = new URL(parent.url()).pathname.split("/").pop() ?? "";
  await expect(parent.getByText("Заметки пока нет")).toBeVisible();

  await page.goto(`/admin/lessons/${lessonId}`);
  await expect(page.getByRole("heading", { level: 1, name: LEAD.childName })).toBeVisible();
  await page.getByRole("textbox", { name: "Общая — видна семье" }).fill(SHARED);
  await page.getByRole("textbox", { name: "Приватная — только для вас" }).fill(PRIVATE);
  await page.getByRole("button", { name: "Сохранить заметку" }).click();
  await expect(page.getByText("Заметка сохранена")).toBeVisible();
  await expect(page.getByRole("button", { name: "Сохранить заметку" })).toBeDisabled();

  await parent.reload();
  const noteSection = parent.locator("section").filter({
    has: parent.getByRole("heading", { name: "Заметка репетитора" }),
  });
  await expect(noteSection).toContainText(SHARED);
  await expect(parent.getByText(PRIVATE)).toHaveCount(0);
  expect(await parent.content()).not.toContain(PRIVATE);

  const response = await parent.request.get(`/api/me/lessons/${lessonId}`);
  expect(response.status()).toBe(200);
  const body = await response.text();
  expect(body).toContain(SHARED);
  expect(body).not.toContain("private_text");
  expect(body).not.toContain(PRIVATE);
});
