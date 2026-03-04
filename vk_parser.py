import telebot
from telebot import types
import requests
import time
import re
import threading
import random
import os

# ================= КОНФИГИ =================
# ВСТАВЬ СЮДА 3-5 ТОКЕНОВ ДЛЯ СКОРОСТИ (Через запятую)
VK_TOKENS = [
    "vk1.a.Noi0OXzVhiNrXq87353MV-GVozMBSR038ye9gRvOt8KMHohEqEB7QpotrwZHwu29TG53wyomh_cQsN5kHepRPzYiDiDGFImdTar-s0W7fbnT_AYawM5XVh72vZHGN1zIwn6Nq7GgN3jfcJ2_iNwJsksqR1QvVX9EdXKkWB2U45-jGjqWoe94jtOPeECeFKy_uAL3ORKTyqAKAMslE6ll1A",
    # "ВТОРОЙ_ТОКЕН_ТУТ",
    # "ТРЕТИЙ_ТОКЕН_ТУТ"
]

V = "5.131"
BOT_TOKEN = "8667236920:AAGnd47krwDRRAAIY9APdR3FnHl00saR21g"
ADMIN_ID = 1568924415
OUTPUT_FILE = "vk_leads_final.txt"
GLOBAL_DB = "all_seen_phones.txt"

bot = telebot.TeleBot(BOT_TOKEN)

# Ключевые слова и Список Городов (расширенный для охвата)
KEYWORDS = ["косметолог", "увеличение губ", "инъекции", "ботокс", "филлер", "биоревитализация", "контурная пластика"]
CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов-на-Дону", "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград", "Краснодар", "Саратов", "Тюмень", "Тольятти", "Ижевск", "Барнаул", "Иркутск", "Хабаровск", "Махачкала", "Владивосток", "Минск", "Алматы", "Астана"]

# ================= ФИЛЬТРЫ =================
TRASH_WORDS = ["кератин", "ресниц", "брови", "маникюр", "ногти", "шугаринг", "депиляц", "тату", "парикмахер", "визаж", "макияж", "окрашивание", "стриж", "логопед", "нутрициолог", "психолог", "гимнастика", "самомассаж"]
KILLER_PHRASES = ["без инъекций", "без уколов", "нет уколам", "против инъекций", "без иглы", "безинъекционная"]
INJECTION_MARKERS = ["губ", "инъекц", "филлер", "ботокс", "укол", "мезо", "биореви", "нити", "пластик", "шприц"]

def is_strict_target(text):
    if not text: return False
    text = text.lower()
    if any(killer in text for killer in KILLER_PHRASES): return False
    if any(bad in text for bad in TRASH_WORDS): return False
    return any(good in text for good in INJECTION_MARKERS)

# ================= СИСТЕМА ТОКЕНОВ =================
token_status = {token: True for token in VK_TOKENS}

def get_active_token():
    active = [t for t, status in token_status.items() if status]
    if not active:
        print("🛑 ВСЕ ТОКЕНЫ В БАНЕ. Сплю 10 минут...")
        time.sleep(600)
        for t in token_status: token_status[t] = True
        return get_active_token()
    return random.choice(active)

def vk_api(method, params, token=None):
    if not token: token = get_active_token()
    url = f"https://api.vk.com/method/{method}"
    params.update({"access_token": token, "v": V})
    try:
        r = requests.get(url, params=params, timeout=15).json()
        if 'error' in r:
            code = r['error']['error_code']
            if code in [6, 9]: # Flood / Too fast
                token_status[token] = False
                print(f"⚠️ Токен {token[:10]}... временно заблокирован. Ротация.")
                return vk_api(method, params)
            return None
        return r.get('response')
    except: return None

# ================= ЛОГИКА СБОРА =================
is_parsing = False
all_leads = []
seen_phones = set()

if os.path.exists(GLOBAL_DB):
    with open(GLOBAL_DB, "r") as f:
        seen_phones = set(line.strip() for line in f)

def save_lead(phone, name, query, text):
    with open(GLOBAL_DB, "a") as f: f.write(f"{phone}\n")
    all_leads.append((phone, name, query, text))

def clean_phone(phone_str):
    if not phone_str: return None
    digits = re.sub(r'\D', '', str(phone_str))
    if len(digits) == 11 and (digits.startswith('7') or digits.startswith('8')):
        return "7" + digits[1:]
    elif len(digits) == 12 and (digits.startswith('375') or digits.startswith('998')):
        return digits
    return None

def extract_phone(text):
    if not text: return None
    match = re.search(r'(?:\+?7|8|375|998)[\s\-]?\(?\d{2,3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', text)
    return clean_phone(match.group(0)) if match else None

def parser_worker(chat_id):
    global is_parsing
    bot.send_message(chat_id, f"🚀 План 5000/день запущен! Работаю с {len(VK_TOKENS)} аккаунтов.")
    
    queries = []
    for city in CITIES:
        for kw in KEYWORDS:
            queries.append(f"{kw} {city}")
    random.shuffle(queries)

    for query in queries:
        if not is_parsing: break
        print(f"🔎 ПРОВЕРКА: {query.upper()}")
        
        # Парсим посты (самая живая база)
        res = vk_api("newsfeed.search", {"q": query, "count": 200})
        if not res or 'items' not in res: continue

        for post in res['items']:
            if not is_parsing: break
            
            p_text = post.get('text', '')
            if not is_strict_target(p_text): continue
            
            phone = extract_phone(p_text)
            author_id = post.get('owner_id')
            
            if not phone and author_id > 0:
                time.sleep(0.5)
                u_res = vk_api("users.get", {"user_ids": author_id, "fields": "contacts,status,about"})
                if u_res:
                    u = u_res[0]
                    u_all = f"{u.get('status','')} {u.get('about','')}"
                    phone = clean_phone(u.get('mobile_phone')) or extract_phone(u_all)
                    if not is_strict_target(u_all) and not phone: continue

            if phone and phone not in seen_phones:
                seen_phones.add(phone)
                save_lead(phone, "Инъекционист", query, p_text[:100])
                print(f"      ✅ НАЙДЕН: {phone}")
                
                if len(all_leads) % 50 == 0:
                    bot.send_message(chat_id, f"📊 Прогресс: {len(all_leads)} новых контактов!")

        time.sleep(random.uniform(1, 2))

    is_parsing = False
    bot.send_message(chat_id, f"✅ Сбор завершен! Новых лидов: {len(all_leads)}")

# ================= ИНТЕРФЕЙС =================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("▶️ Старт", "🛑 Стоп")
        markup.row("📊 Статистика", "💾 Выгрузить базу")
        bot.send_message(message.chat.id, "Запуск промышленного сбора.", reply_markup=markup)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.from_user.id != ADMIN_ID: return
    global is_parsing
    if message.text == "▶️ Старт":
        is_parsing = True
        all_leads.clear()
        threading.Thread(target=parser_worker, args=(message.chat.id,)).start()
    elif message.text == "🛑 Стоп": is_parsing = False
    elif message.text == "📊 Статистика":
        bot.send_message(message.chat.id, f"📊 Новых: {len(all_leads)}\nВсего в базе: {len(seen_phones)}")
    elif message.text == "💾 Выгрузить базу":
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for p, n, q, d in all_leads: f.write(f"{p} | {n} | {q} | {d}\n")
        with open(OUTPUT_FILE, "rb") as f: bot.send_document(message.chat.id, f)

if __name__ == "__main__":
    bot.polling(none_stop=True)
