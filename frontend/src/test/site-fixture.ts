import type { PublicSite } from "@/api/generated/model";

/** Полный пример публичного контента лендинга для тестов. */
export const siteFixture: PublicSite = {
  hero: {
    name: "Анна Иванова",
    title: "Английский для детей и взрослых",
    subtitle: "Индивидуальные занятия онлайн: понятно, спокойно и с результатом",
    cta_text: "Записаться на пробное занятие",
    photo: { url: "/media/site/hero.jpg", width: 800, height: 1000 },
  },
  about: {
    text: "Меня зовут Анна. Я преподаю английский **более 10 лет**.",
    credentials: ["Диплом лингвиста", "Сертификат CELTA"],
    photo: null,
  },
  services: {
    items: [
      {
        title: "Пробное занятие",
        description: "Знакомимся, определяем уровень и ставим цели.",
        duration_min: 30,
        format: "Онлайн",
        price_rub: 0,
      },
      {
        title: "Индивидуальное занятие",
        description: "Занятие по вашей программе.",
        duration_min: 60,
        format: "Онлайн",
        price_rub: 1500,
      },
    ],
  },
  reviews: {
    items: [
      {
        author: "Мария, мама Саши",
        text: "Сын стал с удовольствием заниматься.",
        child_age: 9,
        photo: null,
      },
      {
        author: "Дмитрий",
        text: "За полгода заговорил свободнее.",
        child_age: null,
        photo: null,
      },
    ],
  },
  faq: {
    items: [
      { question: "Как проходят занятия?", answer: "Онлайн в Zoom или Telegram." },
      { question: "Можно ли перенести занятие?", answer: "Да, за 24 часа до начала." },
    ],
  },
  contacts: {
    telegram: "anna_english",
    whatsapp: "+79991234567",
    phone: "+79991234567",
    email: "anna@example.com",
    working_hours_text: "Пн–Пт 10:00–20:00",
  },
};
