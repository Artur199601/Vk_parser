import telebot
from telebot import types
import requests
import time
import re
import threading

# ================= КОНФИГИ =================
VK_TOKEN = "vk1.a.Noi0OXzVhiNrXq87353MV-GVozMBSR038ye9gRvOt8KMHohEqEB7QpotrwZHwu29TG53wyomh_cQsN5kHepRPzYiDiDGFImdTar-s0W7fbnT_AYawM5XVh72vZHGN1zIwn6Nq7GgN3jfcJ2_iNwJsksqR1QvVX9EdXKkWB2U45-jGjqWoe94jtOPeECeFKy_uAL3ORKTyqAKAMslE6ll1A"
V = "5.131"
BOT_TOKEN = "8667236920:AAGnd47krwDRRAAIY9APdR3FnHl00saR21g"
ADMIN_ID = 1568924415
OUTPUT_FILE = "vk_leads_final.txt"

bot = telebot.TeleBot(BOT_TOKEN)

# Ключи, которые дают максимальный профит
PREFIXES = ["косметолог", "врач косметолог", "увеличение губ", "филлер", "ботокс", "инъекции", "биоревитализация", "мезотерапия", "контурная пластика"]

# Только самый жесткий мусор, чтобы не резать базу
TRASH_WORDS = ["кератин", "ресниц", "бровист", "маникюр", "ногти", "электрик", "авто", "шугаринг", "парикмахер", "опт", "поставщик"]

is_parsing = False
all_leads = []
seen_phones = set()
current_city = "Ожидание..."
processed_cities = 0
total_cities = 0

def get_real_cities():
    """Загружает только реальные города (ТОП-500 СНГ)"""
    cities = {}
    # 1 - РФ, 3 - РБ, 4 - КЗ
    for c_id in [1, 3, 4]:
        url = "https://api.vk.com/method/database.getCities"
        params = {"country_id": c_id, "count": 200, "need_all": 0, "access_token": VK_TOKEN, "v": V}
        try:
            r = requests.get(url, params=params).json()
            for item in r.get('response', {}).get('items', []):
                cities[item['title']] = item['id']
        except: pass
    return cities

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

def vk_api(method, params):
    url = f"https://api.vk.com/method/{method}"
    params.update({"access_token": VK_TOKEN, "v": V})
    try:
        r = requests.get(url, params=params, timeout=10).json()
        if 'error' in r and r['error']['error_code'] == 6:
            time.sleep(1.5)
            return vk_api(method, params)
        return r.get('response')
    except: return None

def get_wall_phone(user_id):
    res = vk_api("wall.get", {"owner_id": user_id, "count": 5})
    if res:
        full_text = " ".join([p.get('text', '') for p in res.get('items', [])])
        return extract_phone(full_text)
    return None

def parser_worker(chat_id):
    global is_parsing, all_leads, seen_phones, current_city, processed_cities, total_cities
    
    cities_list = get_real_cities()
    total_cities = len(cities_list)
    print(f"\n🚀 СТАРТ! Городов к обработке: {total_cities}")

    for city_name, city_id in cities_list.items():
        if not is_parsing: break
        current_city = city_name
        processed_cities += 1
        print(f"🌍 [{processed_cities}/{total_cities}] ГОРОД: {city_name.upper()}")
        
        for q in PREFIXES:
            if not is_parsing: break
            # Две сортировки для обхода лимита 1000
            for sort in [0, 1]:
                res = vk_api("users.search", {"q": q, "city": city_id, "sort": sort, "count": 1000, "fields": "status,about,contacts"})
                if not res: continue
                
                users = res.get('items', [])
                for u in users:
                    if not is_parsing: break
                    text = f"{u.get('status', '')} {u.get('about', '')}"
                    if any(w in text.lower() for w in TRASH_WORDS): continue
                    
                    phone = clean_phone(u.get('mobile_phone')) or extract_phone(text)
                    if not phone:
                        time.sleep(0.5)
                        phone = get_wall_phone(u['id'])
                    
                    if phone and phone not in seen_phones:
                        seen_phones.add(phone)
                        name = f"{u.get('first_name', '')} {u.get('last_name', '')}"
                        all_leads.append((phone, name, text[:150]))
                        print(f"   [+] НАЙДЕН: {phone} | {name}")
                time.sleep(1)

    is_parsing = False
    bot.send_message(chat_id, f"✅ Сбор завершен! Итог: {len(all_leads)} номеров.")

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("▶️ Старт", "🛑 Стоп")
        markup.row("📊 Статистика", "💾 Выгрузить базу")
        bot.send_message(message.chat.id, "Бот готов. Жми Старт.", reply_markup=markup)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.from_user.id != ADMIN_ID: return
    global is_parsing, all_leads
    
    if message.text == "▶️ Старт":
        is_parsing = True
        all_leads.clear()
        seen_phones.clear()
        bot.send_message(message.chat.id, "🚀 Погнали! Все логи в консоли.")
        threading.Thread(target=parser_worker, args=(message.chat.id,)).start()
    elif message.text == "🛑 Стоп":
        is_parsing = False
    elif message.text == "📊 Статистика":
        bot.send_message(message.chat.id, f"📊 Собрано: {len(all_leads)}\nГород: {current_city} ({processed_cities}/{total_cities})")
    elif message.text == "💾 Выгрузить базу":
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for p, n, d in all_leads: f.write(f"{p} | {n} | {d}\n")
        with open(OUTPUT_FILE, "rb") as f: bot.send_document(message.chat.id, f)

if __name__ == "__main__":
    bot.polling(none_stop=True)
