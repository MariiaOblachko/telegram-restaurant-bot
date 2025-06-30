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
TOKEN = os.getenv("BOT_TOKEN", "вставь_сюда_свой_токен_если_нужно")
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

# === Команда /start ===
@bot.message_handler(commands=['start'])
def start_auth(message):
    tg_id = str(message.from_user.id)
    sheet = client.open("График сотрудников").worksheet("Сотрудники")
    all_data = sheet.get_all_records()
    for row in all_data:
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

# === Меню кнопок ===
@bot.message_handler(commands=['menu'])
def show_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("📅 Мои смены на неделю"),
               types.KeyboardButton("📋 Общее расписание"))
    bot.send_message(message.chat.id, "Выбери нужную опцию:", reply_markup=markup)

# === Мои смены ===
@bot.message_handler(func=lambda msg: msg.text == "📅 Мои смены на неделю")
def show_week_schedule(message):
    tg_id = str(message.from_user.id)
    staff_sheet = client.open("График сотрудников").worksheet("Сотрудники")
    staff_data = staff_sheet.get_all_records()
    name = next((row['Имя сотрудника'] for row in staff_data if str(row['Телеграм ID']).strip() == tg_id), None)
    if not name:
        bot.send_message(message.chat.id, "❌ Вы не зарегистрированы в системе.")
        return

    schedule_sheet = client.open("График сотрудников").worksheet("График")
    schedule_data = pd.DataFrame(schedule_sheet.get_all_records())
    today = datetime.now()
    week_dates = [(today + timedelta(days=i)).strftime('%d.%m') for i in range(7)]
    shifts = schedule_data[schedule_data['Имя сотрудника'] == name]
    shifts = shifts[shifts['Дата'].astype(str).str[:5].isin(week_dates)]

    if shifts.empty:
        bot.send_message(message.chat.id, "📭 У тебя нет смен на ближайшую неделю.")
    else:
        text = "📅 Твои смены на неделю:\n\n"
        for _, row in shifts.iterrows():
            text += f"📆 {row['Дата']} — {row['Заведение']}, {row['Должность']} ({row['Время смены']})\n"
        bot.send_message(message.chat.id, text)

# === Общее расписание ===
@bot.message_handler(func=lambda message: message.text == "📋 Общее расписание")
def full_schedule_image(message):
    try:
        schedule_sheet = client.open("График сотрудников").worksheet("График")
        schedule_data = schedule_sheet.get_all_records()
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ Не удалось загрузить расписание.")
        print(f"Ошибка при загрузке данных: {e}")
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
    for i, row in df.iterrows():
        color = '#FFE4B5' if 'Бакир' in row['Заведение'] else '#FFC0CB' if 'Пицца' in row['Заведение'] else None
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
    spreadsheet = client.open("График сотрудников")
    schedule_data = spreadsheet.worksheet("График").get_all_records()
    staff_data = spreadsheet.worksheet("Сотрудники").get_all_records()

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

# Старт бота
bot.polling()
