import { LEAD, PARENT } from "../env";
import { expect, test } from "../fixtures";

// «Скопировать» в диалоге приглашения пишет ссылку в буфер обмена.
test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test("пробное, конвертация и вход родителя по приглашению", async ({ page, openPage }) => {
  await page.goto("/admin/leads");
  await page.getByRole("link", { name: LEAD.parentName }).click();
  await expect(page.getByRole("heading", { level: 1, name: LEAD.parentName })).toBeVisible();

  // Пробное: время по умолчанию — следующий час в поясе репетитора.
  await page.getByRole("button", { name: "Назначить пробное" }).click();
  const trialDialog = page.getByRole("dialog", { name: "Назначить пробное" });
  await trialDialog.getByRole("button", { name: "Назначить", exact: true }).click();
  await expect(trialDialog).toBeHidden();
  await expect(page.getByText("Пробное назначено", { exact: true })).toBeVisible();

  // Конвертация: семья, ребёнок и ссылка-приглашение.
  await page.getByRole("button", { name: "Конвертировать в ученика" }).click();
  const convertDialog = page.getByRole("dialog", { name: "Конвертация в ученика" });
  await expect(convertDialog.getByLabel("Имя ребёнка")).toHaveValue(LEAD.childName);
  await convertDialog.getByRole("button", { name: "Конвертировать", exact: true }).click();

  const createdDialog = page.getByRole("dialog", { name: "Семья создана" });
  const linkField = createdDialog.getByRole("textbox", { name: "Ссылка-приглашение" });
  await expect(linkField).toHaveValue(/^https:\/\/tutor\.test\/invite\/[^/]+$/);
  const invitationUrl = await linkField.inputValue();

  await createdDialog.getByRole("button", { name: "Скопировать" }).click();
  await expect(createdDialog.getByText("Скопировано")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(invitationUrl);
  await createdDialog.getByRole("button", { name: "Закрыть" }).click();
  await expect(page.getByText("Стала учеником", { exact: true })).toBeVisible();

  // Родитель в своём браузере принимает приглашение.
  const parent = await openPage();
  await parent.goto(invitationUrl);
  await expect(parent.getByText(`Приглашение в семью «Семья ${LEAD.childName}»`)).toBeVisible();
  await expect(parent.getByLabel("ФИО")).toHaveValue(LEAD.parentName);
  await parent.getByLabel("Email").fill(PARENT.email);
  await parent.getByLabel("Пароль", { exact: true }).fill(PARENT.password);
  await parent.getByLabel("Повторите пароль").fill(PARENT.password);
  await parent.getByRole("checkbox", { name: /Согласен на обработку/ }).click();
  await parent.getByRole("button", { name: "Принять приглашение" }).click();

  await expect(parent).toHaveURL(/\/cabinet$/);
  await expect(
    parent.getByRole("heading", { name: `Здравствуйте, ${LEAD.parentName}!` }),
  ).toBeVisible();
  await expect(parent.getByRole("listitem").filter({ hasText: LEAD.childName })).toBeVisible();
});
