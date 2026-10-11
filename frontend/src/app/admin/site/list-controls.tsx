"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

/**
 * Кнопки «Выше», «Ниже», «Удалить» одного элемента списка.
 *
 * `noun` — название элемента в винительном падеже («услугу»), `index` — позиция с нуля.
 * Номер в `aria-label` нужен, чтобы кнопки разных элементов различались для скринридера.
 */
export function ListControls({
  index,
  count,
  noun,
  onMoveUp,
  onMoveDown,
  onRemove,
}: {
  index: number;
  count: number;
  noun: string;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}) {
  const number = index + 1;
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label={`Переместить ${noun} ${number} выше`}
        disabled={index === 0}
        onClick={onMoveUp}
      >
        Выше
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label={`Переместить ${noun} ${number} ниже`}
        disabled={index === count - 1}
        onClick={onMoveDown}
      >
        Ниже
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        aria-label={`Удалить ${noun} ${number}`}
        onClick={onRemove}
      >
        Удалить
      </Button>
    </div>
  );
}

/** Рамка элемента списка: заголовок «Услуга 2», поля и кнопки управления. */
export function ListItem({
  title,
  controls,
  children,
}: {
  title: string;
  controls: ReactNode;
  children: ReactNode;
}) {
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border p-4">
      <legend className="px-1 text-sm font-medium">{title}</legend>
      {children}
      {controls}
    </fieldset>
  );
}
