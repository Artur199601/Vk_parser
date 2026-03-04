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
OUTPUT_FILE = "vk_leads_vertical.txt"

bot = telebot.TeleBot(BOT_TOKEN)

# МАТРИЦА ЗАПРОСОВ (Только точные инъекционные ключи, убрали голый "ботокс")
PREFIXES = [
    "косметолог", "kosmetolog", "врач косметолог", "увеличение губ", 
    "контурная пластика", "ботулинотерапия", "филлер", "инъекции", 
    "биоревитализация", "мезотерапия", "липолитики"
]

CITY_IDS = {}

# ================= УМНЫЙ ТРОЙНОЙ ФИЛЬТР =================
# Добавили парикмахеров (ботокс волос) и конкурентов (поставщиков)
TRASH_WORDS = [
    "кератин", "ресниц", "бровист", "маникюр", "ногти", "электрик", "авто", "потолк", 
    "одежда", "шугаринг", "депиляц", "тату", "стилист", "парикмахер", "визаж", "макияж",
    "ботокс волос", "ботокс для волос", "окрашивание", "колорист", "стрижк", # Стоп-слова для волос
    "опт", "оптом", "поставщик", "дистрибьютор", "расходник", "магазин" # Стоп-слова конкурентов
]
AESTHETIC_WORDS = ["лазер", "эпиляц", "эстет", "аппаратн", "lpg", "массаж", "чистк", "пилинг"]
INJECTION_WORDS = ["инъекц", "филлер", "ботокс", "губ", "контурн", "мезо", "биоревитализац", "врач", "мед", "шприц", "аугментац", "нитей", "нити", "липолитик", "колю", "скулы", "токсин", "пластик", "препарат", "уколы"]

def is_target_audience(text):
    if not text: return True
    text = text.lower()
    
    # 1. Убиваем парикмахеров, продажников и ноготочки
    for bad in TRASH_WORDS:
        if bad in text: return False

    has_aesthetic = any(a in text for a in AESTHETIC_WORDS)
    has_injection = any(i in text for i in INJECTION_WORDS)

    # 2. Убиваем лазерщиков без уколов
    if has_aesthetic and not has_injection:
        return False

    return True
# ========================================================

is_parsing = False
all_leads = []
seen_phones = set()
last_pulse_count = 0
current_city = "Ожидание..."
processed_cities = 0
total_cities = 0

def load_cities_from_vk():
    cities = {}
    targets = {1: 300, 3: 50, 4: 50} 
    
    for country_id, count in targets.items():
        url = "https://api.vk.com/method/database.getCities"
        params = {"country_id": country_id, "count": count, "need_all": 1, "access_token": VK_TOKEN, "v": V}
        try:
            resp = requests.get(url, params=params, timeout=10).json()
            for item in resp.get('response', {}).get('items', []):
                cities[item['title']] = item['id']
        except Exception:
            pass
        time.sleep(0.5)
    return cities

def clean_human_name(raw_name):
    name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ\s\-]', ' ', raw_name)
    stop_words = ['косметолог', 'врач', 'доктор', 'москва', 'мск', 'спб', 'питер', 'ростов', 'сочи', 'казань', 'краснодар', 'салон', 'клиника', 'студия', 'кабинет', 'эстетист', 'дерматолог', 'медицинский', 'dr', 'doctor']
    words = name.split()
    clean_words = [w for w in words if w.lower() not in stop_words and len(w) > 1]
    final_name = " ".join(clean_words).strip()
    return final_name.title() if final_name else "Косметолог"

def clean_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    if len(digits) == 11 and (digits.startswith('7') or digits.startswith('8')):
        return "7" + digits[1:]
    elif len(digits) == 12 and (digits.startswith('375') or digits.startswith('998')):
        return digits
    return None

def extract_phone_from_text(text):
    if not text: return None
    match = re.search(r'(?:\+?7|8|375|998)[\s\-]?\(?\d{2,3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', text)
    if match: return clean_phone(match.group(0))
    return None

def vk_request(url, params):
    while True:
        try:
            resp = requests.get(url, params=params, timeout=10).json()
            if 'error' in resp:
                err_code = resp['error'].get('error_code')
                if err_code == 6:
                    time.sleep(1.5)
                    continue
                else: return None
            return resp
        except Exception:
            time.sleep(1)
            continue

def check_wall_for_phone(user_id):
    url = "https://api.vk.com/method/wall.get"
    params = {"owner_id": user_id, "count": 4, "access_token": VK_TOKEN, "v": V}
    response = vk_request(url, params)
    if response:
        items = response.get('response', {}).get('items', [])
        return extract_phone_from_text(" ".join([post.get('text', '') for post in items]))
    return None

def parser_worker(chat_id):
    global is_parsing, all_leads, seen_phones, last_pulse_count, current_city, processed_cities, CITY_IDS, total_cities
    
    bot.send_message(chat_id, "⏳ Качаю ТОП-400 городов СНГ...")
    CITY_IDS = load_cities_from_vk()
    total_cities = len(CITY_IDS)
    bot.send_message(chat_id, f"✅ Загружено {total_cities} городов! Запуск матрицы запросов (защита от парикмахеров ВКЛЮЧЕНА).")

    for city_name, city_id in CITY_IDS.items():
        if not is_parsing: break
        current_city = city_name
        processed_cities += 1
        
        for prefix in PREFIXES:
            if not is_parsing: break
            
            for sort_type in [0, 1]:
                if not is_parsing: break
                
                url = "https://api.vk.com/method/users.search"
                params = {
                    "q": prefix, "city": city_id, "sort": sort_type,
                    "count": 1000, "fields": "status,about,contacts,screen_name", 
                    "access_token": VK_TOKEN, "v": V
                }
                
                response = vk_request(url, params)
                if not response: continue
                
                users = response.get('response', {}).get('items', [])
                for user in users:
                    if not is_parsing: break
                    
                    full_text = f"{user.get('first_name', '')} {user.get('last_name', '')} {user.get('status', '')} {user.get('about', '')}"
                    
                    if not is_target_audience(full_text): continue 
                        
                    raw_name = f"{user.get('first_name', '')} {user.get('last_name', '')}"
                    clean_name = clean_human_name(raw_name)
                    
                    desc = f"{user.get('status', '')} {user.get('about', '')}".replace('\n', ' ').strip()
                    if len(desc) > 150: desc = desc[:150] + "..."
                    if not desc: desc = "Нет описания"
                    
                    phone = clean_phone(user.get('mobile_phone', '')) if user.get('mobile_phone') else None
                    if not phone: phone = extract_phone_from_text(full_text)
                    if not phone:
                        time.sleep(0.35) 
                        phone = check_wall_for_phone(user['id'])
                    
                    if phone and phone not in seen_phones:
                        seen_phones.add(phone)
                        all_leads.append((phone, clean_name, desc))
                        
                        if len(all_leads) - last_pulse_count >= 50:
                            last_pulse_count = len(all_leads)
                            bot.send_message(chat_id, f"💓 ПУЛЬС: {len(all_leads)} чистых инъекционистов. Копаю: {current_city}... Файл автосохранен!")
                            
                            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                                for p, n, d in all_leads:
                                    f.write(f"Номер: {p}\nИмя: {n}\nОписание: {d}\n" + "-"*40 + "\n")
                time.sleep(0.5)
            
    if is_parsing:
        is_parsing = False
        bot.send_message(chat_id, f"✅ Глобальный сбор завершен! Идеальных лидов: {len(all_leads)}.")

# ================= ИНТЕРФЕЙС БОТА =================
def get_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(types.KeyboardButton("▶️ Старт"), types.KeyboardButton("🛑 Стоп"))
    markup.row(types.KeyboardButton("📊 Статистика"), types.KeyboardButton("💾 Выгрузить базу"))
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "Привет, Босс. Снайперский прицел наведен.", reply_markup=get_keyboard())

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.from_user.id != ADMIN_ID: return
    global is_parsing, all_leads, seen_phones, last_pulse_count, processed_cities, current_city
    
    if message.text == "▶️ Старт":
        if is_parsing:
            bot.send_message(message.chat.id, "Парсинг уже идет!")
            return
        is_parsing = True
        all_leads = []
        seen_phones.clear()
        last_pulse_count = 0
        processed_cities = 0
        bot.send_message(message.chat.id, "🚀 Погнали! Запущена матрица на 400 городов. Конкуренты и парикмахеры заблокированы.")
        threading.Thread(target=parser_worker, args=(message.chat.id,)).start()
        
    elif message.text == "🛑 Стоп":
        if not is_parsing: return
        is_parsing = False
        bot.send_message(message.chat.id, f"🛑 Остановка... Собрано: {len(all_leads)} номеров.")
        
    elif message.text == "📊 Статистика":
        status = "🟢 В работе" if is_parsing else "🔴 Остановлен"
        bot.send_message(message.chat.id, f"📊 **Live-Статистика:**\n\nСтатус: {status}\nУникальных номеров: **{len(all_leads)}**\nТекущий город: {current_city} ({processed_cities}/{total_cities})", parse_mode="Markdown")
        
    elif message.text == "💾 Выгрузить базу":
        if len(all_leads) == 0: 
            try:
                with open(OUTPUT_FILE, "rb") as f:
                    bot.send_document(message.chat.id, f)
            except:
                bot.send_message(message.chat.id, "База пуста!")
            return
            
        bot.send_message(message.chat.id, "Формирую файл...")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for phone, name, desc in all_leads:
                f.write(f"Номер: {phone}\nИмя: {name}\nОписание: {desc}\n" + "-"*40 + "\n")
        with open(OUTPUT_FILE, "rb") as f:
            bot.send_document(message.chat.id, f)

if __name__ == "__main__":
    bot.polling(none_stop=True)
