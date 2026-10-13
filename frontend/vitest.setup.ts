import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Без `globals: true` Testing Library не размонтирует компоненты сам.
afterEach(cleanup);

// findBy*/waitFor по умолчанию ждут 1 с. При полном прогоне (десятки jsdom-окружений параллельно,
// раннер CI слабее рабочей машины) загрузка мок-данных иногда занимает больше — тесты падали
// нестабильно на ожидании, а не на проверке. Тайминги эти тесты не проверяют.
configure({ asyncUtilTimeout: 5000 });
