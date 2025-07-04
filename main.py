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
def start_auth(message):
    tg_id = str(message.from_user.id)

    # Правильно получаем параметр
    args = message.text.split(maxsplit=1)
    param = args[1] if len(args) > 1 else None

    print(f"💬 /start получен от {tg_id}, param: {param}")

    if param and 'checkout' in param.lower():
        print("📤 Вызван handle_checkout()")
        handle_checkout(message)
        return

    if param and 'checkin' in param.lower():
        print("📥 Вызван handle_checkin()")
        handle_checkin(message)
        return

    # Если это обычный /start без параметров — авторизация
    



    #чекаут
def handle_checkout(message):
    print("🔁 handle_checkout() вызван")

    tg_id = str(message.from_user.id)
    now = datetime.now()
    time_str = now.strftime('%H:%M')

    # Найдём пользователя
    user = next((row for row in staff_data if str(row['Телеграм ID']).strip() == tg_id), None)
    if not user:
        bot.send_message(message.chat.id, "❌ Вы не зарегистрированы в системе.")
        return

    name = user['Имя сотрудника']

        # 🧠 остальной код поиска строки и записи чекаута ниже

    try:
        spreadsheet = client.open("График сотрудников")
        sheet = spreadsheet.worksheet("Чек-ины")
        values = sheet.get_all_values()
        print("📋 Последние строки в 'Чек-ины':", values[-5:])

        today_str = now.strftime('%d.%m')
        target_row_index = None
        for i in range(len(values) - 1, 0, -1):
            if (
                len(values[i]) >= 4 and
                values[i][0].strip() == today_str and
                values[i][3].strip() == tg_id and
                (len(values[i]) < 7 or not values[i][6].strip())
            ):
                target_row_index = i + 1
                break

        if not target_row_index:
            bot.send_message(message.chat.id, "⚠️ Не найден чек-ин для выхода.")
            return

        sheet.update_cell(target_row_index, 7, time_str)  # G колонка
# Сравниваем с окончанием смены
# Найдём запись в расписании
today_str = now.strftime('%d.%m')
user_schedule = next((row for row in schedule_data if row['Имя сотрудника'].strip().lower() == name.strip().lower() and row['Дата'].strip() == today_str), None)

if user_schedule:
    end_time_str = str(user_schedule.get("Время смены", "")).split("-")[-1].strip()
    try:
        planned_end = datetime.strptime(end_time_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        diff = (now - planned_end).total_seconds() // 60
        if diff > 0:
            status = f"⏰ Вышел позже на {int(diff)} мин."
        elif diff < 0:
            status = f"⏳ Вышел раньше на {abs(int(diff))} мин."
        else:
            status = "✅ Вышел вовремя."
    except:
        status = "⚠️ Время окончания смены указано неверно."
else:
    status = "❓ Не найдено время смены."

bot.send_message(message.chat.id, f"👋 До свидания, {name}!\nЧек-аут: {time_str}\n{status}")
        print(f"✅ Чек-аут записан для {name}, строка {target_row_index}")

    except Exception as e:
        print(f"❗ Ошибка при чекауте: {e}")
        bot.send_message(message.chat.id, "⚠️ Не удалось записать чек-аут.")

    


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
    planned_start = now.replace(hour=11, minute=0, second=0, microsecond=0)
delay = now - planned_start
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
        late = delay.total_seconds() > 0
        if late:
            mins = int(delay.total_seconds() // 60)
            status = f"❌ Опоздание на {mins} мин."
        else:
            status = "✅ Вовремя"


        row = [today_str, time_str, name, tg_id, status]
        sheet.append_row(row, value_input_option='USER_ENTERED')

        if late:
            last_row = len(sheet.get_all_values())
            sheet.format(f'E{last_row}', {
                "backgroundColor": {"red": 1, "green": 0.8, "blue": 0.8}
            })

        bot.send_message(message.chat.id, f"📍 Отметка получена: {time_str}\n{name}, спасибо!\n{status}")
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

    # === Сначала определяем нормализатор даты ===
    def normalize_date(d):
        try:
            parts = d.strip().split(".")
            if len(parts) == 2:
                day, month = parts
                return f"{int(day):02d}.{int(month):02d}"
            else:
                return d
        except:
            return d  # если что-то пойдёт не так — оставим как есть

    # === Применяем нормализацию ===
    df['Имя сотрудника'] = df['Имя сотрудника'].astype(str).str.strip().str.lower()
    df['Дата'] = df['Дата'].astype(str).str.strip()
    df['Дата'] = df['Дата'].apply(normalize_date)

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
