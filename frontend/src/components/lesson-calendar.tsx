"use client";

import type { EventInput } from "@fullcalendar/core";
import ruLocale from "@fullcalendar/core/locales/ru";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import listPlugin from "@fullcalendar/list";
import luxon3Plugin from "@fullcalendar/luxon3";
import FullCalendar from "@fullcalendar/react";
import timeGridPlugin from "@fullcalendar/timegrid";
import { useEffect, useRef, useSyncExternalStore } from "react";

import { timeZoneNote } from "@/lib/datetime";

const PLUGINS = [dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin, luxon3Plugin];
const MOBILE_QUERY = "(max-width: 767px)";

function subscribeMobile(onChange: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const media = window.matchMedia(MOBILE_QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function isMobileNow(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(MOBILE_QUERY).matches;
}

/** `< 768px`: на узком экране календарь показывается списком. */
function useIsMobile(): boolean {
  return useSyncExternalStore(subscribeMobile, isMobileNow, () => false);
}

export type LessonCalendarProps = {
  events: EventInput[];
  /** Пояс репетитора: события и сетка календаря показываются в нём, а не в поясе браузера. */
  timeZone: string;
  /** `desktop` — виды для переключателя (первый открывается), `mobile` — единственный вид на узком экране. */
  views: { desktop: string[]; mobile: string };
  /** Вызывается при каждой смене видимого диапазона: `[start, end)`. */
  onRangeChange: (start: Date, end: Date) => void;
  onEventClick: (id: string) => void;
  onSlotClick?: (date: Date) => void;
  /** Текст списочных видов для диапазона без событий (вместо стандартного «Нет событий…»). */
  emptyText?: string;
};

/** Обёртка FullCalendar: русская локаль, пояс репетитора, вид по ширине экрана. Без перетаскивания. */
export function LessonCalendar({
  events,
  timeZone,
  views,
  onRangeChange,
  onEventClick,
  onSlotClick,
  emptyText,
}: LessonCalendarProps) {
  const calendar = useRef<FullCalendar>(null);
  const mobile = useIsMobile();
  const view = mobile ? views.mobile : views.desktop[0];
  const note = timeZoneNote(timeZone);

  // Вид меняем у живого календаря: пересоздание сбросило бы выбранную неделю.
  useEffect(() => {
    const api = calendar.current?.getApi();
    if (api && api.view.type !== view) api.changeView(view);
  }, [view]);

  return (
    <div className="flex flex-col gap-2">
      <FullCalendar
        ref={calendar}
        plugins={PLUGINS}
        locale={ruLocale}
        timeZone={timeZone}
        initialView={view}
        headerToolbar={{
          left: "prev,next today",
          center: "title",
          right: mobile ? "" : views.desktop.join(","),
        }}
        height="auto"
        nowIndicator
        editable={false}
        allDaySlot={false}
        scrollTime="08:00:00"
        events={events}
        noEventsContent={emptyText}
        datesSet={({ start, end }) => onRangeChange(start, end)}
        eventClick={({ event, jsEvent }) => {
          jsEvent.preventDefault();
          onEventClick(event.id);
        }}
        dateClick={onSlotClick ? ({ date }) => onSlotClick(date) : undefined}
      />
      {note && <p className="text-sm text-muted-foreground">{note}</p>}
    </div>
  );
}
