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

CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов-на-Дону", "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград", "Краснодар", "Саратов", "Тюмень", "Тольятти", "Ижевск", "Барнаул", "Ульяновск", "Иркутск", "Хабаровск", "Махачкала", "Владивосток", "Оренбург", "Томск", "Кемерово", "Набережные Челны", "Липецк", "Тула", "Чебоксары", "Калининград", "Ставрополь", "Тверь", "Магнитогорск", "Сочи", "Иваново", "Брянск", "Белгород", "Сургут", "Владимир", "Архангельск", "Калуга", "Смоленск", "Саранск", "Курган", "Подольск", "Вологда", "Орел", "Мурманск", "Тамбов", "Петрозаводск", "Кострома", "Алматы", "Астана", "Шымкент", "Минск", "Гомель"]

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

def get_wall_phone(user_id):
    res = vk_api_call("wall.get", {"owner_id": user_id, "count": 5})
    if res:
        # Проверка на наличие items, так как API может вернуть пустую структуру
        items = res.get('items', [])
        full_text = " ".join([p.get('text', '') for p in items])
        return extract_phone(full_text)
    return None

# ================= ТВОЙ НОВЫЙ КОД (ИНТЕГРИРОВАН) =================

def vk_api_call(method, params, retry=0):
    url = f"https://api.vk.com/method/{method}"
    params = dict(params)
    params.update({"access_token": VK_TOKEN, "v": V})
    try:
        r = requests.get(url, params=params, timeout=15).json()
    except Exception as e:
        print(f"vk_api_call EXCEPTION: {e}")
        if retry < 3:
            time.sleep(1 + retry * 2)
            return vk_api_call(method, params, retry + 1)
        return None

    if 'error' in r:
        code = r['error'].get('error_code')
        msg = r['error'].get('error_msg', '')
        print(f"vk_api_call ERROR {code}: {msg} (method={method} params={params})")
        if code == 6 and retry < 5:
            backoff = 1.5 ** (retry + 1)
            print(f"Rate limit — sleeping {backoff:.1f}s and retrying...")
            time.sleep(backoff + random.uniform(0, 1))
            return vk_api_call(method, params, retry + 1)
        return None
    return r.get('response')

def parser_worker(chat_id):
    global is_parsing, all_leads, seen_phones

    print(f"\n🚀 СТАРТ! Городов в списке: {len(CITIES)}")
    bot.send_message(chat_id, f"🚀 Запуск парсера. Городов: {len(CITIES)}")

    found_since_last_report = 0
    REPORT_EVERY = 10 

    for city in CITIES:
        if not is_parsing:
            print("Парсер остановлен оператором.")
            break

        print(f"\n🌍 ОБРАБАТЫВАЮ ГОРОД: {city}")
        
        for q_prefix in PREFIXES:
            if not is_parsing: break

            base_queries = [q_prefix, f"{q_prefix} {city}"]

            for q in base_queries:
                if not is_parsing: break

                print(f"   🔎 Запрос: '{q}'")
                max_offset = 400
                count = 100
                offset = 0

                while offset <= max_offset and is_parsing:
                    params = {
                        "q": q,
                        "count": count,
                        "offset": offset,
                        "fields": "status,about,contacts,city,home_town"
                    }
                    res = vk_api_call("users.search", params)
                    if not res:
                        print(f"      ⚠️ users.search вернул пустой ответ для q='{q}', offset={offset}.")
                        break

                    users = res.get('items', [])
                    print(f"      найдено {len(users)} пользователей (offset={offset})")

                    if not users:
                        break

                    for u in users:
                        if not is_parsing: break

                        city_title = None
                        if isinstance(u.get('city'), dict):
                            city_title = u['city'].get('title')
                        home_town = u.get('home_town') or ''
                        status = u.get('status') or ''
                        about = u.get('about') or ''
                        combined_text = " ".join([status, about, home_town, city_title or ""])

                        city_match = False
                        if city_title and city.lower() in city_title.lower():
                            city_match = True
                        elif home_town and city.lower() in home_town.lower():
                            city_match = True
                        elif city.lower() in combined_text.lower():
                            city_match = True

                        require_strict_city = (" " in q and city.lower() in q.lower())
                        if require_strict_city and not city_match:
                            continue

                        # Исключение мусора (ногти/волосы)
                        if any(x in combined_text.lower() for x in ["ногт", "кератин", "ресниц", "брови"]): 
                            continue

                        phone = clean_phone(u.get('mobile_phone')) or extract_phone(combined_text)

                        if not phone:
                            time.sleep(0.3)
                            phone = get_wall_phone(u.get('id'))

                        if phone and phone not in seen_phones:
                            seen_phones.add(phone)
                            name = f"{u.get('first_name','')} {u.get('last_name','')}".strip()
                            all_leads.append((phone, name, combined_text[:150], city))
                            found_since_last_report += 1
                            print(f"      ✅ НАЙДЕН: {phone} | {name} | {city}")

                            if found_since_last_report >= REPORT_EVERY:
                                bot.send_message(chat_id, f"📊 Промежуточно собрано: {len(all_leads)}")
                                found_since_last_report = 0

                    time.sleep(1.0 + random.random())
                    offset += count

                time.sleep(0.6 + random.random())

    is_parsing = False
    bot.send_message(chat_id, f"✅ Сбор завершен! Собрано: {len(all_leads)} номеров.")

# ================= ИНТЕРФЕЙС БОТА =================

def get_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("▶️ Старт", "🛑 Стоп")
    markup.row("📊 Статистика", "💾 Выгрузить базу")
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "Бот обновлен. Новая логика поиска активна.", reply_markup=get_keyboard())

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.from_user.id != ADMIN_ID: return
    global is_parsing, all_leads, seen_phones
    
    if message.text == "▶️ Старт":
        is_parsing = True
        all_leads.clear()
        seen_phones.clear()
        bot.send_message(message.chat.id, "🚀 Глобальный сбор запущен. Логи в Termius.")
        threading.Thread(target=parser_worker, args=(message.chat.id,)).start()
    elif message.text == "🛑 Стоп":
        is_parsing = False
        bot.send_message(message.chat.id, f"🛑 Остановка. Собрано: {len(all_leads)}")
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
