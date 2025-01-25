import sqlite3
import random
import os
import discord
from discord.ui import Button, View
from discord.ext import commands


# Функция для добавления кейса в базу данных
def add_case(casename, caseimage, cardnames):
    if not os.path.exists(caseimage):
        return "Ошибка: изображение кейса не найдено."

    # Подключаемся к базе данных
    conn = sqlite3.connect('casesinfo.db')
    cursor = conn.cursor()

    # Создаем таблицы, если они еще не существуют
    cursor.execute('''CREATE TABLE IF NOT EXISTS cases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        casename TEXT,
                        caseimage TEXT,
                        cards TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS player_cases (
                        user_id INTEGER PRIMARY KEY,
                        case_ids TEXT)''')  # case_ids будет хранить ID кейсов для игрока

    # Преобразуем список карточек в строку
    cards = ','.join(cardnames)

    # Вставляем данные о кейсе в таблицу кейсов
    cursor.execute("INSERT INTO cases (casename, caseimage, cards) VALUES (?, ?, ?)",
                   (casename, caseimage, cards))
    conn.commit()

    # Получаем ID вставленного кейса
    case_id = cursor.lastrowid

    # Добавляем кейс в инвентарь первого игрока (по умолчанию)
    cursor.execute("INSERT OR IGNORE INTO player_cases (user_id, case_ids) VALUES (?, ?)",
                   (0, str(case_id)))  # Добавляем кейс для user_id = 0 (пример для теста)
    conn.commit()

    conn.close()

    return f"Кейс '{casename}' добавлен в базу данных."


# Функция для получения всех кейсов
def get_all_cases():
    conn = sqlite3.connect('casesinfo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cases")
    cases = cursor.fetchall()
    conn.close()
    return cases


# Функция для получения эмбеда с кейсом
def create_case_embed(case):
    casename, caseimage, cards = case[1], case[2], case[3].split(',')
    embed = discord.Embed(title=f"Инвентарь: {casename}", description="Выберите действие:")
    embed.set_image(url=caseimage)
    return embed, cards


# Функция для создания кнопок
def create_buttons():
    view = View()
    view.add_item(Button(label="Открыть", custom_id="open_case", style=discord.ButtonStyle.green, row=0))
    view.add_item(Button(label="Влево", custom_id="left_case", style=discord.ButtonStyle.blue, row=1))
    view.add_item(Button(label="Вправо", custom_id="right_case", style=discord.ButtonStyle.blue, row=2))
    return view


# Функция для открытия кейса
def open_case(cases, case_index):
    case = cases[case_index]
    cards = case[3].split(',')
    random_card = random.choice(cards)
    return random_card


# Функция для получения кейсов игрока по его ID
def get_player_cases(user_id):
    conn = sqlite3.connect('casesinfo.db')
    cursor = conn.cursor()
    cursor.execute("SELECT case_ids FROM player_cases WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return list(map(int, result[0].split(',')))
    return []
