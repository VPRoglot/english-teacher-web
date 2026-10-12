import { Alert, AlertDescription } from "@/components/ui/alert";

export const TUTOR_SETTINGS_ERROR_TEXT =
  "Не удалось загрузить настройки репетитора. Обновите страницу.";

/** Вместо формы со временем, когда не загрузился пояс репетитора: отправлять её нельзя. */
export function TutorSettingsError() {
  return (
    <Alert variant="destructive">
      <AlertDescription>{TUTOR_SETTINGS_ERROR_TEXT}</AlertDescription>
    </Alert>
  );
}
