"use client";

import { useEffect, useState } from "react";

const MINUTE_MS = 60_000;

const floorToMinute = (ms: number) => Math.floor(ms / MINUTE_MS) * MINUTE_MS;

/**
 * «Сейчас» с точностью до минуты (мс с эпохи). Обновляется на границе каждой минуты, поэтому
 * внутри минуты значение стабильно (его можно класть в ключ запроса), а страница, оставленная
 * открытой, не «замерзает» на моменте открытия.
 */
export function useMinuteNow(): number {
  const [now, setNow] = useState(() => floorToMinute(Date.now()));

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(() => {
        setNow(floorToMinute(Date.now()));
        schedule();
      }, MINUTE_MS - (Date.now() % MINUTE_MS));
    };
    schedule();
    return () => clearTimeout(timer);
  }, []);

  return now;
}
