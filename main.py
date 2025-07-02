import os
import json
from google.oauth2 import service_account
import telebot
import gspread
import schedule
import time
import threading
from datetime import datetime, timedelta
from telebot import types
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # отключаем GUI backend, чтобы не было предупреждений
from io import BytesIO

# === Настройки ===
TOKEN = "7575822751:AAFH-T5Ik-A5rjIqeWYPH4vspETCSfJyEpA"
bot = telebot.TeleBot(TOKEN)

# === Доступ к Google Sheets через переменную окружения GOOGLE_KEY ===
google_key = os.getenv("GOOGLE_KEY")
if not google_key:
    raise Exception("GOOGLE_KEY переменная окружения не найдена")

keyfile_dict = json.loads(google_key)
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(keyfile_dict, scopes=scope)
client = gspread.authorize(creds)
# === Добавляем глобальные переменные ===
staff_data = []
schedule_data = []

# === Функция обновления кэша из таблиц ===
def update_cache():
    global staff_data, schedule_data
    try:
        spreadsheet = client.open("График сотрудников")
        staff_data = spreadsheet.worksheet("Сотрудники").get_all_records()
        schedule_data = spreadsheet.worksheet("График").get_all_records()
        print("🔄 Данные успешно обновлены из Google Sheets.")
        print("👥 Сотрудники:", staff_data)
        print("📋 График:", schedule_data)
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении данных: {e}")


# === Первичная загрузка данных при запуске ===
update_cache()

# === Автоматическое обновление каждые 5 минут ===
schedule.every(5).minutes.do(update_cache)

@bot.message_handler(commands=['start'])
@bot.message_handler(commands=['start'])
def start_auth(message):
    print("🧪 Вызван /start")
    print("📩 Весь message.json:", message.json)
    tg_id = str(message.from_user.id)

    # ✅ Правильный способ получить start-параметр из ссылки
    try:
        param = message.json.get('start_param')  # именно так приходят аргументы из deep-link
    except:
        param = None

    # 🎯 Если это чек-ин по ссылке
    if param == 'checkin':
        handle_checkin(message)
        return

    # 🎫 Обычная авторизация
    for row in staff_data:
        if str(row['Телеграм ID']).strip() == tg_id:
            name = row['Имя сотрудника']
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("📅 Мои смены на неделю"),
                       types.KeyboardButton("📋 Общее расписание"))
            bot.send_message(message.chat.id, f"✅ Добро пожаловать, {name}!", reply_markup=markup)
            return
    bot.send_message(message.chat.id, "❌ Доступ запрещён. Сообщите свой Telegram ID управляющему.")



# === /getid команда ===
@bot.message_handler(commands=['getid'])
def send_user_id(message):
    bot.reply_to(message, f"Ваш Telegram ID: {message.from_user.id}\nСообщите его управляющему для доступа к боту.")

# === 💡 Новая функция: обработка чек-ина ===
def handle_checkin(message):
    tg_id = str(message.from_user.id)
    now = datetime.now()
    today_str = now.strftime('%d.%m')
    time_str = now.strftime('%H:%M')

    # Поиск сотрудника по Telegram ID
    user = next((row for row in staff_data if str(row['Телеграм ID']).strip() == tg_id), None)
    if not user:
        bot.send_message(message.chat.id, "❌ Вы не зарегистрированы в системе.")
        return

    name = user['Имя сотрудника']

    try:
        spreadsheet = client.open("График сотрудников")
        sheet = spreadsheet.worksheet("Чек-ины")

        # Опоздание: если позже 11:00
        late = now.hour > 11 or (now.hour == 11 and now.minute > 0)
        status = "✅ Вовремя" if not late else "❌ Опоздание"

        row = [today_str, time_str, name, tg_id, status]
        sheet.append_row(row, value_input_option='USER_ENTERED')

        if late:
            last_row = len(sheet.get_all_values())
            sheet.format(f'E{last_row}', {
                "backgroundColor": {"red": 1, "green": 0.8, "blue": 0.8}
            })

        bot.send_message(message.chat.id, f"📍 Отметка получена: {time_str}\n{name}, спасибо!")
    except Exception as e:
        print(f"❗ Ошибка при чек-ине: {e}")
        bot.send_message(message.chat.id, "⚠️ Не удалось записать чек-ин.")


# === Меню кнопок ===
@bot.message_handler(commands=['menu'])
def _menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📅 Мои смены на неделю"),
               types.KeyboardButton("📋 Общее расписание"))
    bot.send_message(message.chat.id, "Выбери нужную опцию:", reply_markup=markup)

# === Мои смены ===
@bot.message_handler(func=lambda msg: msg.text == "📅 Мои смены на неделю")
def show_week_schedule(message):
    tg_id = str(message.from_user.id)

    # Поиск сотрудника
    name = next((row['Имя сотрудника'] for row in staff_data if str(row['Телеграм ID']).strip() == tg_id), None)
    if not name:
        bot.send_message(message.chat.id, "❌ Вы не зарегистрированы в системе.")
        return

    # Формируем список смен на неделю
    today = datetime.now()
    week_dates = [(today + timedelta(days=i)).strftime('%d.%m') for i in range(7)]

    df = pd.DataFrame(schedule_data)

    # Нормализуем имена и даты
    df['Имя сотрудника'] = df['Имя сотрудника'].astype(str).str.strip().str.lower()
    df['Дата'] = df['Дата'].astype(str).str.strip()
    df['Дата'] = df['Дата'].apply(lambda x: x.zfill(5) if '.' in x else x)def normalize_date(d):
    try:
        parts = d.strip().split(".")
        if len(parts) == 2:
            day, month = parts
            return f"{int(day):02d}.{int(month):02d}"
        else:
            return d
    except:
        return d  # если что-то пойдёт не так — оставим как есть

    df['Дата'] = df['Дата'].astype(str).apply(normalize_date)


    name_normalized = name.strip().lower()
    shifts = df[(df['Имя сотрудника'] == name_normalized) & (df['Дата'].isin(week_dates))]



    # 🔍 Отладочные принты
    print("👤 Имя из staff_data:", repr(name))
    print("🧾 Все имена из графика:", df['Имя сотрудника'].unique())
    print("📆 Неделя:", week_dates)
    print("🔎 Совпавшие смены:", shifts)


    # Ответ пользователю
    if shifts.empty:
        bot.send_message(message.chat.id, "📭 У тебя нет смен на ближайшую неделю.")
    else:
        text = "📅 Твои смены на неделю:\n\n"
        for _, row in shifts.iterrows():
            text += f"📆 {row['Дата']} — {row['Заведение']}, {row['Должность']} ({row['Время смены']})\n"
        bot.send_message(message.chat.id, text)


# === Общее расписание (картинка) ===
@bot.message_handler(func=lambda message: message.text == "📋 Общее расписание")
def full_schedule_image(message):
    if not schedule_data:
        bot.send_message(message.chat.id, "❌ Расписание недоступно.")
        return

    today = datetime.now()
    end_date = today + timedelta(days=30)
    filtered = []

    for row in schedule_data:
        try:
            row_date_str = str(row['Дата']).strip()
            if row_date_str.isdigit() and len(row_date_str) <= 2:
                row_date_str = f"{row_date_str.zfill(2)}.{today.month:02d}"

            date_obj = datetime.strptime(row_date_str, '%d.%m').replace(year=today.year)
            if today.date() <= date_obj.date() <= end_date.date():
                filtered.append({
                    'Дата': row['Дата'],
                    'Имя': row['Имя сотрудника'],
                    'Заведение': row.get('Заведение', ''),
                    'Должность': row.get('Должность', ''),
                    'Время': row['Время смены']
                })
        except Exception as e:
            print(f"Ошибка при обработке строки: {e}")
            continue

    if not filtered:
        bot.send_message(message.chat.id, "❌ Расписание пустое.")
        return

    df = pd.DataFrame(filtered)
    fig, ax = plt.subplots(figsize=(12, 0.6 * len(df)))
    ax.axis('off')
    table = ax.table(cellText=df.values, colLabels=df.columns, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)

    # Цветовая заливка "Бакир" и "Пицца"
    for i, row in df.iterrows():
        place = str(row['Заведение'])
        color = '#FFE4B5' if 'Бакир' in place else '#FFC0CB' if 'Пицца' in place else None
        if color:
            table[(i + 1, 2)].set_facecolor(color)

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)

    try:
        bot.send_photo(message.chat.id, buf, caption="📋 Общее расписание на месяц")
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ Ошибка при отправке изображения.")
        print(f"Ошибка при отправке фото: {e}")

    plt.close()


# === Напоминания о сменах ===
def send_reminders():
    print("⏰ Проверка напоминаний: функция запущена.")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d.%m')

    for row in schedule_data:
        if str(row['Дата']).strip() == tomorrow:
            name = row['Имя сотрудника'].strip()
            for staff in staff_data:
                if staff['Имя сотрудника'].strip() == name:
                    tg_id = staff['Телеграм ID']
                    try:
                        bot.send_message(int(tg_id),
                                         f"📅 Напоминание: у тебя завтра смена!\n"
                                         f"🏢 Заведение: {row.get('Заведение', '—')}\n"
                                         f"👔 Должность: {row.get('Должность', '—')}\n"
                                         f"🕘 Время: {row['Время смены']}")
                    except Exception as e:
                        print(f"❗ Ошибка при отправке {name}: {e}")
                    break


# Планировщик
schedule.every().day.at("10:00").do(send_reminders)
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)
threading.Thread(target=run_scheduler).start()

from flask import Flask, request

app = Flask(__name__)

@app.route(f"/{TOKEN}", methods=["POST"])
def receive_update():
    print("✅ Получен апдейт от Telegram")
    update = telebot.types.Update.de_json(request.data.decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Бот работает", 200

if __name__ == "__main__":
    bot.remove_webhook()
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    print("Установка вебхука:", webhook_url)
    bot.set_webhook(url=webhook_url)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
