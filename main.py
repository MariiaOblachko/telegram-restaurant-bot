import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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
TOKEN = '7575822751:AAFH-T5Ik-A5rjIqeWYPH4vspETCSfJyEpA'
bot = telebot.TeleBot(TOKEN)
KEY_PATH = 'bot-key.json'

# === Доступ к Google Sheets ===
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_PATH, scope)
client = gspread.authorize(creds)

# === Команда /start ===
from telebot import types


@bot.message_handler(commands=['start'])
def start_auth(message):
    tg_id = str(message.from_user.id)

    # Получаем данные сотрудников
    sheet = client.open("График сотрудников").worksheet("Сотрудники")
    all_data = sheet.get_all_records()

    for row in all_data:
        if str(row['Телеграм ID']).strip() == tg_id:
            name = row['Имя сотрудника']

            # ⌨️ Создаём клавиатуру
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            btn1 = types.KeyboardButton("📅 Мои смены на неделю")
            btn2 = types.KeyboardButton("📋 Общее расписание")
            markup.add(btn1, btn2)

            # Отправляем приветствие с кнопками
            bot.send_message(message.chat.id,
                             f"✅ Добро пожаловать, {name}!",
                             reply_markup=markup)
            return

    bot.send_message(
        message.chat.id,
        "❌ Доступ запрещён. Сообщите свой Telegram ID управляющему.")


# === Команда /getid ===
@bot.message_handler(commands=['getid'])
def send_user_id(message):
    user_id = message.from_user.id
    bot.reply_to(
        message,
        f"Ваш Telegram ID: {user_id}\nСообщите его управляющему для доступа к боту."
    )


# === Меню кнопок ===
@bot.message_handler(commands=['menu'])
def show_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("\ud83d\udcc5 Мои смены на неделю")
    btn2 = types.KeyboardButton("\ud83d\udccb Общее расписание")
    markup.add(btn1, btn2)
    bot.send_message(message.chat.id,
                     "Выбери нужную опцию:",
                     reply_markup=markup)


# === Мои смены ===
@bot.message_handler(
    func=lambda message: message.text == "\ud83d\udcc5 Мои смены на неделю")
def my_schedule(message):
    tg_id = str(message.from_user.id)
    staff_sheet = client.worksheet("Сотрудники")
    schedule_sheet = client.worksheet("График")
    staff_data = staff_sheet.get_all_records()
    name = None
    for row in staff_data:
        if str(row['Телеграм ID']).strip() == tg_id:
            name = row['Имя сотрудника'].strip()
            break

    if not name:
        bot.send_message(message.chat.id,
                         "❌ Вы не зарегистрированы в системе.")
        return

    today = datetime.now()
    end_date = today + timedelta(days=7)
    schedule_data = schedule_sheet.get_all_records()
    msg = f"\ud83d\udcc5 Твои смены на {today.strftime('%d.%m')}–{end_date.strftime('%d.%m')}:\n\n"
    found = False

    for row in schedule_data:
        try:
            date_obj = datetime.strptime(row['Дата'], '%d.%m.%Y')
        except:
            continue
        if name == row['Имя сотрудника'].strip(
        ) and today <= date_obj <= end_date:
            found = True
            msg += (
                f"\ud83d\udcc6 {row['Дата']} | \ud83d\udd58 {row['Время смены']} | "
                f"\ud83c\udfe2 {row.get('Заведение', '—')} | \ud83d\udcbc {row.get('Должность', '—')}\n"
            )

    if not found:
        msg = "✅ У тебя нет смен на ближайшие 7 дней."

    bot.send_message(message.chat.id, msg)


# === Общее расписание (картинка) ===
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
            row_date = row['Дата']
            row_date_str = str(row_date).strip()

            # Обработка даты в формате "20" (число)
            if row_date_str.isdigit() and len(row_date_str) <= 2:
                row_date_str = f"{row_date_str.zfill(2)}.{today.month:02d}"

            try:
                date_obj = datetime.strptime(row_date_str, '%d.%m')
                date_obj = date_obj.replace(year=today.year)
            except Exception as e:
                print(f"Ошибка при разборе даты '{row_date_str}': {e}")
                continue

            date_obj = date_obj.replace(year=today.year)

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
    table = ax.table(cellText=df.values,
                     colLabels=df.columns,
                     loc='center',
                     cellLoc='center')

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)

    # Заливка по столбцу "Заведение"
    for i, row in df.iterrows():
        place = str(row['Заведение']).strip()
        color = None
        if 'Бакир' in place:
            color = '#FFE4B5'  # светло-оранжевый
        elif 'Пицца' in place:
            color = '#FFC0CB'  # розовый

        if color:
            table[(i + 1, 2)].set_facecolor(color)  # колонка "Заведение" — индекс 2

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)

    try:
        bot.send_photo(message.chat.id, buf, caption="📋 Общее расписание на месяц")
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ Ошибка при отправке изображения.")
        print(f"Ошибка при отправке фото: {e}")

    plt.close()





# === Напоминание о сменах ===
# 🔔 Напоминания
def send_reminders():
    print("⏰ Проверка напоминаний: функция запущена.")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d.%m')

    # Открываем таблицу
    spreadsheet = client.open("График сотрудников")

    # Подключаемся к листам
    schedule_sheet = spreadsheet.worksheet("График")
    schedule_data = schedule_sheet.get_all_records()

    staff_sheet = spreadsheet.worksheet("Сотрудники")
    staff_data = staff_sheet.get_all_records()

    for row in schedule_data:
        if str(row['Дата']).strip() == tomorrow:
            name = row['Имя сотрудника'].strip()
            shift_time = row['Время смены']

            for staff in staff_data:
                if staff['Имя сотрудника'].strip() == name:
                    tg_id = staff['Телеграм ID']
                    try:
                        bot.send_message(
                            int(tg_id),
                            f"📅 Напоминание: у тебя завтра смена!\n"
                            f"🏢 Заведение: {row.get('Заведение', '—')}\n"
                            f"👔 Должность: {row.get('Должность', '—')}\n"
                            f"🕘 Время: {shift_time}")
                    except Exception as e:
                        print(f"❗ Ошибка при отправке {name}: {e}")
                    break


# Планировщик
schedule.every().day.at("10:00").do(send_reminders)  # для теста


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)


threading.Thread(target=run_scheduler).start()
from datetime import datetime, timedelta
import pandas as pd


# Обработка кнопки "Мои смены на неделю"
@bot.message_handler(func=lambda msg: msg.text == "📅 Мои смены на неделю")
def show_week_schedule(message):
    tg_id = str(message.from_user.id)

    # Получаем имя сотрудника по ID
    staff_sheet = client.open("График сотрудников").worksheet("Сотрудники")
    staff_data = staff_sheet.get_all_records()

    name = None
    for staff in staff_data:
        if str(staff['Телеграм ID']).strip() == tg_id:
            name = staff['Имя сотрудника']
            break

    if not name:
        bot.send_message(message.chat.id, "❌ Доступ запрещён.")
        return

    # Получаем смены на неделю
    schedule_sheet = client.open("График сотрудников").worksheet("График")
    schedule_data = pd.DataFrame(schedule_sheet.get_all_records())

    today = datetime.now()
    week_dates = [(today + timedelta(days=i)).strftime('%d.%m')
                  for i in range(7)]
    shifts = schedule_data[schedule_data['Имя сотрудника'] == name]
    shifts = shifts[shifts['Дата'].astype(str).str[:5].isin(week_dates)]

    if shifts.empty:
        bot.send_message(message.chat.id,
                         "📭 У тебя нет смен на ближайшую неделю.")
    else:
        text = "📅 Твои смены на неделю:\n\n"
        for _, row in shifts.iterrows():
            text += f"📆 {row['Дата']} — {row['Заведение']}, {row['Должность']} ({row['Время смены']})\n"
        bot.send_message(message.chat.id, text)


bot.polling()
