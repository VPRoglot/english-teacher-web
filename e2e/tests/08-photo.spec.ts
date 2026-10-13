import { expect, test } from "../fixtures";

// Минимальный валидный PNG 1×1: backend проверяет картинку по содержимому (Pillow).
const PNG_1X1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

test("фото hero загружается в MinIO и отдаётся на главной через /media", async ({
  page,
  openPage,
}) => {
  await page.goto("/admin/site");
  const hero = page.locator('[data-slot="card"]').filter({ hasText: "Главный экран" });

  const uploaded = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/admin/media") && response.request().method() === "POST",
  );
  await hero
    .getByLabel("Фото", { exact: true })
    .setInputFiles({ name: "hero.png", mimeType: "image/png", buffer: PNG_1X1 });
  const response = await uploaded;
  expect(response.status()).toBe(201);
  const { url } = (await response.json()) as { url: string };
  expect(url).toMatch(/^\/media\/.+/);

  await hero.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByText("Сохранено. Сайт обновится в течение минуты")).toBeVisible();

  // Главная обновляется после revalidate (worker): ждём картинку hero с загруженным адресом.
  const visitor = await openPage();
  await expect
    .poll(
      async () => {
        await visitor.goto("/");
        return visitor.locator(`img[src="${url}"]`).count();
      },
      { timeout: 15_000, intervals: [500, 1_000] },
    )
    .toBe(1);

  // Браузер посетителя действительно получил картинку: цепочка nginx → MinIO (анонимное чтение).
  const image = visitor.locator(`img[src="${url}"]`);
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);

  const direct = await visitor.request.get(url);
  expect(direct.status()).toBe(200);
  expect(direct.headers()["content-type"]).toMatch(/^image\//);
});
