# card_system.py
import sqlite3
import discord
from discord import app_commands, ui
from discord import Interaction, Embed, File

# Подключение к базе данных
cardcon = sqlite3.connect("cards.db")
cardcur = cardcon.cursor()


class CardSelect(ui.Select):
    def __init__(self, options):
        super().__init__(
            placeholder="Выберите карточку...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: Interaction):
        # Получение выбранной карточки
        selected_card = self.values[0]

        # Поиск карточки в базе данных
        cardcur.execute("SELECT name, description, tags, image_path FROM cards WHERE name = ?", (selected_card,))
        result = cardcur.fetchone()

        if not result:
            await interaction.response.send_message(f"Карточка '{selected_card}' не найдена.", ephemeral=True)
            return

        name, description, tags, image_path = result

        # Создание встраиваемого сообщения
        embed = Embed(title=name, description=description, color=0x00ff00)
        embed.add_field(name="Теги", value=tags, inline=False)
        embed.set_image(url=f"attachment://{image_path}")

        with open(f"cardsPNG/{image_path}", "rb") as img_file:
            await interaction.response.send_message(embed=embed, file=File(img_file, filename=image_path), ephemeral=True)


class CardView(ui.View):
    def __init__(self, options):
        super().__init__()
        self.add_item(CardSelect(options))


async def show_card(interaction: Interaction, cardcur):
    # Получение списка карточек у пользователя из базы данных
    cardcur.execute("""
        SELECT cards.name 
        FROM cards
        JOIN player_cards ON cards.id = player_cards.card_id
        WHERE player_cards.player_id = ?
    """, (interaction.user.id,))
    cards = cardcur.fetchall()

    if not cards:
        await interaction.response.send_message("В данный момент у вас нет коллекционных карточек.\nПродолжайте общаться на нашем сервере и вы обязательно получите одну!", ephemeral=True)
        return

    # Создание списка опций для выбора
    options = [discord.SelectOption(label=card[0]) for card in cards]

    # Отправка сообщения с выбором карточки
    await interaction.response.send_message(
        "Выберите карточку из списка:",
        view=CardView(options),
        ephemeral=True
    )

async def add_card_to_db(interaction: Interaction, name: str, description: str, tag: str, image: str, rarity: str, cardcur, cardcon):
    # Добавление карточки с редкостью в базу данных
    try:
        cardcur.execute(
            "INSERT INTO cards (name, description, tags, image_path, rarity) VALUES (?, ?, ?, ?, ?)",
            (name, description, tag, image, rarity)
        )
        cardcon.commit()
        await interaction.response.send_message(f"Карточка '{name}' с тегом '{tag}' и редкостью '{rarity}' успешно добавлена!", ephemeral=True)
        print(f"Карточка '{name}' с тегом '{tag}' и редкостью '{rarity}' успешно добавлена!")
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"Карточка с именем '{name}' уже существует.", ephemeral=True)


async def give_card_to_player(interaction: Interaction, user: discord.Member, cardname: str, cardcur, cardcon):
    # Поиск карточки в базе данных
    cardcur.execute("SELECT id FROM cards WHERE name = ?", (cardname,))
    card = cardcur.fetchone()

    if not card:
        await interaction.response.send_message(f"Карточка с именем '{cardname}' не найдена.", ephemeral=True)
        return

    card_id = card[0]

    # Добавление карточки игроку
    cardcur.execute("INSERT INTO player_cards (player_id, card_id) VALUES (?, ?)", (user.id, card_id))
    cardcon.commit()
    await interaction.response.send_message(f"Карточка '{cardname}' успешно выдана игроку {user.mention}!", ephemeral=True)


async def delete_card_from_db(interaction: Interaction, name: str, cardcur, cardcon):
    # Проверка, существует ли карточка с таким именем
    cardcur.execute("SELECT name FROM cards WHERE name = ?", (name,))
    result = cardcur.fetchone()

    if not result:
        await interaction.response.send_message(f"Карточка с именем '{name}' не найдена.", ephemeral=True)
        return

    # Удаление карточки
    try:
        cardcur.execute("DELETE FROM cards WHERE name = ?", (name,))
        cardcon.commit()
        await interaction.response.send_message(f"Карточка '{name}' успешно удалена!", ephemeral=True)
        print(f"Карточка '{name}' успешно удалена!")
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при удалении карточки: {str(e)}", ephemeral=True)


async def remove_card_from_player(interaction: Interaction, user: discord.User, card_id_or_name: str, cardcur, cardcon):
    # Проверяем, является ли входная переменная числом (ID карточки)
    if card_id_or_name.isdigit():
        card_id = int(card_id_or_name)

        # Проверка, существует ли карточка с таким ID
        cardcur.execute("SELECT id FROM cards WHERE id = ?", (card_id,))
        result = cardcur.fetchone()

        if not result:
            await interaction.response.send_message(f"Карточка с ID '{card_id}' не найдена.", ephemeral=True)
            return

    else:
        name = card_id_or_name

        # Проверка, существует ли карточка с таким названием
        cardcur.execute("SELECT id FROM cards WHERE name = ?", (name,))
        result = cardcur.fetchone()

        if not result:
            await interaction.response.send_message(f"Карточка с именем '{name}' не найдена.", ephemeral=True)
            return

        card_id = result[0]  # Извлекаем ID карточки

    # Проверка, есть ли у пользователя эта карточка по ID
    cardcur.execute("SELECT * FROM player_cards WHERE player_id = ? AND card_id = ?", (user.id, card_id))
    user_card = cardcur.fetchone()

    if not user_card:
        await interaction.response.send_message(
            f"У пользователя '{user.name}' нет карточки с ID '{card_id}' или с именем '{name}'.", ephemeral=True)
        return

    # Удаление карточки у пользователя
    try:
        cardcur.execute("DELETE FROM player_cards WHERE player_id = ? AND card_id = ?", (user.id, card_id))
        cardcon.commit()
        await interaction.response.send_message(
            f"Карточка с ID '{card_id}' ({name}) успешно удалена у пользователя '{user.name}'.", ephemeral=True)
        print(f"Карточка с ID '{card_id}' ({name}) успешно удалена у пользователя '{user.name}'.")
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при удалении карточки: {str(e)}", ephemeral=True)


import random
import discord

# Вероятности для каждой редкости (в процентах)
rarity_chances = {
    "Обычная": 0.7,  # 70% шанс на обычную карту
    "Редкая": 0.2,  # 20% шанс на необычную карту
    "Эпическая": 0.07,  # 7% шанс на редкую карту
    "Легендарная": 0.03,  # 3% шанс на легендарную карту
}

async def try_drop_card(message: discord.Message, cardcur, cardcon):
    # Вероятность выпадения карты при каждом сообщении (например, 10%)
    drop_chance = 0.07  # Это можно настроить по вашему усмотрению

    # Генерация случайного числа от 0 до 1
    if random.random() > drop_chance:
        return  # Если шанс не сработал, выходим из функции

    # Генерация случайного числа от 0 до 1 для определения редкости
    random_roll = random.random()

    # Определение редкости карты на основе случайного числа
    cumulative_chance = 0  # Это накопленная вероятность
    selected_rarity = None
    for rarity, chance in rarity_chances.items():
        cumulative_chance += chance
        if random_roll <= cumulative_chance:
            selected_rarity = rarity
            break

    if not selected_rarity:
        return  # Если случайно ничего не выпало, выходим

    # Составляем запрос на случайную карту с нужной редкостью
    cardcur.execute("""
        SELECT name, description, tags, image_path, rarity 
        FROM cards
        WHERE rarity = ?
    """, (selected_rarity,))
    available_cards = cardcur.fetchall()

    if not available_cards:
        return  # Если карт нет с этой редкостью, выходим

    # Выбираем случайную карту из списка доступных
    card = random.choice(available_cards)

    name, description, tags, image_path, rarity = card

    # Проверяем, есть ли у пользователя уже эта карта
    cardcur.execute("""
        SELECT 1 FROM player_cards
        WHERE player_id = ? AND card_id = (
            SELECT id FROM cards WHERE name = ?
        )
    """, (message.author.id, name))

    if cardcur.fetchone():
        return  # Если карта уже есть у пользователя, не добавляем

    # Получаем URL для изображения
    image_url = f"attachment://{image_path}"

    # Создаем встраиваемое сообщение с карточкой
    embed = discord.Embed(
        title=name,
        description=description,
        color=discord.Color.blue()  # Цвет можно настроить
    )
    embed.add_field(name="Редкость", value=selected_rarity, inline=False)  # Редкость на русском
    embed.add_field(name="Теги", value=tags, inline=False)  # Теги
    embed.set_image(url=image_url)  # Изображение карточки

    # Выводим сообщение о выпадении карты
    await message.channel.send(
        f"Поздравляем, {message.author.mention}! Вы получили новую карту:\n",  # Приветствие пользователю
        embed=embed,
        file=discord.File(f"cardsPNG/{image_path}", filename=image_path)
    )

    # Получаем ID карты
    cardcur.execute("SELECT id FROM cards WHERE name = ?", (name,))
    card_id = cardcur.fetchone()[0]

    # Добавляем карту пользователю
    cardcur.execute("INSERT INTO player_cards (player_id, card_id) VALUES (?, ?)", (message.author.id, card_id))
    cardcon.commit()

    print(
        f"Карточка '{name}' с редкостью '{selected_rarity}' и тегом '{tags}' была добавлена пользователю {message.author.name}.")

async def get_card_by_name(card_name, cardcur):
    cardcur.execute("SELECT * FROM cards WHERE name = ?", (card_name,))
    return cardcur.fetchone()
