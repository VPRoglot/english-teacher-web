import { LEAD } from "../env";
import { expect, test } from "../fixtures";

test("посетитель оставляет заявку, репетитор видит её в списке", async ({ page, openPage }) => {
  const visitor = await openPage();
  await visitor.goto("/#trial");

  const form = visitor.locator("#trial");
  await form.getByLabel("Ваше имя").fill(LEAD.parentName);
  await form.getByLabel("Имя ребёнка").fill(LEAD.childName);
  await form.getByLabel("Возраст ребёнка").fill(LEAD.childAge);
  await form.getByRole("textbox", { name: "Телефон" }).fill(LEAD.phone);
  await form.getByLabel("Ник в Telegram").fill(LEAD.telegram);
  await form.getByLabel("Цель занятий").fill("Подтянуть школьную программу");
  await form.getByRole("checkbox", { name: /Согласен\(на\) на обработку/ }).click();
  await form.getByRole("button", { name: "Записаться на пробное" }).click();
  await expect(form.getByRole("status")).toContainText("Спасибо! Заявка отправлена");

  await page.goto("/admin/leads");
  await expect(page.getByRole("heading", { name: "Заявки" })).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: LEAD.parentName });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText(`${LEAD.childName}, ${LEAD.childAge}`);
  await expect(row).toContainText("Новая");
});
