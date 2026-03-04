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

PREFIXES = ["косметолог", "врач косметолог", "увеличение губ", "филлер", "ботокс", "инъекции", "биоревитализация", "мезотерапия"]

# Список городов (основные центры)
CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов-на-Дону", "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград", "Краснодар", "Саратов", "Тюмень", "Тольятти", "Ижевск", "Барнаул", "Ульяновск", "Иркутск", "Хабаровск", "Махачкала", "Владивосток", "Оренбург", "Томск", "Кемерово", "Набережные Челны", "Липецк", "Тула", "Чебоксары", "Калининград", "Алматы", "Астана", "Шымкент", "Минск", "Гомель"]

TRASH_WORDS = ["кератин", "ресниц", "бровист", "маникюр", "ногти", "шугаринг", "парикмахер"]

is_parsing = False
all_leads = []
seen_phones = set()

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

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

def vk_api_call(method, params, retry=0):
    url = f"https://api.vk.com/method/{method}"
    params = dict(params)
    params.update({"access_token": VK_TOKEN, "v": V})
    try:
        r = requests.get(url, params=params, timeout=15).json()
    except Exception as e:
        print(f"   ❌ ОШИБКА СЕТИ: {e}")
        if retry < 3:
            time.sleep(2)
            return vk_api_call(method, params, retry + 1)
        return None

    if 'error' in r:
        code = r['error'].get('error_code')
        msg = r['error'].get('error_msg', '')
        if code == 6: # Rate limit
            time.sleep(2)
            return vk_api_call(method, params, retry + 1)
        print(f"   ❌ ОШИБКА VK {code}: {msg}")
        return None
    return r.get('response')

def get_wall_phone(user_id):
    res = vk_api_call("wall.get", {"owner_id": user_id, "count": 5})
    if res and 'items' in res:
        full_text = " ".join([p.get('text', '') for p in res['items']])
        return extract_phone(full_text)
    return None

# ================= ОСНОВНОЙ ПАРСЕР =================

def parser_worker(chat_id):
    global is_parsing, all_leads, seen_phones

    print(f"\n🚀 СТАРТ! Городов в списке: {len(CITIES)}")
    
    for city in CITIES:
        if not is_parsing: break

        print(f"\n🌍 ГОРОД: {city.upper()}")
        
        for q_prefix in PREFIXES:
            if not is_parsing: break

            # Две стратегии запроса для каждого города
            base_queries = [q_prefix, f"{q_prefix} {city}"]

            for q in base_queries:
                if not is_parsing: break

                print(f"   🔎 Запрос: '{q}'")
                offset = 0
                max_offset = 300 # Листаем 3 страницы

                while offset <= max_offset and is_parsing:
                    params = {
                        "q": q,
                        "count": 100,
                        "offset": offset,
                        "fields": "status,about,contacts,city,home_town"
                    }
                    res = vk_api_call("users.search", params)
                    if not res or 'items' not in res:
                        print(f"      ⚠️ Пустой ответ для offset {offset}")
                        break

                    users = res['items']
                    print(f"      Найдено в выдаче: {len(users)} чел.")

                    if not users: break

                    for u in users:
                        uid = u.get('id')
                        # 1. Проверка города
                        u_city_dict = u.get('city')
                        u_city_title = u_city_dict.get('title') if isinstance(u_city_dict, dict) else ""
                        u_home = u.get('home_town') or ""
                        
                        status = u.get('status') or ""
                        about = u.get('about') or ""
                        combined = f"{status} {about} {u_home} {u_city_title}".lower()

                        # Строгая проверка: если мы ищем в Самаре, а у чела написано Москва - скипаем
                        if city.lower() not in combined:
                            # Это лог, который ты просил: почему перепрыгивает
                            # print(f"      ⏭ Скип юзера {uid}: не тот город ({u_city_title or u_home or 'не указан'})")
                            continue

                        # 2. Проверка мусора
                        trash_found = [w for w in TRASH_WORDS if w in combined]
                        if trash_found:
                            print(f"      ⏭ Скип юзера {uid}: мусорное слово {trash_found}")
                            continue

                        # 3. Поиск телефона
                        phone = clean_phone(u.get('mobile_phone')) or extract_phone(combined)
                        method = "профиль"

                        if not phone:
                            time.sleep(0.4)
                            phone = get_wall_phone(uid)
                            method = "стена"

                        if phone:
                            if phone not in seen_phones:
                                seen_phones.add(phone)
                                name = f"{u.get('first_name','')} {u.get('last_name','')}"
                                all_leads.append((phone, name, combined[:100], city))
                                print(f"      ✅ НАЙДЕН [{method}]: {phone} | {name}")
                                
                                if len(all_leads) % 10 == 0:
                                    bot.send_message(chat_id, f"📊 Собрано: {len(all_leads)} (сейчас: {city})")
                        else:
                            # Лог: почему не парсит (нет телефона)
                            # print(f"      ℹ️ Юзер {uid}: телефон не найден")
                            pass

                    offset += 100
                    time.sleep(1)

    is_parsing = False
    bot.send_message(chat_id, f"✅ Сбор завершен! Итог: {len(all_leads)} номеров.")

# ================= ИНТЕРФЕЙС =================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id == ADMIN_ID:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("▶️ Старт", "🛑 Стоп")
        markup.row("📊 Статистика", "💾 Выгрузить базу")
        bot.send_message(message.chat.id, "Бот в диагностическом режиме. Жми Старт.", reply_markup=markup)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.from_user.id != ADMIN_ID: return
    global is_parsing, all_leads
    
    if message.text == "▶️ Старт":
        is_parsing = True
        all_leads.clear()
        seen_phones.clear()
        bot.send_message(message.chat.id, "🚀 Поехали! Следи за консолью Termius — там все причины пропусков.")
        threading.Thread(target=parser_worker, args=(message.chat.id,)).start()
    elif message.text == "🛑 Стоп":
        is_parsing = False
    elif message.text == "📊 Статистика":
        bot.send_message(message.chat.id, f"📊 Собрано уникальных: {len(all_leads)}")
    elif message.text == "💾 Выгрузить базу":
        if not all_leads:
            bot.send_message(message.chat.id, "База пуста!")
            return
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            for p, n, d, c in all_leads:
                f.write(f"{p} | {n} | {c} | {d}\n")
        with open(OUTPUT_FILE, "rb") as f:
            bot.send_document(message.chat.id, f)

if __name__ == "__main__":
    bot.polling(none_stop=True)
