import requests
import time
import re

TOKEN = "vk1.a.Noi0OXzVhiNrXq87353MV-GVozMBSR038ye9gRvOt8KMHohEqEB7QpotrwZHwu29TG53wyomh_cQsN5kHepRPzYiDiDGFImdTar-s0W7fbnT_AYawM5XVh72vZHGN1zIwn6Nq7GgN3jfcJ2_iNwJsksqR1QvVX9EdXKkWB2U45-jGjqWoe94jtOPeECeFKy_uAL3ORKTyqAKAMslE6ll1A"
V = "5.131"

KEYWORDS = ["косметолог", "увеличение губ", "филлеры", "контурная пластика", "ботокс"]
CITIES = ["Москва", "Санкт-Петербург", "Самара", "Казань", "Екатеринбург", "Краснодар", "Новосибирск", "Ростов"]
OUTPUT_FILE = "vk_leads.txt"

def clean_phone(phone_str):
    digits = re.sub(r'\D', '', phone_str)
    if len(digits) == 11 and (digits.startswith('79') or digits.startswith('89')):
        return "7" + digits[1:]
    return None

def extract_phone_from_text(text):
    if not text: return None
    match = re.search(r'(?:\+?7|8)[\s\-]?\(?[9]\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', text)
    if match:
        return clean_phone(match.group(0))
    return None

def search_groups(query):
    print(f"[*] Ищу группы: {query}...")
    url = "https://api.vk.com/method/groups.search"
    params = {"q": query, "count": 500, "access_token": TOKEN, "v": V}
    try:
        response = requests.get(url, params=params, timeout=10).json()
        if 'error' in response:
            return []
        items = response.get('response', {}).get('items', [])
        return [str(item['id']) for item in items]
    except Exception:
        return []

def get_group_contacts(group_ids):
    url = "https://api.vk.com/method/groups.getById"
    leads = []
    for i in range(0, len(group_ids), 500):
        chunk = group_ids[i:i+500]
        params = {"group_ids": ",".join(chunk), "fields": "contacts,description,status,city", "access_token": TOKEN, "v": V}
        try:
            response = requests.get(url, params=params, timeout=10).json()
            items = response.get('response', [])
            for group in items:
                name = group.get('name', '')
                link = f"https://vk.com/{group.get('screen_name', '')}"
                phone = None
                contacts = group.get('contacts', [])
                for contact in contacts:
                    if 'phone' in contact and contact['phone']:
                        phone = clean_phone(contact['phone'])
                        if phone: break
                if not phone:
                    desc = group.get('description', '')
                    status = group.get('status', '')
                    phone = extract_phone_from_text(desc + " " + status)
                if phone:
                    leads.append((phone, name, link))
                    print(f"[+] Найден лид: {phone}")
        except Exception:
            pass
        time.sleep(0.4)
    return leads

def main():
    print("[*] БУРОВАЯ УСТАНОВКА ЗАПУЩЕНА!")
    all_leads = set()
    for city in CITIES:
        for keyword in KEYWORDS:
            query = f"{keyword} {city}"
            group_ids = search_groups(query)
            if not group_ids:
                time.sleep(0.5)
                continue
            print(f"[*] Найдено {len(group_ids)} групп. Выкачиваю контакты...")
            leads = get_group_contacts(group_ids)
            for lead in leads:
                all_leads.add(lead)
            time.sleep(0.5)
            
    print(f"[*] Сбор завершен! Уникальных номеров: {len(all_leads)}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for phone, name, link in all_leads:
            f.write(f"{phone} | {name} | {link}\n")
    print(f"[*] Готово! База сохранена в {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
