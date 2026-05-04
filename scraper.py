#!/usr/bin/env python3
"""
Скрипт парсинга беговых событий России.
Запускается GitHub Actions 2 раза в сутки.

Источники:
  Официальные сайты:
    krasmarafon.ru, pushkin-run.ru, heroleague.ru, ea-m.org,
    runsim.ru, tomskmarathon.ru, kazan.run, sib-events.ru,
    wnmarathon.runc.run, moscowhalf.runc.run, springrun.ru,
    sportsauce.ru, timerman.org, topliga.ru/events, alpmarathon.ru,
    myrace.info, rtra.ru, skyrunning.ru

  ВКонтакте (через VK API, токен из секрета VK_TOKEN):
    vk.com/runningrussia, vk.com/krasmarafon, vk.com/begaem
"""

import json
import os
import re
import sys
import time
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, date

# ─── HTTP ────────────────────────────────────────────────────────────────────

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/122.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.5',
}

def fetch(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            charset = 'utf-8'
            ct = r.headers.get_content_charset()
            if ct:
                charset = ct
            return r.read().decode(charset, errors='ignore')
    except Exception as e:
        print(f"  [ERR] {url}: {e}")
        return ""

def fetch_json(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode('utf-8', errors='ignore'))
    except Exception as e:
        print(f"  [ERR JSON] {url}: {e}")
        return None

# ─── HELPERS ─────────────────────────────────────────────────────────────────

RU_MONTHS = {
    'января':1,'февраля':2,'марта':3,'апреля':4,'мая':5,'июня':6,
    'июля':7,'августа':8,'сентября':9,'октября':10,'ноября':11,'декабря':12,
    'январе':1,'феврале':2,'марте':3,'апреле':4,'июне':6,
    'июле':7,'августе':8,'сентябре':9,'октябре':10,'ноябре':11,'декабре':12,
    'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
    'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12,
}

def parse_date(s):
    """Парсит дату из строки → YYYY-MM-DD или None."""
    if not s:
        return None
    s = s.strip().lower()
    # DD месяц YYYY
    m = re.search(r'(\d{1,2})\s+([а-яёa-z]+)\s+(\d{4})', s)
    if m:
        day, mon, year = int(m.group(1)), m.group(2), int(m.group(3))
        if mon in RU_MONTHS and 2026 <= year <= 2027:
            return f"{year}-{RU_MONTHS[mon]:02d}-{day:02d}"
    # YYYY-MM-DD
    m = re.search(r'(202[6-7])-(\d{2})-(\d{2})', s)
    if m:
        return m.group(0)
    # DD.MM.YYYY
    m = re.search(r'(\d{1,2})\.(\d{2})\.(202[6-7])', s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
    return None

def strip_tags(html):
    """Убирает HTML-теги и их содержимое для script/style, остальное — пробел."""
    # Убираем script и style вместе с содержимым
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S | re.I)
    # Убираем все остальные теги
    html = re.sub(r'<[^>]+>', ' ', html)
    return html

# Паттерны HTML-мусора, которые могут просочиться в название
_HTML_GARBAGE = re.compile(
    r'''
    role\s*=           |  # role="presentation"
    class\s*=          |  # class="t959__card"
    width\s*=          |  # width="14"
    height\s*=         |  # height="14"
    style\s*=          |  # style="color:..."
    aria-[a-z]         |  # aria-label
    data-[a-z]         |  # data-id
    href\s*=           |  # href="..."
    src\s*=            |  # src="..."
    t\d{3}__           |  # классы tilda: t959__, t123__
    _blank             |  # target="_blank"
    noopener           |  # rel="noopener"
    presentation       |  # role="presentation"
    viewBox            |  # SVG атрибут
    xmlns              |  # SVG атрибут
    stroke-            |  # SVG stroke-width
    fill-              |  # SVG fill-rule
    &[a-z]{2,6};          # HTML-энтити (&nbsp; &mdash; итд)
    ''',
    re.X | re.I
)

# Минимальная длина валидного названия события
_MIN_NAME_LEN = 5
# Признаки того что строка — не название, а HTML/CSS мусор
_JUNK_MARKERS = re.compile(
    r'[\{\}\[\]\\|<>]'             # технические символы
    r'|(?:px|em|rem|vw|vh)\b'      # CSS единицы
    r'|#[0-9a-f]{3,6}\b'           # hex-цвета
    r'|https?://'                   # ссылки
    r'|__[a-z]'                     # BEM-классы: card__title, t959__arrow
    r'|\b(?:function|return|var|const|let|if|else|div|span|svg|ul|li|img'
    r'|arrow|card|block|wrapper|container|inner|outer|section'
    r'|btn|button|icon|logo|nav|menu|header|footer|sidebar|widget'
    r'|col|row|grid|flex|box|tile|thumb|banner|modal|popup|overlay'
    r'|active|disabled|hidden|visible|primary|secondary)\b',
    re.I
)

def clean(s):
    """Очищает строку от HTML, мусора и возвращает чистый текст."""
    s = strip_tags(str(s))
    # Убираем HTML-мусор атрибутов
    s = _HTML_GARBAGE.sub(' ', s)
    # Убираем кавычки с содержимым если это значение атрибута (="...")
    s = re.sub(r'=\s*["\'][^"\']*["\']', ' ', s)
    # Убираем разрозненные кавычки
    s = re.sub(r'["\']', ' ', s)
    # Схлопываем пробелы
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def is_valid_name(s):
    """Проверяет, что строка похожа на название события, а не на HTML-мусор."""
    if not s or len(s) < _MIN_NAME_LEN:
        return False
    if _JUNK_MARKERS.search(s):
        return False
    # Должен содержать хотя бы одну букву
    if not re.search(r'[а-яёА-ЯЁa-zA-Z]', s):
        return False
    # Не должен начинаться с цифры или спецсимвола
    if re.match(r'^[\d\W]', s):
        return False
    return True

def make_event(date, name, city, region, distances, etype, url):
    # Финальная очистка названия
    name = clean(name)
    if not is_valid_name(name):
        return None  # сигнал: событие невалидно, не добавлять
    # Обрезаем слишком длинные названия
    if len(name) > 100:
        name = name[:97] + '…'
    return {
        "date": date, "name": name, "city": city, "region": region,
        "distances": distances, "type": etype, "url": url,
    }

TODAY = date.today().isoformat()

def is_future(d):
    return d and d >= TODAY

# ─── SITE SCRAPERS ───────────────────────────────────────────────────────────

def scrape_generic(url, city, region, etype, default_name):
    """Универсальный парсер: ищет даты 2026/2027 рядом с названиями событий."""
    html = fetch(url)
    if not html:
        return []
    events = []
    # Паттерн: ищем блок <a ...>Название</a> рядом с датой
    # или просто дату + ближайший текст
    chunks = re.split(r'(?=\d{1,2}\s+[а-яА-Я]+\s+202[67])', html)
    seen = set()
    for chunk in chunks[:30]:
        d = parse_date(chunk[:60])
        if not d or not is_future(d):
            continue
        # Ищем название в тегах <a>, <h2>, <h3>, <strong>, <b> в пределах 400 символов
        name_m = re.search(
            r'<(?:a|h[123]|strong|b|span)[^>]*?>([^<]{6,80})</(?:a|h[123]|strong|b|span)>',
            chunk[:400]
        )
        if name_m:
            name = clean(name_m.group(1))
        else:
            # fallback — берём первый нормальный текстовый фрагмент
            text = clean(chunk[:300])
            parts = [p.strip() for p in text.split() if len(p) > 4]
            name = ' '.join(parts[3:8]) if len(parts) > 5 else default_name
        if not name or len(name) < 5:
            name = default_name
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        events.append(make_event(d, name, city, region, "", etype, url))
    return events


def scrape_krasmarafon():
    """krasmarafon.ru — Красноярский марафон и серия стартов"""
    print("  krasmarafon.ru")
    events = []
    pages = [
        ("https://krasmarafon.ru/", "road"),
        ("https://krasmarafon.ru/nightrun", "night"),
        ("https://krasmarafon.ru/vesna", "road"),
        ("https://krasmarafon.ru/colorrun", "road"),
        ("https://krasmarafon.ru/girlseven", "road"),
    ]
    for url, etype in pages:
        html = fetch(url)
        if not html:
            continue
        # Ищем названия событий и даты
        name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', html)
        name = clean(name_m.group(1)) if name_m else "Старт Красноярск"
        date_blocks = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
        for db in date_blocks[:3]:
            d = parse_date(db)
            if d and is_future(d):
                events.append(make_event(d, name, "Красноярск", "Красноярский край", "", etype, url))
                break
    return events


def scrape_pushkin_run():
    """pushkin-run.ru — Серия стартов Санкт-Петербург"""
    print("  pushkin-run.ru")
    html = fetch("https://pushkin-run.ru/")
    if not html:
        return []
    events = []
    # Сайт обычно содержит таблицу с датами
    rows = re.findall(r'(\d{1,2}[.\s]+(?:\d{2}|\w+)[.\s]+202\d)[^<]{0,200}', html)
    seen = set()
    for row in rows[:15]:
        d = parse_date(row)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        events.append(make_event(d, "Старт серии Pushkin Run", "Санкт-Петербург",
                                  "Санкт-Петербург", "", "road", "https://pushkin-run.ru/#calendar"))
    return events


def scrape_heroleague():
    """heroleague.ru — Дорога Жизни и другие"""
    print("  heroleague.ru")
    events = []
    for slug, name, etype in [
        ("doroga", "Марафон «Дорога Жизни»", "road"),
        ("", "Старт HeroLeague", "road"),
    ]:
        url = f"https://heroleague.ru/{slug}"
        html = fetch(url)
        if not html:
            continue
        dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
        for db in dates[:3]:
            d = parse_date(db)
            if d and is_future(d):
                events.append(make_event(d, name, "Санкт-Петербург",
                                          "Санкт-Петербург", "", etype, url))
                break
    return events


def scrape_ea_m():
    """
    ea-m.org — серия Европа-Азия, Екатеринбург.
    Используем жёстко заданный список известных событий +
    проверяем страницу на новые анонсы.
    """
    print("  ea-m.org")
    html = fetch("https://ea-m.org/")
    if not html:
        return []

    events = []
    seen = set()

    # Ищем ссылки вида href="https://ea-m.org/SLUG" рядом с датой
    # Формат на сайте: <a href="https://ea-m.org/slug">Название\nДата</a>
    blocks = re.findall(
        r'href="(https://ea-m\.org/[a-z0-9\-]+)"[^>]*>(.*?)</a>',
        html, re.S
    )

    for url, content in blocks:
        # Пропускаем служебные страницы
        if url in ('https://ea-m.org/', 'https://ea-m.org/therunningroom',
                   'https://ea-m.org/privacy'):
            continue

        # Ищем дату в содержимом блока
        d = parse_date(content)
        if not d or not is_future(d):
            continue

        # Чистим название — берём первую строку до даты
        lines = [l.strip() for l in re.split(r'[\n\r]+', strip_tags(content)) if l.strip()]
        # Убираем строки которые являются датой или служебным текстом
        name_parts = []
        for line in lines:
            line_clean = clean(line)
            if not line_clean:
                continue
            # Пропускаем если строка содержит дату или слишком короткая
            if re.search(r'\d{1,2}\s+[а-яА-Я]+\s+20\d{2}|\d{4}', line_clean):
                continue
            if not is_valid_name(line_clean):
                continue
            name_parts.append(line_clean)

        name = ' '.join(name_parts[:2]).strip() if name_parts else None
        if not name or not is_valid_name(name):
            continue

        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)

        # Определяем тип
        etype = 'road'
        if re.search(r'трейл|trail|шигир', name, re.I):
            etype = 'trail'
        elif re.search(r'ночн|laser|night', name, re.I):
            etype = 'night'

        ev = make_event(d, name, 'Екатеринбург', 'Свердловская область', '', etype, url)
        if ev:
            events.append(ev)

    return events


def scrape_runsim():
    """
    runsim.ru — серия SIM Омск:
    Рождественский полумарафон, Весенний полумарафон ЗаБег.РФ,
    Цветочный забег, Сибирский международный марафон.
    Сайт рендерится через JS, парсим известные страницы событий напрямую.
    """
    print("  runsim.ru")

    KNOWN = [
        ("https://runsim.ru/events/vesennii-polumarafon-zabegrf-2026",
         "Весенний полумарафон ЗаБег.РФ", "Омск", "Омская область",
         "1 км, 5 км, 10 км, 21,1 км", "road"),
        ("https://runsim.ru/events/cvetocnyi-zabeg-2026",
         "Цветочный забег", "Омск", "Омская область",
         "3 км, 10 км", "road"),
        ("https://runsim.ru/events/sibirskii-mezdunarodnyi-marafon2026",
         "37-й Сибирский международный марафон", "Омск", "Омская область",
         "3 км, 10 км, 42,2 км", "road"),
    ]

    events = []
    for url, default_name, city, region, distances, etype in KNOWN:
        html = fetch(url)
        # Сайт JS-rendered, поэтому сразу используем hardcoded данные
        # и пробуем извлечь дату из HTML если получится
        d = None
        if html:
            dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
            for ds in dates[:5]:
                candidate = parse_date(ds)
                if candidate and is_future(candidate):
                    d = candidate
                    break
        # Fallback: берём дату из URL
        if not d:
            if 'vesennii' in url: d = '2026-05-23'
            elif 'cvetocnyi' in url: d = '2026-06-14'
            elif 'sibirskii' in url: d = '2026-08-01'
        if d and is_future(d):
            ev = make_event(d, default_name, city, region, distances, etype, url)
            if ev:
                events.append(ev)
        time.sleep(0.5)

    return events


def scrape_tomskmarathon():
    """tomskmarathon.ru — Томск"""
    print("  tomskmarathon.ru")
    html = fetch("https://tomskmarathon.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', html)
    name = clean(name_m.group(1)) if name_m else "Томский марафон"
    seen = set()
    for db in dates[:5]:
        d = parse_date(db)
        if d and is_future(d) and d not in seen:
            seen.add(d)
            events.append(make_event(d, name, "Томск", "Томская область", "", "road",
                                      "https://tomskmarathon.ru/"))
    return events


def scrape_kazan_run():
    """kazan.run — Казанский марафон"""
    print("  kazan.run")
    html = fetch("https://kazan.run/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for db in dates[:5]:
        d = parse_date(db)
        if d and is_future(d):
            events.append(make_event(d, "Казанский марафон", "Казань",
                                      "Республика Татарстан",
                                      "3 км, 10 км, 21,1 км, 42,2 км", "road",
                                      "https://kazan.run/"))
            break
    return events


def scrape_sib_events():
    """sib-events.ru — Алтай, Сибирь"""
    print("  sib-events.ru")
    html = fetch("https://sib-events.ru/")
    if not html:
        return []
    events = []
    items = re.findall(r'href="(/reg/[^"]+)"[^>]*>(.*?)</a>', html, re.S)
    for href, text in items[:20]:
        text_clean = clean(text)
        if len(text_clean) < 5:
            continue
        d = parse_date(text_clean)
        if not d:
            # пробуем получить дату со страницы события
            sub = fetch("https://sib-events.ru" + href)
            dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d)', sub)
            d = parse_date(dates[0]) if dates else None
        if d and is_future(d):
            name_m = re.search(r'[А-ЯA-Z][^<]{5,60}', text_clean)
            name = name_m.group(0).strip() if name_m else text_clean[:60]
            events.append(make_event(d, name, "Алтайский край", "Алтайский край", "", "road",
                                      "https://sib-events.ru" + href))
    return events[:5]


def scrape_wnmarathon():
    """wnmarathon.runc.run — Марафон Белые ночи СПб"""
    print("  wnmarathon.runc.run")
    html = fetch("https://wnmarathon.runc.run/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for db in dates[:3]:
        d = parse_date(db)
        if d and is_future(d):
            events.append(make_event(d, "Марафон «Белые ночи»", "Санкт-Петербург",
                                      "Санкт-Петербург", "10 км, 42,2 км, эстафета",
                                      "road", "https://wnmarathon.runc.run/"))
            break
    return events


def scrape_moscowhalf():
    """moscowhalf.runc.run — Московский полумарафон"""
    print("  moscowhalf.runc.run")
    html = fetch("https://moscowhalf.runc.run/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for db in dates[:3]:
        d = parse_date(db)
        if d and is_future(d):
            events.append(make_event(d, "Московский полумарафон", "Москва", "Москва",
                                      "5 км, 21,1 км", "road",
                                      "https://moscowhalf.runc.run/"))
            break
    return events


def scrape_springrun():
    """springrun.ru — Весенний полумарафон Новосибирск"""
    print("  springrun.ru")
    html = fetch("https://www.springrun.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for db in dates[:3]:
        d = parse_date(db)
        if d and is_future(d):
            events.append(make_event(d, "Весенний полумарафон Академгородок",
                                      "Новосибирск", "Новосибирская область",
                                      "5 км, 10 км, 21,1 км, детский", "road",
                                      "https://www.springrun.ru/"))
            break
    return events


def scrape_sportsauce():
    """sportsauce.ru — серия Новосибирск"""
    print("  sportsauce.ru")
    html = fetch("https://sportsauce.ru/starts/")
    if not html:
        html = fetch("https://sportsauce.ru/")
    if not html:
        return []
    events = []
    # Ищем карточки с датами
    blocks = re.findall(
        r'<(?:article|div|li)[^>]*class="[^"]*(?:event|start|race)[^"]*"[^>]*>(.*?)</(?:article|div|li)>',
        html, re.S
    )
    if not blocks:
        blocks = re.findall(r'<a href="/starts/[^"]+"[^>]*>(.*?)</a>', html, re.S)
    seen = set()
    for block in blocks[:20]:
        d = parse_date(block)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        name_m = re.search(r'([А-ЯA-Z][^<]{5,60})', block)
        name = clean(name_m.group(1)) if name_m else "Старт Новосибирск"
        events.append(make_event(d, name, "Новосибирск", "Новосибирская область",
                                  "", "road", "https://sportsauce.ru/starts/"))
    return events[:8]


def scrape_timerman():
    """timerman.org — Казань и Татарстан"""
    print("  timerman.org")
    html = fetch("https://timerman.org/events/")
    if not html:
        html = fetch("https://timerman.org/")
    if not html:
        return []
    events = []
    items = re.findall(
        r'<(?:article|div|li)[^>]*>(.*?)</(?:article|div|li)>', html, re.S
    )
    seen = set()
    for item in items[:30]:
        d = parse_date(item)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        name_m = re.search(r'<(?:h[1-4]|a|strong)[^>]*>([^<]{5,80})</(?:h[1-4]|a|strong)>', item)
        name = clean(name_m.group(1)) if name_m else "Старт Казань"
        events.append(make_event(d, name, "Казань", "Республика Татарстан",
                                  "", "road", "https://timerman.org/"))
    return events[:8]


def scrape_topliga():
    """topliga.ru/events — юг России, Сириус"""
    print("  topliga.ru/events")
    html = fetch("https://events.topliga.ru/")
    if not html:
        return []
    events = []
    # Карточки событий
    cards = re.findall(
        r'href="(/event/[^"]+)"[^>]*>(.*?)</a>', html, re.S
    )
    seen = set()
    for href, text in cards[:20]:
        text_c = clean(text)
        if len(text_c) < 4:
            continue
        sub = fetch("https://events.topliga.ru" + href)
        dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', sub)
        d = None
        for db in dates:
            d = parse_date(db)
            if d and is_future(d):
                break
        if not d or d in seen:
            continue
        seen.add(d)
        name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', sub)
        name = clean(name_m.group(1)) if name_m else text_c[:60]
        city_m = re.search(r'(?:Город|Место|Location)[^:]*:\s*([А-Яа-я\s\-]{3,30})', sub)
        city = city_m.group(1).strip() if city_m else "Краснодарский край"
        events.append(make_event(d, name, city, "Краснодарский край", "", "road",
                                  "https://events.topliga.ru" + href))
    return events[:6]


def scrape_alpmarathon():
    """alpmarathon.ru — Иркутский международный марафон"""
    print("  alpmarathon.ru")
    html = fetch("https://alpmarathon.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for db in dates[:3]:
        d = parse_date(db)
        if d and is_future(d):
            events.append(make_event(d, "Иркутский международный марафон",
                                      "Иркутск", "Иркутская область",
                                      "10 км, 21,1 км, 42,2 км", "road",
                                      "https://alpmarathon.ru/"))
            break
    return events


def scrape_myrace():
    """myrace.info — трейловые и другие старты по всей России"""
    print("  myrace.info")
    html = fetch("https://myrace.info/events/")
    if not html:
        html = fetch("https://myrace.info/")
    if not html:
        return []
    events = []
    # Карточки событий
    cards = re.findall(
        r'<(?:article|div)[^>]*class="[^"]*(?:event|race|card)[^"]*"[^>]*>(.*?)</(?:article|div)>',
        html, re.S
    )
    seen = set()
    for card in cards[:30]:
        d = parse_date(card)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        name_m = re.search(r'<(?:h[1-4]|a|strong)[^>]*>([^<]{5,80})</(?:h[1-4]|a|strong)>', card)
        name = clean(name_m.group(1)) if name_m else "Трейл"
        city_m = re.search(r'(?:Город|Место|Локация)[^:]*:\s*([А-Яа-я\s\-]{3,25})', card)
        city = city_m.group(1).strip() if city_m else "Россия"
        url_m = re.search(r'href="(/events/\d+[^"]*)"', card)
        url = ("https://myrace.info" + url_m.group(1)) if url_m else "https://myrace.info/"
        events.append(make_event(d, name, city, "", "", "trail", url))
    return events[:15]


def scrape_rtra():
    """rtra.ru — Кубок RTRA, трейлы по всей России"""
    print("  rtra.ru")
    html = fetch("https://rtra.ru/")
    if not html:
        html = fetch("https://rtra.ru/calendar/")
    if not html:
        return []
    events = []
    items = re.findall(
        r'<(?:tr|div|li)[^>]*>(.*?)</(?:tr|div|li)>', html, re.S
    )
    seen = set()
    for item in items[:40]:
        d = parse_date(item)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        name_m = re.search(r'<(?:td|a|strong)[^>]*>([^<]{5,80})</(?:td|a|strong)>', item)
        name = clean(name_m.group(1)) if name_m else "Трейл RTRA"
        city_m = re.search(r'<td[^>]*>([А-Яа-я][^<]{2,25})</td>', item)
        city = city_m.group(1).strip() if city_m else "Россия"
        events.append(make_event(d, name, city, "", "", "trail", "https://rtra.ru/"))
    return events[:10]


def scrape_skyrunning():
    """skyrunning.ru — горные и трейловые старты"""
    print("  skyrunning.ru")
    html = fetch("https://skyrunning.ru/")
    if not html:
        html = fetch("https://skyrunning.ru/events/")
    if not html:
        return []
    events = []
    items = re.findall(
        r'<(?:article|div|li)[^>]*>(.*?)</(?:article|div|li)>', html, re.S
    )
    seen = set()
    for item in items[:20]:
        d = parse_date(item)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        name_m = re.search(r'<(?:h[1-4]|a|strong)[^>]*>([^<]{5,80})</(?:h[1-4]|a|strong)>', item)
        name = clean(name_m.group(1)) if name_m else "Горный старт"
        events.append(make_event(d, name, "Россия", "", "", "trail",
                                  "https://skyrunning.ru/"))
    return events[:8]


# ─── VK API ──────────────────────────────────────────────────────────────────

VK_GROUPS = [
    ("runningrussia", "Россия"),   # vk.com/runningrussia
    ("krasmarafon",   "Красноярск"),
    ("begaem",        "Россия"),
]

def scrape_vk():
    """
    Парсит стены ВКонтакте через VK API v5.199.
    Требует переменную окружения VK_TOKEN (сервисный ключ доступа).
    Получить: vk.com/dev → Мои приложения → Создать → Ключ доступа сервисного аккаунта
    Добавить в GitHub: Settings → Secrets → Actions → VK_TOKEN
    """
    token = os.environ.get("VK_TOKEN", "")
    if not token:
        print("  [VK] VK_TOKEN не задан — пропускаем ВКонтакте")
        return []

    events = []
    for group_id, default_city in VK_GROUPS:
        print(f"  vk.com/{group_id}")
        url = (
            f"https://api.vk.com/method/wall.get"
            f"?domain={group_id}&count=50&filter=owner"
            f"&access_token={token}&v=5.199"
        )
        data = fetch_json(url)
        if not data or "response" not in data:
            print(f"    [VK ERR] {data}")
            continue

        items = data["response"].get("items", [])
        for post in items:
            text = post.get("text", "")
            if not text or len(text) < 30:
                continue
            # Ищем дату в тексте поста
            dates_found = re.findall(r'\d{1,2}\s+[а-яА-Я]+\s+202\d', text)
            for df in dates_found:
                d = parse_date(df)
                if not d or not is_future(d):
                    continue
                # Ищем название — первая строка поста или слово после эмодзи
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                name = lines[0][:80] if lines else "Беговое событие"
                # Убираем эмодзи и лишние символы из начала
                name = re.sub(r'^[\U0001F000-\U0001FFFF\s#@🏃🏅🎽🏆]+', '', name).strip()
                if len(name) < 4:
                    name = lines[1][:80] if len(lines) > 1 else "Беговое событие"

                # Пробуем определить тип
                etype = "road"
                if re.search(r'трейл|trail|горн|лес|бездорожь', text, re.I):
                    etype = "trail"
                elif re.search(r'ночн|night', text, re.I):
                    etype = "night"

                # Ссылка на пост
                owner_id = post.get("owner_id", 0)
                post_id = post.get("id", 0)
                post_url = f"https://vk.com/wall{owner_id}_{post_id}"

                events.append(make_event(d, name, default_city, "", "", etype, post_url))
                break  # берём первую найденную дату в посте

        time.sleep(0.4)  # VK API rate limit

    return events


def scrape_wildtrail():
    """
    wildtrail.ru — серия трейловых фестивалей по всей России:
    Dagestan Wild Trail, Elbrus Wild Trail, Rosa Wild Fest,
    MMK Wild Fest (Башкирия), Arkhyz Wild Trail, Grand Kislovodsk,
    Sport-Marafon Fest (Никола-Ленивец), City Trail (Москва).
    Парсим главную — там все события с датами и локациями.
    """
    print("  wildtrail.ru")
    html = fetch("https://wildtrail.ru/")
    if not html:
        return []

    events = []

    # На главной блоки вида:
    # Место: Архыз\nДата: 26−28 июня 2026\nДистанции: от 10 км
    # Ищем пары Место+Дата рядом с названием события

    # Сначала вытаскиваем все блоки с датами
    # Паттерн: название (из ссылки или заголовка) + Место + Дата
    blocks = re.findall(
        r'(?:href="(https://(?:wildtrail\.ru/[^"]+|[a-z]+wildtrail\.ru[^"]*|[a-z\-]+\.ru[^"]*?))"[^>]*>)?'
        r'([^<]{5,80})</[^>]+>'
        r'(?:.*?Место:\s*([^\n<]{3,40}))?'
        r'.*?Дата:\s*([^\n<]{5,40})'
        r'(?:.*?Дистанции:\s*([^\n<]{3,60}))?',
        html, re.S
    )

    # Маппинг ссылок → города и регионы
    URL_GEO = {
        'wildtrail.ru/dwt':  ('Дагестан',           'Республика Дагестан'),
        'wildtrail.ru/ewt':  ('Эльбрус',             'Кабардино-Балкария'),
        'wildtrail.ru/rwt':  ('Красная Поляна',      'Краснодарский край'),
        'wildtrail.ru/mmk':  ('Абзаково',            'Республика Башкортостан'),
        'wildtrail.ru/awt':  ('Архыз',               'Карачаево-Черкессия'),
        'wildtrail.ru/gk':   ('Кисловодск',          'Ставропольский край'),
        'wildtrail.ru/nlwwt':('Никола-Ленивец',      'Калужская область'),
        'sportmarafonfest.ru':('Никола-Ленивец',     'Калужская область'),
        'city-trail.ru':     ('Москва',              'Москва'),
        'lightsofderbent.ru':('Дербент',             'Республика Дагестан'),
    }

    seen = set()
    for url, name, place, date_str, distances in blocks:
        name = clean(name)
        if not is_valid_name(name):
            continue
        d = parse_date(date_str)
        if not d or not is_future(d):
            continue

        # Определяем город
        city, region = '', ''
        for key, geo in URL_GEO.items():
            if key in (url or ''):
                city, region = geo
                break
        if not city and place:
            city = clean(place).split(',')[0].strip()
            region = ''

        if not city:
            city = 'Россия'

        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)

        ev = make_event(d, name, city, region,
                        clean(distances) if distances else 'от 10 км',
                        'trail', url or 'https://wildtrail.ru/')
        if ev:
            events.append(ev)

    # Если регулярка не сработала — используем жёстко заданные события с сайта
    if not events:
        HARDCODED = [
            ("2026-02-14", "Т-Банк Nikola-Lenivets Winter Wild Trail", "Никола-Ленивец", "Калужская область",       "от 10 до 50 км",   "https://wildtrail.ru/nlwwt"),
            ("2026-04-10", "Т-Банк Dagestan Wild Trail",               "Дагестан",       "Республика Дагестан",     "от 10 до 100 км",  "https://wildtrail.ru/dwt"),
            ("2026-05-02", "Т-Банк Grand Kislovodsk",                  "Кисловодск",     "Ставропольский край",     "от 5 до 105 км",   "https://wildtrail.ru/gk"),
            ("2026-06-11", "Т-Банк Sport-Marafon Fest",                "Никола-Ленивец", "Калужская область",       "от 10 до 100 км",  "https://sportmarafonfest.ru"),
            ("2026-06-26", "Т-Банк Arkhyz Wild Trail",                 "Архыз",          "Карачаево-Черкессия",     "от 10 км",         "https://wildtrail.ru/awt"),
            ("2026-08-08", "Т-Банк Elbrus Wild Trail",                 "Эльбрус",        "Кабардино-Балкария",      "от 5 до 130 км",   "https://wildtrail.ru/ewt"),
            ("2026-08-21", "Т-Банк MMK Wild Fest",                     "Абзаково",       "Республика Башкортостан", "от 11 до 95 км",   "https://wildtrail.ru/mmk"),
            ("2026-09-04", "Т-Банк Rosa Wild Fest",                    "Красная Поляна", "Краснодарский край",      "от 10 до 180 км",  "https://wildtrail.ru/rwt"),
        ]
        for date, name, city, region, distances, url in HARDCODED:
            if is_future(date):
                ev = make_event(date, name, city, region, distances, 'trail', url)
                if ev:
                    events.append(ev)

    return events



    """
    runc.run — главный сайт серии: Московский марафон, Белые ночи,
    СПБ полумарафон, Фестиваль бега, Ночной забег, Красочный забег и др.
    Парсим главную, при 403 — парсим субдомены напрямую.
    """
    print("  runc.run")

    SUBDOMAINS = [
        ("https://moscowmarathon.runc.run/", "СберПрайм Московский Марафон",       "Москва",           "Москва",           "42,2 км, 10 км, эстафета",  "road"),
        ("https://moscowhalf.runc.run/",     "Московский полумарафон",              "Москва",           "Москва",           "21,1 км, 5 км, эстафета",   "road"),
        ("https://wnmarathon.runc.run/",     "СберПрайм Марафон «Белые ночи»",     "Санкт-Петербург",  "Санкт-Петербург",  "42,2 км, 10 км, эстафета",  "road"),
        ("https://spbhalf.runc.run/",        "СПБ полумарафон «Северная столица»",  "Санкт-Петербург",  "Санкт-Петербург",  "21,1 км, 10 км, эстафета",  "road"),
        ("https://runfest.runc.run/",        "Большой фестиваль бега",              "Москва",           "Москва",           "5 км, 10 км",               "road"),
        ("https://nightrun10km.runc.run/",   "Ночной забег",                        "Москва",           "Москва",           "10 км",                     "night"),
        ("https://colorrun5km.runc.run/",    "Красочный забег",                     "Москва",           "Москва",           "5 км",                      "road"),
        ("https://gardenring.runc.run/",     "Эстафета по Садовому кольцу",         "Москва",           "Москва",           "15 км, эстафета",           "road"),
    ]

    current_year = datetime.utcnow().year
    events = []
    seen = set()

    # Попытка 1: главная страница
    html = fetch("https://runc.run/")
    if html:
        pattern = re.compile(
            r'(\d{1,2}(?:-\d{1,2})?\s+[а-яА-Я]+)'
            r'[^<]{0,30}'
            r'href="(https://[a-z0-9\-]+\.runc\.run/[^"#]*)"'
            r'[^>]*>([^<]{3,80})</a>',
            re.S
        )
        for m in pattern.finditer(html):
            date_str, url, name = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            name = clean(name)
            if not is_valid_name(name):
                continue
            d = parse_date(date_str + f' {current_year}')
            if not d:
                d = parse_date(date_str + f' {current_year + 1}')
            if not d or not is_future(d):
                continue
            city, region = 'Москва', 'Москва'
            if any(x in url.lower() or x in name.lower() for x in ['spb', 'петербург', 'белые', 'северн']):
                city, region = 'Санкт-Петербург', 'Санкт-Петербург'
            etype = 'road'
            if re.search(r'ночн|night', name.lower()):
                etype = 'night'
            elif re.search(r'кросс|trail|трейл|лисья', name.lower()):
                etype = 'trail'
            key = (d, name[:30])
            if key in seen:
                continue
            seen.add(key)
            ev = make_event(d, name, city, region, '', etype, url)
            if ev:
                events.append(ev)
        if events:
            return events

    # Попытка 2: парсим субдомены напрямую
    for url, default_name, city, region, distances, etype in SUBDOMAINS:
        sub = fetch(url)
        if not sub:
            continue
        dates = re.findall(r'(\d{1,2}(?:-\d{1,2})?\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', sub)
        name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', sub)
        name = clean(name_m.group(1)) if name_m else default_name
        if not is_valid_name(name):
            name = default_name
        for ds in dates[:3]:
            d = parse_date(ds)
            if d and is_future(d):
                key = (d, name[:30])
                if key not in seen:
                    seen.add(key)
                    ev = make_event(d, name, city, region, distances, etype, url)
                    if ev:
                        events.append(ev)
                break
        time.sleep(0.5)

    return events


def scrape_trail1():
    """trail1.ru — многодневный трейл на Камчатке"""
    print("  trail1.ru")
    html = fetch("https://trail1.ru/")
    if not html:
        return []
    events = []
    # Ищем даты вида "10-13 сентября 2026"
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    # Страницы дистанций
    DAYS = [
        ("https://trail1.ru/warmthoftheearth", "Trail-1 «Тепло Земли»",            "30 км (↑1300 м), вулкан Горелый"),
        ("https://trail1.ru/ursa",             "Trail-1 «Урса. Путеводная звезда»", "20 км (↑1300 м), массив Вачкажец"),
        ("https://trail1.ru/anotherplanet",    "Trail-1 «Другая планета»",          "17 км (↑2000 м), вулкан Авачинский"),
        ("https://trail1.ru/oceansong",        "Trail-1 «Океанская песня»",         "32 км (↑900 м), берег Тихого океана"),
    ]
    # Определяем стартовую дату из главной страницы
    start_date = None
    for ds in dates[:5]:
        d = parse_date(ds)
        if d and is_future(d):
            start_date = d
            break
    if not start_date:
        return []
    from datetime import date as _date, timedelta
    base = _date.fromisoformat(start_date)
    for i, (url, name, distances) in enumerate(DAYS):
        day_date = (base + timedelta(days=i)).isoformat()
        if is_future(day_date):
            ev = make_event(day_date, name, "Петропавловск-Камчатский",
                            "Камчатский край", distances, "trail", url)
            if ev:
                events.append(ev)
    return events


def scrape_norilsktrail():
    """norilsktrail.ru — Норильск. Горный старт на плато Путорана"""
    print("  norilsktrail.ru")
    html = fetch("https://norilsktrail.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for ds in dates[:5]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Норильск. Горный старт",
                            "Норильск", "Красноярский край",
                            "5 км, 15 км, 30 км, 50 км, 70 км, детский",
                            "trail", "https://norilsktrail.ru")
            if ev:
                events.append(ev)
            break
    return events


def scrape_runc_run():
    """
    runc.run — серия: Московский марафон, Белые ночи, СПБ полумарафон,
    Большой фестиваль бега, Ночной забег, Красочный забег и др.
    Парсим главную, при 403 — субдомены напрямую.
    """
    print("  runc.run")

    SUBDOMAINS = [
        ("https://moscowmarathon.runc.run/", "СберПрайм Московский Марафон",      "Москва",          "Москва",          "42,2 км, 10 км, эстафета",  "road"),
        ("https://moscowhalf.runc.run/",     "Московский полумарафон",             "Москва",          "Москва",          "21,1 км, 5 км, эстафета",   "road"),
        ("https://wnmarathon.runc.run/",     "СберПрайм Марафон «Белые ночи»",    "Санкт-Петербург", "Санкт-Петербург", "42,2 км, 10 км, эстафета",  "road"),
        ("https://spbhalf.runc.run/",        "СПБ полумарафон «Северная столица»", "Санкт-Петербург", "Санкт-Петербург", "21,1 км, 10 км, эстафета",  "road"),
        ("https://runfest.runc.run/",        "Большой фестиваль бега",             "Москва",          "Москва",          "5 км, 10 км",               "road"),
        ("https://nightrun10km.runc.run/",   "Ночной забег",                       "Москва",          "Москва",          "10 км",                     "night"),
        ("https://colorrun5km.runc.run/",    "Красочный забег",                    "Москва",          "Москва",          "5 км",                      "road"),
        ("https://gardenring.runc.run/",     "Эстафета по Садовому кольцу",        "Москва",          "Москва",          "15 км, эстафета",           "road"),
    ]

    current_year = datetime.utcnow().year
    events = []
    seen = set()

    html = fetch("https://runc.run/")
    if html:
        pattern = re.compile(
            r'(\d{1,2}(?:-\d{1,2})?\s+[а-яА-Я]+)'
            r'[^<]{0,30}'
            r'href="(https://[a-z0-9\-]+\.runc\.run/[^"#]*)"'
            r'[^>]*>([^<]{3,80})</a>',
            re.S
        )
        for m in pattern.finditer(html):
            date_str, url, name = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            name = clean(name)
            if not is_valid_name(name):
                continue
            d = parse_date(date_str + f' {current_year}')
            if not d:
                d = parse_date(date_str + f' {current_year + 1}')
            if not d or not is_future(d):
                continue
            city, region = 'Москва', 'Москва'
            if any(x in url.lower() or x in name.lower() for x in ['spb', 'петербург', 'белые', 'северн']):
                city, region = 'Санкт-Петербург', 'Санкт-Петербург'
            etype = 'road'
            if re.search(r'ночн|night', name.lower()):
                etype = 'night'
            elif re.search(r'кросс|trail|трейл|лисья', name.lower()):
                etype = 'trail'
            key = (d, name[:30])
            if key in seen:
                continue
            seen.add(key)
            ev = make_event(d, name, city, region, '', etype, url)
            if ev:
                events.append(ev)
        if events:
            return events

    for url, default_name, city, region, distances, etype in SUBDOMAINS:
        sub = fetch(url)
        if not sub:
            continue
        dates = re.findall(r'(\d{1,2}(?:-\d{1,2})?\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', sub)
        name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', sub)
        name = clean(name_m.group(1)) if name_m else default_name
        if not is_valid_name(name):
            name = default_name
        for ds in dates[:3]:
            d = parse_date(ds)
            if d and is_future(d):
                key = (d, name[:30])
                if key not in seen:
                    seen.add(key)
                    ev = make_event(d, name, city, region, distances, etype, url)
                    if ev:
                        events.append(ev)
                break
        time.sleep(0.5)

    return events



    """
    runc.run — серия: Московский марафон, Белые ночи, СПБ полумарафон,
    Большой фестиваль бега, Ночной забег, Красочный забег и др.
    Парсим главную, при 403 — субдомены напрямую.
    """
    print("  runc.run")

    SUBDOMAINS = [
        ("https://moscowmarathon.runc.run/", "СберПрайм Московский Марафон",      "Москва",          "Москва",          "42,2 км, 10 км, эстафета",  "road"),
        ("https://moscowhalf.runc.run/",     "Московский полумарафон",             "Москва",          "Москва",          "21,1 км, 5 км, эстафета",   "road"),
        ("https://wnmarathon.runc.run/",     "СберПрайм Марафон «Белые ночи»",    "Санкт-Петербург", "Санкт-Петербург", "42,2 км, 10 км, эстафета",  "road"),
        ("https://spbhalf.runc.run/",        "СПБ полумарафон «Северная столица»", "Санкт-Петербург", "Санкт-Петербург", "21,1 км, 10 км, эстафета",  "road"),
        ("https://runfest.runc.run/",        "Большой фестиваль бега",             "Москва",          "Москва",          "5 км, 10 км",               "road"),
        ("https://nightrun10km.runc.run/",   "Ночной забег",                       "Москва",          "Москва",          "10 км",                     "night"),
        ("https://colorrun5km.runc.run/",    "Красочный забег",                    "Москва",          "Москва",          "5 км",                      "road"),
        ("https://gardenring.runc.run/",     "Эстафета по Садовому кольцу",        "Москва",          "Москва",          "15 км, эстафета",           "road"),
    ]

    current_year = datetime.utcnow().year
    events = []
    seen = set()

    # Попытка 1: главная страница
    html = fetch("https://runc.run/")
    if html:
        pattern = re.compile(
            r'(\d{1,2}(?:-\d{1,2})?\s+[а-яА-Я]+)'
            r'[^<]{0,30}'
            r'href="(https://[a-z0-9\-]+\.runc\.run/[^"#]*)"'
            r'[^>]*>([^<]{3,80})</a>',
            re.S
        )
        for m in pattern.finditer(html):
            date_str, url, name = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
            name = clean(name)
            if not is_valid_name(name):
                continue
            d = parse_date(date_str + f' {current_year}')
            if not d:
                d = parse_date(date_str + f' {current_year + 1}')
            if not d or not is_future(d):
                continue
            city, region = 'Москва', 'Москва'
            if any(x in url.lower() or x in name.lower() for x in ['spb', 'петербург', 'белые', 'северн']):
                city, region = 'Санкт-Петербург', 'Санкт-Петербург'
            etype = 'road'
            if re.search(r'ночн|night', name.lower()):
                etype = 'night'
            elif re.search(r'кросс|trail|трейл|лисья', name.lower()):
                etype = 'trail'
            key = (d, name[:30])
            if key in seen:
                continue
            seen.add(key)
            ev = make_event(d, name, city, region, '', etype, url)
            if ev:
                events.append(ev)
        if events:
            return events

    # Попытка 2: субдомены напрямую
    for url, default_name, city, region, distances, etype in SUBDOMAINS:
        sub = fetch(url)
        if not sub:
            continue
        dates = re.findall(r'(\d{1,2}(?:-\d{1,2})?\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', sub)
        name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', sub)
        name = clean(name_m.group(1)) if name_m else default_name
        if not is_valid_name(name):
            name = default_name
        for ds in dates[:3]:
            d = parse_date(ds)
            if d and is_future(d):
                key = (d, name[:30])
                if key not in seen:
                    seen.add(key)
                    ev = make_event(d, name, city, region, distances, etype, url)
                    if ev:
                        events.append(ev)
                break
        time.sleep(0.5)

    return events


def scrape_elbrus_redfox():
    """elbrus.redfox.ru — Red Fox Elbrus Race, горный фестиваль"""
    print("  elbrus.redfox.ru")
    html = fetch("https://elbrus.redfox.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s*[-–]\s*\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Red Fox Elbrus Race", "Эльбрус", "Кабардино-Балкария",
                            "скайраннинг, ски-альпинизм, снегоступинг", "trail",
                            "https://elbrus.redfox.ru/")
            if ev:
                events.append(ev)
            break
    return events


def scrape_taigatrail():
    """taigatrail.run — серия Taiga Trail: Манжерок, Шерегеш, Новосибирск"""
    print("  taigatrail.run")
    html = fetch("https://taigatrail.run/")
    if not html:
        return []
    events = []
    # Ищем блоки с датами и ссылками на страницы событий
    blocks = re.findall(
        r'href="(https://taigatrail\.run/[^"]+)"[^>]*>.*?'
        r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)'
        r'.*?([А-ЯA-Z][^\n<]{3,60})',
        html, re.S
    )
    seen = set()
    for url, date_str, name in blocks[:10]:
        d = parse_date(date_str)
        if not d or not is_future(d):
            continue
        name = clean(name)
        if not is_valid_name(name):
            continue
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        # Определяем город по URL
        city, region = "Сибирь", "Сибирский федеральный округ"
        if 'manzherok' in url or 'maytrail' in url:
            city, region = "Манжерок", "Республика Алтай"
        elif 'gesh' in url:
            city, region = "Шерегеш", "Кемеровская область"
        elif 'october' in url or 'novosibirsk' in url:
            city, region = "Новосибирск", "Новосибирская область"
        ev = make_event(d, name, city, region, "", "trail", url)
        if ev:
            events.append(ev)
    return events


def scrape_galtropa():
    """galtropa.ru — Галичское Заозерье, Костромская область"""
    print("  galtropa.ru")
    html = fetch("https://galtropa.ru/")
    if not html:
        return []
    events = []
    # Страница содержит блоки: название + дата
    items = re.findall(
        r'\*{0,2}\[([^\]]{5,60})\]\((https://galtropa\.ru/[^)]+)\)\*{0,2}\s*'
        r'(\d{1,2}[−–.\-]\d{1,2}\.\d{4}|\d{1,2}\.\d{2}\.\d{4})',
        html
    )
    seen = set()
    for name, url, date_str in items[:10]:
        d = parse_date(date_str)
        if not d or not is_future(d):
            continue
        name = clean(name)
        if not is_valid_name(name):
            continue
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        etype = "trail" if re.search(r'трейл|спортфест|рогейн', name, re.I) else "road"
        ev = make_event(d, name, "Галич", "Костромская область", "", etype, url)
        if ev:
            events.append(ev)
    return events


def scrape_sambatrail():
    """sambatrail.ru — трейлы Саратовской области"""
    print("  sambatrail.ru")
    html = fetch("https://www.sambatrail.ru/")
    if not html:
        return []
    events = []
    # Блоки: дата + название + ссылка
    blocks = re.findall(
        r'(\d{1,2}[-–]\s*\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)'
        r'.*?href="(https://www\.sambatrail\.ru/[^"]+)"[^>]*>\s*\[?([^\]\n<]{5,60})',
        html, re.S
    )
    seen = set()
    for date_str, url, name in blocks[:10]:
        d = parse_date(date_str)
        if not d or not is_future(d):
            continue
        name = clean(name)
        if not is_valid_name(name):
            continue
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        ev = make_event(d, name, "Саратов", "Саратовская область", "", "trail", url)
        if ev:
            events.append(ev)
    return events


def scrape_altai_trail():
    """altai-trail.ru — Altai Ultra-Trail, БЧТ и серия стартов"""
    print("  altai-trail.ru")
    html = fetch("https://altai-trail.ru/calendar/")
    if not html:
        html = fetch("https://altai-trail.ru/")
    if not html:
        return []
    events = []
    # Календарь содержит строки вида: [Название - дата](url)
    items = re.findall(
        r'\[([^\]]{5,80}[-–]\s*\d{1,2}[.\-]\d{2}\.202\d[^\]]*)\]\((https://[^)]+)\)',
        html
    )
    seen = set()
    for text, url in items[:15]:
        # Извлекаем дату из конца строки
        date_m = re.search(r'(\d{1,2}[.\-]\d{2}\.202\d)', text)
        if not date_m:
            continue
        d = parse_date(date_m.group(1))
        if not d or not is_future(d):
            continue
        # Название — всё до даты
        name = clean(re.sub(r'\s*[-–]\s*\d{1,2}[.\-]\d{2}\.202\d.*', '', text))
        if not is_valid_name(name):
            continue
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        city = "Горный Алтай"
        region = "Республика Алтай"
        if 'bkt' in url.lower():
            city = "Белуха"
        ev = make_event(d, name, city, region, "", "trail", url)
        if ev:
            events.append(ev)
    return events


def scrape_wildpeak():
    """wildsiberia.ru/wild-peak — горный трейл в Акташе"""
    print("  wildsiberia.ru/wild-peak")
    html = fetch("https://wildsiberia.ru/wild-peak")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Wild Peak", "Акташ", "Республика Алтай",
                            "7, 15, 35, 66 км (набор до 3700 м)", "trail",
                            "https://wildsiberia.ru/wild-peak")
            if ev:
                events.append(ev)
            break
    return events


def scrape_wildsiberia():
    """wildsiberia.ru — экстремальный триатлон Wild Siberia 226/113"""
    print("  wildsiberia.ru")
    html = fetch("https://wildsiberia.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    seen = set()
    for ds in dates[:5]:
        d = parse_date(ds)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        ev = make_event(d, "Wild Siberia 226", "Акташ", "Республика Алтай",
                        "226 км (плавание 3,8 + вело 180 + бег 42,2 км)", "road",
                        "https://wildsiberia.ru")
        if ev:
            events.append(ev)
    return events


def scrape_city_trail():
    """city-trail.ru — серия городских трейлов в парках Москвы"""
    print("  city-trail.ru")
    html = fetch("https://city-trail.ru/")
    if not html:
        return []
    events = []
    # На странице блоки: номер этапа + дата + место
    blocks = re.findall(
        r'href="(https://city-trail\.ru/\d+)"[^>]*>.*?'
        r'(\d{1,2}\s+[а-яА-Я]+).*?'
        r'([А-Яа-я][^\n<]{3,40})',
        html, re.S
    )
    current_year = datetime.utcnow().year
    seen = set()
    for url, date_str, place in blocks[:10]:
        d = parse_date(date_str + f' {current_year}')
        if not d or not is_future(d):
            continue
        # Извлекаем номер этапа из URL
        num_m = re.search(r'/(\d+)$', url)
        num = num_m.group(1) if num_m else '?'
        name = f"City Trail #{num} {clean(place)}"
        if not is_valid_name(name):
            continue
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        ev = make_event(d, name, "Москва", "Москва", "5–30 км + вело", "trail", url)
        if ev:
            events.append(ev)
    return events


def scrape_run2kremlins():
    """run2kremlins.ru — пробег От Кремля до Кремля, Коломна→Зарайск"""
    print("  run2kremlins.ru")
    html = fetch("https://run2kremlins.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Пробег «От Кремля до Кремля»",
                            "Коломна", "Московская область",
                            "65 км (соло) или эстафета 4×12–20 км",
                            "road", "https://run2kremlins.ru")
            if ev:
                events.append(ev)
            break
    return events


def scrape_paris_running():
    """paris-running.ru — Парижский полумарафон, Красноуфимск"""
    print("  paris-running.ru")
    html = fetch("https://paris-running.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', html)
            name = clean(name_m.group(1)) if name_m else "Парижский полумарафон"
            if not is_valid_name(name):
                name = "Парижский полумарафон"
            ev = make_event(d, name, "Красноуфимск", "Свердловская область",
                            "5, 10, 21,1 км, детский, ночной 1,6 км",
                            "trail", "https://paris-running.ru")
            if ev:
                events.append(ev)
            break
    return events


def scrape_donspacetrail():
    """donspacetrail.tilda.ws — трейлы Ростовской области"""
    print("  donspacetrail.tilda.ws")
    html = fetch("https://donspacetrail.tilda.ws/pogorelov")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Ультра Погорелов DON SPACE TRAIL",
                            "Белая Калитва", "Ростовская область",
                            "5, 10, 25, 50 км, детский 1,5 км",
                            "trail", "https://donspacetrail.tilda.ws/pogorelov")
            if ev:
                events.append(ev)
            break
    return events


def scrape_taganay_ultra():
    """ultra.irunclub.ru — ультрамарафон Taganay-Turgoyak"""
    print("  ultra.irunclub.ru")
    html = fetch("https://ultra.irunclub.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Ультрамарафон Taganay-Turgoyak",
                            "Миасс", "Челябинская область",
                            "9,5 км, 30 км, 65 км, скандинавская ходьба, детский",
                            "trail", "https://ultra.irunclub.ru")
            if ev:
                events.append(ev)
            break
    return events


def scrape_trail1():
    """trail1.ru — многодневная гонка Trail-1 (Камчатка и др.)"""
    print("  trail1.ru")
    html = fetch("https://trail1.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', html)
    name = clean(name_m.group(1)) if name_m and is_valid_name(clean(name_m.group(1))) else "Trail-1 многодневная гонка"
    city_m = re.search(r'(?:Камчатк|Петропавловск|Байкал|Алтай|Кавказ)', html)
    city = "Петропавловск-Камчатский" if city_m and "Камчатк" in city_m.group(0) else "Россия"
    region = "Камчатский край" if "Камчатк" in html else ""
    seen = set()
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d) and d not in seen:
            seen.add(d)
            ev = make_event(d, name, city, region, "", "trail", "https://trail1.ru")
            if ev:
                events.append(ev)
    return events


def scrape_norilsktrail():
    """norilsktrail.ru — Норильск. Горный старт, плато Путорана"""
    print("  norilsktrail.ru")
    html = fetch("https://norilsktrail.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Норильск. Горный старт", "Норильск", "Красноярский край",
                            "5 км, 15 км, 30 км, 50 км, 70 км, детский",
                            "trail", "https://norilsktrail.ru")
            if ev:
                events.append(ev)
            break
    return events


def scrape_edge_ultra():
    """edge-ultra.ru — Alol Ultra Trail, Псковская область"""
    print("  edge-ultra.ru")
    html = fetch("https://edge-ultra.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    name_m = re.search(r'<h1[^>]*>([^<]{5,80})</h1>', html)
    name = clean(name_m.group(1)) if name_m and is_valid_name(clean(name_m.group(1))) else "Alol Ultra Trail"
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, name, "Пустошка", "Псковская область",
                            "5, 10, 20, 30, 50, 100, 180 км",
                            "trail", "https://edge-ultra.ru")
            if ev:
                events.append(ev)
            break
    return events


def scrape_okarivertrail():
    """okarivertrail.ru — Oka River Trail, Рязанская область"""
    print("  okarivertrail.ru")
    html = fetch("https://okarivertrail.ru/")
    if not html:
        return []
    events = []
    dates = re.findall(r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\s+[а-яА-Я]+\s+202\d)', html)
    for ds in dates[:3]:
        d = parse_date(ds)
        if d and is_future(d):
            ev = make_event(d, "Oka River Trail", "Выползово", "Рязанская область",
                            "5 км, 10 км, 30 км, 50 км",
                            "trail", "https://okarivertrail.ru")
            if ev:
                events.append(ev)
            break
    return events


def scrape_russiarunning():
    """
    reg.russiarunning.com — крупнейшая платформа регистрации на забеги.
    Парсим страницу предстоящих событий.
    """
    print("  reg.russiarunning.com")
    html = fetch("https://reg.russiarunning.com/events")
    if not html:
        html = fetch("https://reg.russiarunning.com/")
    if not html:
        return []
    events = []
    # Карточки событий
    cards = re.findall(
        r'href="(/event/[^"]+)"[^>]*>(.*?)</a>',
        html, re.S
    )
    seen = set()
    for path, content in cards[:30]:
        content_clean = clean(content)
        if not is_valid_name(content_clean):
            continue
        d = parse_date(content_clean)
        if not d or not is_future(d):
            continue
        key = (d, content_clean[:30])
        if key in seen:
            continue
        seen.add(key)
        url = "https://reg.russiarunning.com" + path
        ev = make_event(d, content_clean, "Россия", "", "", "road", url)
        if ev:
            events.append(ev)
    return events[:10]


def scrape_toplist():
    """toplist.run — агрегатор/платформа регистрации на трейлы"""
    print("  toplist.run")
    html = fetch("https://toplist.run/races/")
    if not html:
        html = fetch("https://toplist.run/")
    if not html:
        return []
    events = []
    cards = re.findall(
        r'href="(/race/[^"]+)"[^>]*>(.*?)</a>',
        html, re.S
    )
    seen = set()
    for path, content in cards[:20]:
        name = clean(content)
        if not is_valid_name(name):
            continue
        d = parse_date(content)
        if not d or not is_future(d):
            continue
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        url = "https://toplist.run" + path
        ev = make_event(d, name, "Россия", "", "", "trail", url)
        if ev:
            events.append(ev)
    return events[:10]


def scrape_beg40():
    """бег40.рф — Калужская область: Космический марафон, Атомный трейл"""
    print("  бег40.рф")
    html = fetch("https://xn--40-emcadbfdgn.xn--p1ai/events")
    if not html:
        html = fetch("https://xn--40-emcadbfdgn.xn--p1ai/")
    if not html:
        return []
    events = []
    items = re.findall(
        r'href="/events/(\d+)"[^>]*>(.*?)</a>',
        html, re.S
    )
    seen = set()
    for event_id, content in items[:15]:
        name = clean(content)
        if not is_valid_name(name):
            continue
        d = parse_date(content)
        if not d or not is_future(d):
            continue
        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)
        etype = "trail" if re.search(r'трейл|trail', name, re.I) else "road"
        url = f"https://xn--40-emcadbfdgn.xn--p1ai/events/{event_id}"
        ev = make_event(d, name, "Калуга", "Калужская область", "", etype, url)
        if ev:
            events.append(ev)
    return events


def scrape_zabeg_rf():
    """забег.рф — всероссийская серия массовых забегов по городам"""
    print("  забег.рф")
    html = fetch("https://xn--e1afamqp.xn--p1ai/")  # IDN: забег.рф
    if not html:
        html = fetch("https://zabeg.run/")
    if not html:
        return []
    events = []
    # Серия проходит одновременно в десятках городов
    dates = re.findall(r'(\d{1,2}\s+[а-яА-Я]+\s+202\d|\d{1,2}\.\d{2}\.202\d)', html)
    cities_m = re.findall(r'(?:Москва|Санкт-Петербург|Новосибирск|Екатеринбург|Казань|Нижний Новгород)', html)
    seen_dates = set()
    for ds in dates[:5]:
        d = parse_date(ds)
        if not d or not is_future(d) or d in seen_dates:
            continue
        seen_dates.add(d)
        # Добавляем как одно событие "Забег РФ (по всей России)"
        ev = make_event(d, "Забег РФ", "Россия (все города)", "",
                        "1 км, 5 км, 10 км, 21,1 км",
                        "road", "https://xn--e1afamqp.xn--p1ai/")
        if ev:
            events.append(ev)
    return events


def scrape_otime():
    """
    reg.o-time.ru — платформа регистрации на забеги СПб и Северо-Запада.
    Парсим календарь предстоящих событий.
    """
    print("  reg.o-time.ru")
    html = fetch("https://reg.o-time.ru/calendar")
    if not html:
        return []

    events = []
    seen = set()

    # Страница использует windows-1251, fetch уже декодирует
    # Формат строк: DD.MM.YYYY :: г. Город  Название события
    rows = re.findall(
        r'(\d{2}\.\d{2}\.202\d)\s*::\s*([^\n<]{3,80})',
        html
    )

    for date_str, rest in rows[:30]:
        d = parse_date(date_str)
        if not d or not is_future(d):
            continue

        # rest = "г. Выборг  XXI Выборгский полумарафон" — убираем город из начала
        rest_clean = re.sub(r'^г\.\s*\S+\s+', '', rest.strip())
        name = clean(rest_clean)
        if not is_valid_name(name):
            continue

        # Город — слово после "г."
        city_m = re.search(r'г\.\s*(\S+)', rest)
        city = city_m.group(1).strip('.,') if city_m else "Санкт-Петербург"
        region = ""

        key = (d, name[:30])
        if key in seen:
            continue
        seen.add(key)

        etype = "trail" if re.search(r'трейл|trail|кросс', name, re.I) else "road"
        ev = make_event(d, name, city, region, "", etype,
                        "https://reg.o-time.ru/calendar")
        if ev:
            events.append(ev)

    return events[:15]


def scrape_goldenultra():
    """
    goldenultra.ru — серия Running Heroes Russia:
    Golden Ring Ultra-Trail, Mad Fox Ultra, Белая Невеста,
    CrazyOwl50, Воттоваара, Баскунчак, Хребет Кодара и др.
    Проверяем каждый старт отдельно — у каждого своя страница.
    """
    print("  goldenultra.ru")

    # Список стартов: (url, название по умолчанию, город, регион, дистанции, тип)
    RACES = [
        ("https://goldenultra.ru/grut/",
         "Golden Ring Ultra-Trail 100", "Суздаль", "Владимирская область",
         "5, 10, 20, 30, 50, 80, 100 км, SE 30K, HN 10K, детский", "trail"),

        ("https://goldenultra.ru/madfox/",
         "Mad Fox Ultra", "Переславль-Залесский", "Ярославская область",
         "10 км, 40 км, 100 миль", "trail"),

        ("https://goldenultra.ru/wbu/",
         "Белая Невеста Геленджик (White Bride Ultra)", "Геленджик", "Краснодарский край",
         "4,2 км, 15 км, 30 км, 50 км, 70 км, 120 км", "trail"),

        ("https://goldenultra.ru/crazyowl/",
         "CrazyOwl50 — Сумасшедшая Сова", "Переславль-Залесский", "Ярославская область",
         "10 км, 30 км, 50 км (ночной)", "night"),

        ("https://goldenultra.ru/bud/",
         "Баскунчак Ультра Дискавери", "Баскунчак", "Астраханская область",
         "ультра", "trail"),

        ("https://goldenultra.ru/kuge/",
         "Рыбачий-Териберка Ultra Grand Escape", "Мурманск", "Мурманская область",
         "ультра", "trail"),

        ("https://goldenultra.ru/krcs/",
         "Хребет Кодара — Пески Чара (Life Journey Race)", "Чара", "Забайкальский край",
         "трейл-экспедиция", "trail"),

        ("https://goldenultra.ru/cameltrophy/",
         "Трофи Верблюда. Калмыкия (Kalmyk Camel Trophy)", "Элиста", "Республика Калмыкия",
         "ультра", "trail"),

        ("https://goldenultra.ru/vmr/",
         "Воттоваара Ультра (Vottovaara Mountain Race)", "Гимолы", "Республика Карелия",
         "14 км, 55 км, 50 миль, 100 миль", "trail"),

        ("https://ultras.goldenultra.ru/",
         "ANTA Кросс Московский Дрифт", "Москва", "Москва",
         "кросс", "trail"),
    ]

    events = []
    seen = set()

    for url, default_name, city, region, distances, etype in RACES:
        html = fetch(url)
        if not html:
            continue

        # Ищем дату в формате "DD-DD месяца YYYY" или "DD месяца YYYY"
        date_patterns = [
            r'(\d{1,2}[-–]\d{1,2}\s+[а-яА-Я]+\s+202\d)',  # диапазон
            r'(\d{1,2}\s+[а-яА-Я]+\s+202\d)',               # одна дата
            r'(\d{2}\.\d{2}\.202\d)',                         # DD.MM.YYYY
        ]

        found_date = None
        for pat in date_patterns:
            dates = re.findall(pat, html)
            for ds in dates[:5]:
                d = parse_date(ds)
                if d and is_future(d):
                    found_date = d
                    break
            if found_date:
                break

        if not found_date:
            time.sleep(0.3)
            continue

        # Пробуем найти реальное название на странице
        name_m = re.search(r'<h1[^>]*>([^<]{5,100})</h1>', html)
        name = clean(name_m.group(1)) if name_m and is_valid_name(clean(name_m.group(1))) \
               else default_name

        key = (found_date, name[:30])
        if key not in seen:
            seen.add(key)
            ev = make_event(found_date, name, city, region, distances, etype, url)
            if ev:
                events.append(ev)
                print(f"    → {found_date}  {name}")

        time.sleep(0.5)

    return events


# ─── MERGE & SAVE ────────────────────────────────────────────────────────────

SOURCES = [
    ("krasmarafon.ru",           scrape_krasmarafon),
    ("pushkin-run.ru",           scrape_pushkin_run),
    ("heroleague.ru",            scrape_heroleague),
    ("ea-m.org",                 scrape_ea_m),
    ("runsim.ru",                scrape_runsim),
    ("tomskmarathon.ru",         scrape_tomskmarathon),
    ("kazan.run",                scrape_kazan_run),
    ("sib-events.ru",            scrape_sib_events),
    ("runc.run",                 scrape_runc_run),
    ("wildtrail.ru",             scrape_wildtrail),
    ("wnmarathon.runc.run",      scrape_wnmarathon),
    ("moscowhalf.runc.run",      scrape_moscowhalf),
    ("springrun.ru",             scrape_springrun),
    ("sportsauce.ru",            scrape_sportsauce),
    ("timerman.org",             scrape_timerman),
    ("topliga.ru/events",        scrape_topliga),
    ("alpmarathon.ru",           scrape_alpmarathon),
    ("myrace.info",              scrape_myrace),
    ("rtra.ru",                  scrape_rtra),
    ("skyrunning.ru",            scrape_skyrunning),
    ("elbrus.redfox.ru",         scrape_elbrus_redfox),
    ("taigatrail.run",           scrape_taigatrail),
    ("galtropa.ru",              scrape_galtropa),
    ("sambatrail.ru",            scrape_sambatrail),
    ("altai-trail.ru",           scrape_altai_trail),
    ("wildsiberia.ru/wild-peak", scrape_wildpeak),
    ("wildsiberia.ru",           scrape_wildsiberia),
    ("city-trail.ru",            scrape_city_trail),
    ("run2kremlins.ru",          scrape_run2kremlins),
    ("paris-running.ru",         scrape_paris_running),
    ("donspacetrail.tilda.ws",   scrape_donspacetrail),
    ("ultra.irunclub.ru",        scrape_taganay_ultra),
    ("trail1.ru",                scrape_trail1),
    ("norilsktrail.ru",          scrape_norilsktrail),
    ("edge-ultra.ru",            scrape_edge_ultra),
    ("okarivertrail.ru",         scrape_okarivertrail),
    ("reg.russiarunning.com",    scrape_russiarunning),
    ("toplist.run",              scrape_toplist),
    ("бег40.рф",                 scrape_beg40),
    ("забег.рф",                 scrape_zabeg_rf),
    ("reg.o-time.ru",            scrape_otime),
    ("goldenultra.ru",           scrape_goldenultra),
    ("vk.com (API)",             scrape_vk),
]

def load_base():
    try:
        with open("events.json", "r", encoding="utf-8") as f:
            return json.load(f).get("events", [])
    except Exception:
        return []


# ─── ДЕДУПЛИКАЦИЯ ────────────────────────────────────────────────────────────

# Слова, которые убираем перед сравнением названий
_NOISE = re.compile(
    r'\b(?:марафон|marathon|полумарафон|half|забег|run|race|старт|start|'
    r'трейл|trail|кросс|cross|пробег|серия|open|cup|кубок|'
    # крупные города — часто добавляются в названия как суффикс
    r'москва|москв\w*|петербург|екатеринбург|новосибирск|казань|'
    r'красноярск|омск|томск|самара|moscow|spb)\b',
    re.I | re.U,
)
_QUOTES = re.compile(u'[\u00ab\u00bb\u201c\u201d\u2018\u2019\u0060\u0027]')
_NONALPHA = re.compile(r'[^а-яёa-z0-9\s]', re.I | re.U)

_YEAR = re.compile(r'\b20\d{2}\b')

# Транслит: русские окончания слов → короткая форма для сравнения
_TRANSLIT_SUFFIXES = [
    (re.compile(r'ический$'), 'ик'),
    (re.compile(r'ческий$'),  'ик'),
    (re.compile(r'овский$'),  'ов'),
    (re.compile(r'евский$'),  'ев'),
    (re.compile(r'ский$'),    ''),
    (re.compile(r'ской$'),    ''),
    (re.compile(r'ного$'),    ''),
    (re.compile(r'ный$'),     ''),
]

def stem(word):
    """Упрощённое стемминг-подобное срезание окончаний."""
    for pat, repl in _TRANSLIT_SUFFIXES:
        w2 = pat.sub(repl, word)
        if w2 != word:
            return w2
    return word

def normalize_name(s):
    """Приводим название к форме для сравнения."""
    s = s.lower()
    s = _YEAR.sub('', s)
    s = _QUOTES.sub('', s)
    s = _NOISE.sub('', s)
    s = _NONALPHA.sub(' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Стемминг каждого слова
    s = ' '.join(stem(w) for w in s.split())
    return s

def normalize_city(s):
    """Нормализуем город: убираем 'г.', скобки, пробелы."""
    s = s.lower().strip()
    s = re.sub(r'^г\.?\s*', '', s)
    s = re.sub(r'\s*\(.*?\)', '', s)
    return s.strip()

def levenshtein(a, b):
    """Расстояние Левенштейна между двумя строками."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Оптимизация: работаем с одной строкой
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j, cb in enumerate(b, 1):
        curr = [j]
        for i, ca in enumerate(a, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[i] + 1, curr[i - 1] + 1, prev[i - 1] + cost))
        prev = curr
    return prev[-1]

def similarity(a, b):
    """
    Схожесть строк от 0.0 до 1.0.
    Комбинирует три метрики:
      1. Расстояние Левенштейна на нормализованных строках
      2. Доля общих токенов (слов) — Жаккар
      3. Бонус если одна строка содержится в другой
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    # 1. Левенштейн
    max_len = max(len(na), len(nb))
    lev_sim = 1.0 - levenshtein(na, nb) / max_len

    # 2. Жаккар по словам
    ta = set(na.split())
    tb = set(nb.split())
    intersection = ta & tb
    union = ta | tb
    jaccard = len(intersection) / len(union) if union else 0.0

    # 3. Бонус за вхождение (одно название — часть другого или все токены одного входят в другое)
    contain_bonus = 0.0
    if na in nb or nb in na:
        contain_bonus = 0.25
    elif ta and tb and (ta <= tb or tb <= ta):
        contain_bonus = 0.25

    score = max(lev_sim, jaccard) + contain_bonus
    return min(score, 1.0)

# Допуск в днях: события в одном городе с похожим названием
# в пределах ±DAYS_WINDOW считаем одним событием
DAYS_WINDOW = 1
SIMILARITY_THRESHOLD = 0.78

def dates_close(d1, d2):
    """Проверяет, что даты отличаются не более чем на DAYS_WINDOW дней."""
    try:
        from datetime import date as _date
        a = _date.fromisoformat(d1)
        b = _date.fromisoformat(d2)
        return abs((a - b).days) <= DAYS_WINDOW
    except Exception:
        return d1 == d2

def is_duplicate(candidate, existing_list):
    """
    Возвращает True, если кандидат является дубликатом
    хотя бы одного события из existing_list.

    Считаем дубликатом если:
      - города совпадают (нечётко)
      - даты совпадают или отличаются на 1 день
      - названия похожи на SIMILARITY_THRESHOLD+
    """
    c_city = normalize_city(candidate.get("city", ""))
    c_date = candidate.get("date", "")
    c_name = candidate.get("name", "")

    for e in existing_list:
        e_city = normalize_city(e.get("city", ""))
        e_date = e.get("date", "")

        # Города должны совпасть (или хотя бы один — пустой/«россия»)
        city_match = (
            c_city == e_city
            or not c_city or not e_city
            or c_city in e_city or e_city in c_city
        )
        if not city_match:
            continue

        if not dates_close(c_date, e_date):
            continue

        sim = similarity(c_name, e.get("name", ""))
        if sim >= SIMILARITY_THRESHOLD:
            return True

    return False

def pick_better(candidate, existing_list):
    """
    Из двух дубликатов выбирает «лучший»:
    предпочитаем запись с большим количеством заполненных полей.
    """
    for e in existing_list:
        if not dates_close(candidate.get("date",""), e.get("date","")):
            continue
        if normalize_city(candidate.get("city","")) != normalize_city(e.get("city","")):
            continue
        if similarity(candidate.get("name",""), e.get("name","")) >= SIMILARITY_THRESHOLD:
            # Если у кандидата больше данных — обновляем поля существующего
            for field in ("distances", "region", "url"):
                if candidate.get(field) and not e.get(field):
                    e[field] = candidate[field]
            return True
    return False


def merge(base, scraped):
    """
    Объединяет базовые события с новыми из парсинга.
    - Удаляет прошедшие события
    - Добавляет новые, которые не являются дубликатами
    - Обогащает существующие записи (дистанции, URL) из новых источников
    - Логирует отброшенные дубликаты
    """
    active = [e for e in base if e.get("date", "") >= TODAY]
    next_id = max((e.get("id", 0) for e in active), default=0) + 1

    added = 0
    enriched = 0
    skipped = 0

    for candidate in scraped:
        if candidate is None:
            continue
        if not candidate.get("date") or not is_future(candidate["date"]):
            continue

        if pick_better(candidate, active):
            # Дубликат — но возможно обогатили поля
            enriched += 1
            skipped += 1
            continue

        if is_duplicate(candidate, active):
            skipped += 1
            continue

        candidate["id"] = next_id
        next_id += 1
        active.append(candidate)
        added += 1

    print(f"  Добавлено новых: {added}, обогащено: {enriched}, отброшено дублей: {skipped}")

    active.sort(key=lambda x: x.get("date", ""))
    return active

def main():
    ts = datetime.utcnow().isoformat()
    print(f"=== Обновление events.json [{ts}] ===\n")

    base = load_base()
    print(f"Базовых событий: {len(base)}\n")
    print(f"Запускаем {len(SOURCES)} источников:\n")

    scraped = []
    for label, fn in SOURCES:
        try:
            result = fn()
            scraped.extend(result)
            print(f"    → {label}: {len(result)} событий")
        except Exception as e:
            print(f"    [FAIL] {label}: {e}")
        time.sleep(1)

    print(f"\nВсего кандидатов из парсинга: {len(scraped)}")
    merged = merge(base, scraped)
    print(f"Итого в базе после объединения: {len(merged)}")

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "events": merged,
        }, f, ensure_ascii=False, indent=2)

    print("\n=== Готово ===")

if __name__ == "__main__":
    main()