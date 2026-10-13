import { expect, test } from "../fixtures";

const NEW_TITLE = "Английский, который нравится детям (e2e)";

test("новый заголовок hero появляется на главной за 15 секунд", async ({ page, openPage }) => {
  const visitor = await openPage();
  // Главная уже в кеше Next со старым заголовком: сброс кеша делает worker (POST /api/revalidate).
  await visitor.goto("/");
  await expect(visitor.getByRole("heading", { level: 1 })).not.toHaveText(NEW_TITLE);

  await page.goto("/admin/site");
  const hero = page.locator('[data-slot="card"]').filter({ hasText: "Главный экран" });
  await hero.getByLabel("Заголовок", { exact: true }).fill(NEW_TITLE);
  await hero.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText("Сохранено. Сайт обновится в течение минуты")).toBeVisible();

  await expect
    .poll(
      async () => {
        await visitor.goto("/");
        return visitor.getByRole("heading", { level: 1 }).textContent();
      },
      { timeout: 15_000, intervals: [500, 1_000] },
    )
    .toBe(NEW_TITLE);
});
