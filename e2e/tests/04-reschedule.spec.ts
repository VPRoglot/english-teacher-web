import { LEAD, PARENT } from "../env";
import { expect, login, test } from "../fixtures";

test("родитель просит перенос, репетитор одобряет с новым временем", async ({ page, openPage }) => {
  const parent = await openPage();
  await login(parent, PARENT.email, PARENT.password);

  // Ближайшее занятие — завтра в 15:00 у первого ребёнка (сценарий 3).
  const nearest = parent.locator('[data-slot="card"]').filter({ hasText: "Ближайшее занятие" });
  await expect(nearest).toContainText(LEAD.childName);
  await expect(nearest).toContainText("15:00–16:00");
  await nearest.getByRole("link").first().click();
  await expect(parent).toHaveURL(/\/cabinet\/lessons\/[0-9a-f-]+/);
  const lessonUrl = parent.url();
  await expect(parent.getByRole("heading", { level: 1, name: LEAD.childName })).toBeVisible();

  await parent.getByRole("button", { name: "Запросить перенос" }).click();
  const requestDialog = parent.getByRole("dialog", { name: "Запросить перенос" });
  await requestDialog.getByLabel("Когда удобно?").fill("В тот же день вечером, после 19:00");
  await requestDialog.getByRole("button", { name: "Отправить" }).click();
  await expect(requestDialog).toBeHidden();
  await expect(parent.getByText("Ждёт ответа репетитора")).toBeVisible();

  await page.goto("/admin/requests");
  const card = page
    .getByRole("listitem")
    .filter({ hasText: LEAD.childName })
    .filter({ hasText: "В тот же день вечером" });
  await expect(card).toHaveCount(1);
  await card.getByRole("button", { name: "Одобрить" }).click();
  const approveDialog = page.getByRole("dialog", { name: "Одобрить перенос" });
  await expect(approveDialog.getByLabel("Время", { exact: true })).toHaveValue("15:00");
  await approveDialog.getByLabel("Время", { exact: true }).fill("19:30");
  await approveDialog.getByRole("button", { name: "Одобрить" }).click();
  await expect(approveDialog).toBeHidden();
  await expect(page.getByText("Запросов нет")).toBeVisible();

  await parent.goto(lessonUrl);
  await expect(parent.getByText("19:30–20:30")).toBeVisible();
  await expect(parent.getByText("15:00–16:00")).toHaveCount(0);
  await expect(parent.getByText("Одобрен", { exact: true })).toBeVisible();
});
