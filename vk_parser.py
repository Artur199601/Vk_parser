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
ADMIN_ID = 1568924415 # Твой ID
OUTPUT_FILE = "vk_leads_clean.txt"

bot = telebot.TeleBot(BOT_TOKEN)

PREFIXES = ["косметолог", "kosmetolog", "cosmetolog", "cosmetologist", "врач косметолог"]
CITIES = ["Москва", "Moscow", "Moskva", "Мск", "Санкт-Петербург", "Spb", "Спб", "Новосибирск", "Екатеринбург", "Казань", "Краснодар", "Нижний Новгород", "Челябинск", "Самара", "Ростов-на-Дону", "Уфа", "Омск", "Красноярск", "Воронеж", "Пермь", "Волгоград", "Сочи", "Тюмень", "Саратов", "Тольятти", "Ижевск", "Барнаул", "Ульяновск", "Иркутск", "Хабаровск", "Махачкала", "Владивосток", "Минск", "Гомель", "Алматы", "Астана", "Ташкент"]
BAD_WORDS = ["кератин", "волос", "ресниц", "брови", "маникюр", "ногти", "электрик", "авто", "потолк", "одежда", "шугаринг", "депиляц", "массаж", "тату", "фото", "визаж", "стилист", "парикмахер", "макияж", "аренда"]

# Глобальные переменные для управления ботом
is_parsing = False
all_leads = []
last_pulse_count = 0

# ============================================

def is_target_audience(text):
    if not text: return True
    text = text.lower()
    for bad in BAD_WORDS:
        if bad in text: return False 
    return True

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

def check_wall_for_phone(user_id):
    url = "https://api.vk.com/method/wall.get"
    params = {"owner_id": user_id, "count": 4, "access_token": VK_TOKEN, "v": V}
    try:
        response = requests.get(url, params=params, timeout=5).json()
        items = response.get('response', {}).get('items', [])
        return extract_phone_from_text(" ".join([post.get('text', '') for post in items]))
    except Exception: return None

def parser_worker(chat_id):
    global is_parsing, all_leads, last_pulse_count
    
    for city in CITIES:
        if not is_parsing: break
        
        for prefix in PREFIXES:
            if not is_parsing: break
            
            query = f"{prefix} {city}"
            url = "https://api.vk.com/method/users.search"
            params = {"q": query, "count": 1000, "fields": "status,about,contacts,screen_name", "access_token": VK_TOKEN, "v": V}
            
            try:
                response = requests.get(url, params=params, timeout=10).json()
                users = response.get('response', {}).get('items', [])
                
                for user in users:
                    if not is_parsing: break
                    
                    full_text = f"{user.get('first_name', '')} {user.get('last_name', '')} {user.get('status', '')} {user.get('about', '')}"
                    if not is_target_audience(full_text): continue 
                        
                    name = f"{user.get('first_name', '')} {user.get('last_name', '')}"
                    
                    # Описание для проверки глазками
                    desc = f"{user.get('status', '')} {user.get('about', '')}".replace('\n', ' ').strip()
                    if len(desc) > 100: desc = desc[:100] + "..."
                    if not desc: desc = "Нет описания"
                    
                    phone = clean_phone(user.get('mobile_phone', '')) if user.get('mobile_phone') else None
                    if not phone: phone = extract_phone_from_text(full_text)
                    if not phone:
                        time.sleep(0.35) 
                        phone = check_wall_for_phone(user['id'])
                    
                    if phone:
                        if not any(phone == lead[0] for lead in all_leads):
                            # Сохраняем ТОЛЬКО Номер, Имя и Описание
                            all_leads.append((phone, name, desc))
                            
                            # Отправка ПУЛЬСА каждые 50 номеров
                            if len(all_leads) - last_pulse_count >= 50:
                                last_pulse_count = len(all_leads)
                                bot.send_message(chat_id, f"💓 ПУЛЬС: Собрано {len(all_leads)} чистых номеров. Работаю дальше...")
                
            except Exception: pass
            time.sleep(0.5)
            
    if is_parsing:
        is_parsing = False
        bot.send_message(chat_id, f"✅ Сбор полностью завершен! Всего найдено: {len(all_leads)} номеров. Жми 'Выгрузить базу'.")

# ================= ИНТЕРФЕЙС БОТА =================

def get_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("▶️ Старт"), types.KeyboardButton("🛑 Стоп"))
    markup.add(types.KeyboardButton("💾 Выгрузить базу"))
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id != ADMIN_ID: return
    bot.send_message(message.chat.id, "Привет, Босс. Буровая установка готова. Жми кнопки.", reply_markup=get_keyboard())

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.from_user.id != ADMIN_ID: return
    global is_parsing, all_leads, last_pulse_count
    
    if message.text == "▶️ Старт":
        if is_parsing:
            bot.send_message(message.chat.id, "Парсинг уже идет!")
            return
        is_parsing = True
        all_leads = []
        last_pulse_count = 0
        bot.send_message(message.chat.id, "🚀 Погнали! Запустил сбор базы. Пришлю пульс через 50 номеров.")
        threading.Thread(target=parser_worker, args=(message.chat.id,)).start()
        
    elif message.text == "🛑 Стоп":
        if not is_parsing:
            bot.send_message(message.chat.id, "Парсер и так стоит.")
            return
        is_parsing = False
        bot.send_message(message.chat.id, f"🛑 Остановка... Собрано: {len(all_leads)} номеров. Можешь выгружать.")
        
    elif message.text == "💾 Выгрузить базу":
        if len(all_leads) == 0:
            bot.send_message(message.chat.id, "База пуста! Сначала запусти парсер.")
            return
            
        bot.send_message(message.chat.id, "Формирую файл...")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for phone, name, desc in all_leads:
                # Записываем в файл только то, что просил: Номер | Имя | Описание
                f.write(f"{phone} | {name} | {desc}\n")
                
        with open(OUTPUT_FILE, "rb") as f:
            bot.send_document(message.chat.id, f)

if __name__ == "__main__":
    print("Бот запущен. Напиши ему /start в Телеграме.")
    bot.polling(none_stop=True)
