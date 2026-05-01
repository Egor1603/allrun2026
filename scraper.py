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
    return re.sub(r'<[^>]+>', ' ', html)

def clean(s):
    return re.sub(r'\s+', ' ', strip_tags(s)).strip()

def make_event(date, name, city, region, distances, etype, url):
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
    """ea-m.org — Европа-Азия Екатеринбург"""
    print("  ea-m.org")
    html = fetch("https://ea-m.org/")
    if not html:
        return []
    events = []
    # Ищем карточки событий
    cards = re.findall(
        r'<(?:article|div|li)[^>]*class="[^"]*event[^"]*"[^>]*>(.*?)</(?:article|div|li)>',
        html, re.S
    )
    if not cards:
        # fallback
        return scrape_generic("https://ea-m.org/", "Екатеринбург",
                               "Свердловская область", "road", "Старт Европа-Азия")
    for card in cards[:10]:
        d = parse_date(card)
        if not d or not is_future(d):
            continue
        name_m = re.search(r'<(?:h[123]|strong|a)[^>]*>([^<]{5,80})</(?:h[123]|strong|a)>', card)
        name = clean(name_m.group(1)) if name_m else "Старт Европа-Азия"
        events.append(make_event(d, name, "Екатеринбург", "Свердловская область",
                                  "", "road", "https://ea-m.org/"))
    return events


def scrape_runsim():
    """runsim.ru — Омские старты"""
    print("  runsim.ru")
    html = fetch("https://runsim.ru/events/")
    if not html:
        return []
    events = []
    # Карточки событий
    items = re.findall(r'<(?:article|div|li)[^>]*>(.*?)</(?:article|div|li)>', html, re.S)
    seen = set()
    for item in items:
        d = parse_date(item)
        if not d or not is_future(d) or d in seen:
            continue
        seen.add(d)
        name_m = re.search(r'<(?:h[1-4]|a|strong)[^>]*>([^<]{5,80})</(?:h[1-4]|a|strong)>', item)
        name = clean(name_m.group(1)) if name_m else "Старт Омск"
        events.append(make_event(d, name, "Омск", "Омская область", "", "road",
                                  "https://runsim.ru/events/"))
    return events[:10]


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


# ─── MERGE & SAVE ────────────────────────────────────────────────────────────

SOURCES = [
    ("krasmarafon.ru",      scrape_krasmarafon),
    ("pushkin-run.ru",      scrape_pushkin_run),
    ("heroleague.ru",       scrape_heroleague),
    ("ea-m.org",            scrape_ea_m),
    ("runsim.ru",           scrape_runsim),
    ("tomskmarathon.ru",    scrape_tomskmarathon),
    ("kazan.run",           scrape_kazan_run),
    ("sib-events.ru",       scrape_sib_events),
    ("wnmarathon.runc.run", scrape_wnmarathon),
    ("moscowhalf.runc.run", scrape_moscowhalf),
    ("springrun.ru",        scrape_springrun),
    ("sportsauce.ru",       scrape_sportsauce),
    ("timerman.org",        scrape_timerman),
    ("topliga.ru/events",   scrape_topliga),
    ("alpmarathon.ru",      scrape_alpmarathon),
    ("myrace.info",         scrape_myrace),
    ("rtra.ru",             scrape_rtra),
    ("skyrunning.ru",       scrape_skyrunning),
    ("vk.com (API)",        scrape_vk),
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
_QUOTES = re.compile(r'[«»""\'`]')
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
