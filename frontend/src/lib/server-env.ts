type ServerEnvName = "API_INTERNAL_URL" | "SITE_URL" | "REVALIDATE_SECRET";

/**
 * Читает переменную окружения во время вызова (не при сборке) и убирает завершающий `/`.
 * Пустая переменная считается незаданной.
 */
export function serverEnv(name: ServerEnvName): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Не задана переменная окружения ${name}`);
  }
  return value.replace(/\/+$/, "");
}
