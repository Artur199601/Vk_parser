import telebot
from telebot import types
import requests
import time
import re
import threading
import random

# ================= КОНФИГИ =================
VK_TOKEN = "vk1.a.Noi0OXzVhiNrXq87353MV-GVozMBSR038ye9gRvOt8KMHohEqEB7QpotrwZHwu29TG53wyomh_cQsN5kHepRPzYiDiDGFImdTar-s0W7fbnT_AYawM5XVh72vZHGN1zIwn6Nq7GgN3jfcJ2_iNwJsksqR1QvVX9EdXKkWB2U45-jGjqWoe94jtOPeECeFKy_uAL3ORKTyqAKAMslE6ll1A"
V = "5.131"
BOT_TOKEN = "8667236920:AAGnd47krwDRRAAIY9APdR3FnHl00saR21g"
ADMIN_ID = 1568924415
OUTPUT_FILE = "vk_leads_vertical.txt"

bot = telebot.TeleBot(BOT_TOKEN)

# Ключи для поиска активных объявлений
NEWS_QUERIES = [
    "запись на губы", "косметолог инъекции", "филлер москва", "ботокс акция", 
    "увеличение губ самара", "биоревитализация спб", "контурная пластика",
    "мезотерапия лица", "препараты для косметологов", "нужны модели губы"
]

# ================= ЖЕСТКИЕ ФИЛЬТРЫ (ТВОИ ТРЕБОВАНИЯ) =================
TRASH_WORDS = ["кератин", "ресниц", "брови", "маникюр", "ногти", "шугаринг", "депиляц", "тату", "парикмахер", "визаж", "макияж", "окрашивание", "стриж"]
INJECTION_MARKERS = ["инъекц", "филлер", "ботокс", "губ", "контурн", "мезо", "биоревитализац", "врач", "мед", "шприц", "нитей", "нити", "липолитик", "колю", "скулы", "токсин", "уколы"]

def is_strict_target(text):
    if not text: return False
    text = text.lower()
    
    # 1. Если есть ногти/волосы - сразу в бан
    if any(bad in text for bad in TRASH_WORDS):
        return False
    
    # 2. Обязательно наличие инъекционных слов
    if any(good in text for good in INJECTION_MARKERS):
        return True
        
    return False

# =====================================================================

is_parsing = False
all_leads = []
seen_phones = set()
seen_users = set()

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

def vk_api(method, params, retry=0):
    url = f"https://api.vk.com/method/{method}"
    params.update({"access_token": VK_TOKEN, "v": V})
    try:
        r = requests.get(url, params=params, timeout=20).json()
        if 'error' in r:
            code = r['error']['error_code']
            if code == 9: 
                time.sleep(300) # Бан за скорость - спим 5 мин
                return vk_api(method, params, retry + 1)
            if code == 6: 
                time.sleep(3)
                return vk_api(method, params, retry + 1)
            return None
        return r.get('response')
    except: return None

def get_user_data(user_id):
    res = vk_api("users.get", {"user_ids": user_id, "fields": "status,about,contacts"})
    if res:
        u = res[0]
        full_info = f"{u.get('status', '')} {u.get('about', '')}"
        phone = clean_phone(u.get('mobile_phone')) or extract_phone(full_info)
        return phone, f"{u.get('first_name')} {u.get('last_name')}", full_info
    return None, None, None

def parser_worker(chat_id):
    global is_parsing, all_leads, seen_phones, seen_users
    
    print(f"\n🚀 СНАЙПЕРСКИЙ ПАРСИНГ НОВОСТЕЙ ЗАПУЩЕН...")

    for query in NEWS_QUERIES:
        if not is_parsing: break
        print(f"\n🔎 ИЩУ ПОСТЫ: {query.upper()}")
        
        res = vk_api("newsfeed.search", {"q": query, "count": 200})
        if not res or 'items' not in res: continue

        posts = res['items']
        for post in posts:
            if not is_parsing: break
            
            author_id = post.get('owner_id')
            if not author_id or author_id < 0 or author_id in seen_users:
                continue
            
            post_text = post.get('text', '')
            
            # СТРОЖАЙШАЯ ПРОВЕРКА ТЕКСТА ПОСТА
            if not is_strict_target(post_text):
                continue

            seen_users.add(author_id)
            phone = extract_phone(post_text)
            
            if not phone:
                time.sleep(1.2)
                phone, name, about = get_user_data(author_id)
                # Проверяем профиль, если в посте было мало инфы
                if not is_strict_target(about) and not phone:
                    continue
            else:
                _, name, _ = get_user_data(author_id)

            if phone and phone not in seen_phones:
                seen_phones.add(phone)
                name = name or "Инъекционист"
                all_leads.append((phone, name, post_text[:100], "Живой пост"))
                print(f"      🎯 ЦЕЛЬ ЗАХВАЧЕНА: {phone} | {name}")
                
                if len(all_leads) % 10 == 0:
                    bot.send_message(chat_id, f"🎯 В базе {len(all_leads)} чистых инъекционистов!")
            
            time.sleep(random.uniform(2, 4))

    is_parsing = False
    bot.send_message(chat_id, f"✅ Сбор завершен! Итог: {len(all_leads)} идеальных лидов.")

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("▶️ Старт", "🛑 Стоп")
        markup.row("📊 Статистика", "💾 Выгрузить базу")
        bot.send_message(message.chat.id, "Снайпер на позиции. Мусор не пройдет.", reply_markup=markup)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.from_user.id != ADMIN_ID: return
    global is_parsing, all_leads
    
    if message.text == "▶️ Старт":
        is_parsing = True
        all_leads.clear()
        seen_phones.clear()
        seen_users.clear()
        bot.send_message(message.chat.id, "🚀 Начинаю зачистку новостей по твоим фильтрам!")
        threading.Thread(target=parser_worker, args=(message.chat.id,)).start()
    elif message.text == "🛑 Стоп":
        is_parsing = False
    elif message.text == "📊 Статистика":
        bot.send_message(message.chat.id, f"📊 Отфильтровано инъекционистов: {len(all_leads)}")
    elif message.text == "💾 Выгрузить базу":
        if not all_leads: return
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for p, n, d, c in all_leads:
                f.write(f"{p} | {n} | {d}\n")
        with open(OUTPUT_FILE, "rb") as f:
            bot.send_document(message.chat.id, f)

if __name__ == "__main__":
    bot.polling(none_stop=True)
