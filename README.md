# 🏃 Беговые события России 2026

Сайт-календарь беговых событий по всей России с автоматическим обновлением.

🔗 **Сайт:** `https://ВАШ-НИК.github.io/ИМЯ-РЕПОЗИТОРИЯ/`

---

## Структура проекта

```
├── index.html                        # Сайт (фильтры по городу, месяцу, типу)
├── events.json                       # База событий (обновляется автоматически)
├── scraper.py                        # Скрипт парсинга официальных сайтов
├── .github/
│   └── workflows/
│       └── update.yml                # GitHub Actions: запуск 2 раза в сутки
└── README.md
```

---

## Шаг 1 — Загрузить файлы на GitHub

### Создать репозиторий
1. Зайдите на [github.com](https://github.com) → кнопка **+** → **New repository**
2. Имя: например `running-russia`
3. Видимость: **Public** (обязательно для GitHub Pages)
4. **Не** ставить галочку «Add README» — файлы загрузим вручную
5. Нажать **Create repository**

### Загрузить файлы
Нажать **Add file → Upload files** и загрузить:
- `index.html`
- `events.json`
- `scraper.py`

### Создать workflow вручную
Нажать **Add file → Create new file**:
- В поле имени написать: `.github/workflows/update.yml`
- Вставить содержимое файла `update.yml`
- Нажать **Commit changes**

---

## Шаг 2 — Включить GitHub Pages

1. Открыть **Settings** (вкладка в репозитории)
2. В левом меню → **Pages**
3. Source: **Deploy from a branch**
4. Branch: **main** → папка **/ (root)**
5. Нажать **Save**
6. Подождать 2–3 минуты — ссылка появится вверху раздела Pages

---

## Шаг 3 — Разрешить Actions записывать файлы

1. **Settings** → **Actions** → **General**
2. Прокрутить до «Workflow permissions»
3. Выбрать **Read and write permissions**
4. Нажать **Save**

---

## Шаг 4 — Добавить VK токен (опционально)

Без токена скрипт работает, но не парсит ВКонтакте.

1. Зайти на [vk.com/dev](https://vk.com/dev) → **Мои приложения** → **Создать**
2. Тип приложения: **Standalone**
3. После создания: **Настройки** → скопировать **Сервисный ключ доступа**
4. В GitHub: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
   - Name: `VK_TOKEN`
   - Value: ваш токен
5. Нажать **Add secret**

---

## Шаг 5 — Проверить что всё работает

1. Открыть вкладку **Actions** в репозитории
2. Нажать на **Update Events** → **Run workflow** → **Run workflow**
3. Дождаться зелёной галочки (1–2 минуты)
4. Открыть сайт — данные обновлены

После этого скрипт будет запускаться автоматически каждый день в **09:00** и **18:00 по МСК**.

---

## Как добавить событие вручную

Открыть `events.json` в репозитории → нажать карандаш (Edit) → добавить объект в массив `events`:

```json
{
  "id": 99,
  "date": "2026-09-20",
  "name": "Название забега",
  "city": "Город",
  "region": "Регион",
  "distances": "5 км, 10 км, 21,1 км",
  "type": "road",
  "url": "https://сайт-события.ru"
}
```

Поле `type`: `road` — шоссе, `trail` — трейл, `night` — ночной.

---

## Источники парсинга

| Сайт | Что парсится |
|---|---|
| krasmarafon.ru | Красноярск |
| pushkin-run.ru | Санкт-Петербург |
| heroleague.ru | Санкт-Петербург |
| ea-m.org | Екатеринбург |
| runsim.ru | Омск |
| tomskmarathon.ru | Томск |
| kazan.run | Казань |
| sib-events.ru | Алтай, Сибирь |
| wnmarathon.runc.run | СПб, Белые ночи |
| moscowhalf.runc.run | Москва |
| springrun.ru | Новосибирск |
| sportsauce.ru | Новосибирск |
| timerman.org | Казань, Татарстан |
| events.topliga.ru | Юг России |
| alpmarathon.ru | Иркутск |
| myrace.info | Трейлы, вся Россия |
| rtra.ru | Трейлы, вся Россия |
| skyrunning.ru | Горные старты |
| vk.com (API) | runningrussia, krasmarafon, begaem |
