import sqlite3
import discord
from discord import app_commands, ui
from discord import Interaction, Embed, File
import random

discon = sqlite3.connect("discord.db")
discur = discon.cursor()

# Подключение к базе данных
cardcon = sqlite3.connect("cards.db")
cardcur = cardcon.cursor()

# Создание таблицы для кейсов, если она еще не существует
cardcur.execute('''
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    image_path TEXT,
    contents TEXT -- Список карточек через запятую
)
''')
cardcon.commit()

class CaseView(ui.View):
    def __init__(self, cases, user_id):
        super().__init__()
        self.cases = cases
        self.current_index = 0
        self.user_id = user_id

    async def interaction_check(self, interaction: Interaction):
        # Проверка, что взаимодействие исходит от инициатора
        return interaction.user.id == self.user_id

    @ui.button(label="⬅", style=discord.ButtonStyle.primary)
    async def left_button(self, interaction: Interaction, button: ui.Button):
        self.current_index = (self.current_index - 1) % len(self.cases)
        await self.update_embed(interaction)

    @ui.button(label="Открыть", style=discord.ButtonStyle.success)
    async def open_button(self, interaction: Interaction, button: ui.Button):
        button.disabled = True
        await interaction.response.edit_message(view=self)

        case = self.cases[self.current_index]
        await self.open_case(interaction, case)

    @ui.button(label="➡", style=discord.ButtonStyle.primary)
    async def right_button(self, interaction: Interaction, button: ui.Button):
        self.current_index = (self.current_index + 1) % len(self.cases)
        await self.update_embed(interaction)

    async def update_embed(self, interaction: Interaction):
        case = self.cases[self.current_index]
        embed = Embed(
            title=case["name"],
            description=case["description"],
            color=discord.Color.gold()
        )
        embed.set_image(url=f"attachment://{case['image_path']}")

        try:
            with open(f"casesPNG/{case['image_path']}", "rb") as img_file:
                file = File(img_file, filename=case['image_path'])
                await interaction.response.edit_message(
                    embed=embed, attachments=[file], view=self
                )
        except FileNotFoundError:
            await interaction.response.send_message(
                "Ошибка: изображение кейса не найдено.", ephemeral=True
            )

    async def open_case(self, interaction: Interaction, case):
        # Проверка, есть ли кейс у пользователя
        cardcur.execute(
            "SELECT 1 FROM player_cases WHERE player_id = ? AND case_id = ?",
            (interaction.user.id, case["id"])
        )
        if not cardcur.fetchone():
            await interaction.followup.send(
                "У вас нет этого кейса. Пожалуйста, выберите другой кейс.", ephemeral=True
            )
            return

        cards = case["contents"].split(", ")
        random_card = random.choice(cards)

        # Проверка наличия карты в базе данных
        cardcur.execute("SELECT id, name FROM cards WHERE name = ?", (random_card,))
        card = cardcur.fetchone()

        if not card:
            await interaction.followup.send(
                f"Ошибка: карта '{random_card}' не найдена.", ephemeral=True
            )
            return

        card_id, card_name = card
        cardcur.execute(
            "DELETE FROM player_cases WHERE player_id = ? AND case_id = ?",
            (interaction.user.id, case["id"])
        )
        cardcon.commit()

        # Проверка, есть ли карта у пользователя
        cardcur.execute(
            "SELECT 1 FROM player_cards WHERE player_id = ? AND card_id = ?",
            (interaction.user.id, card_id)
        )

        if cardcur.fetchone():
            await interaction.followup.send(
                "Эта карта уже есть у вас. Выдаём вам 50 монет", ephemeral=True
            )
            discur.execute("SELECT money FROM users WHERE id = ?", (interaction.user.id,))
            result = discur.fetchone()

            if result is not None:
                current_money = result[0]
                # Увеличиваем количество монет на 50
                new_money = current_money + 50
                # Обновляем запись в базе данных
                discur.execute("UPDATE users SET money = ? WHERE id = ?", (new_money, interaction.user.id))
                discon.commit()
            else:
                # Если записи пользователя нет, создаем новую
                discur.execute("INSERT INTO users (id, money) VALUES (?, ?)", (interaction.user.id, 50))
                discon.commit()
            cardcur.execute(
                "DELETE FROM player_cases WHERE player_id = ? AND case_id = ?",
                (interaction.user.id, case["id"])
            )
            cardcon.commit()

        else:
            await interaction.followup.send(
                f"Вы открыли кейс и получили карту: {card_name}!", ephemeral=True
            )
            cardcur.execute(
                "INSERT INTO player_cards (player_id, card_id) VALUES (?, ?)",
                (interaction.user.id, card_id)
            )
            cardcon.commit()


async def show_cases(interaction: Interaction):
    """Команда для отображения кейсов пользователя."""
    cardcur.execute(
        """
        SELECT cases.id, cases.name, cases.description, cases.image_path, cases.contents
        FROM cases
        JOIN player_cases ON cases.id = player_cases.case_id
        WHERE player_cases.player_id = ?
        """,
        (interaction.user.id,)
    )

    cases = [
        {"id": row[0], "name": row[1], "description": row[2], "image_path": row[3], "contents": row[4]} for row in cardcur.fetchall()
    ]

    if not cases:
        await interaction.response.send_message(
            "У вас нет доступных кейсов.", ephemeral=True
        )
        return

    first_case = cases[0]

    embed = Embed(
        title=first_case["name"],
        description=first_case["description"],
        color=discord.Color.gold()
    )
    embed.set_image(url=f"attachment://{first_case['image_path']}")

    view = CaseView(cases, interaction.user.id)

    try:
        with open(f"casesPNG/{first_case['image_path']}", "rb") as img_file:
            file = File(img_file, filename=first_case['image_path'])
            await interaction.response.send_message(
                embed=embed,
                file=file,
                view=view, ephemeral=True
            )
    except FileNotFoundError:
        await interaction.response.send_message(
            "Ошибка: изображение первого кейса не найдено.", ephemeral=True
        )


async def add_case(interaction: Interaction, name: str, description: str, image_path: str, card_list: str):
    """Добавление кейса в базу данных."""
    try:
        cardcur.execute(
            "INSERT INTO cases (name, description, image_path, contents) VALUES (?, ?, ?, ?)",
            (name, description, image_path, card_list)
        )
        cardcon.commit()
        await interaction.response.send_message(f"Кейс '{name}' успешно добавлен!", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"Кейс с именем '{name}' уже существует.", ephemeral=True)

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

    # Проверка, есть ли у пользователя эта карточка
    cardcur.execute("SELECT 1 FROM player_cards WHERE player_id = ? AND card_id = ?", (user.id, card_id))
    if cardcur.fetchone():
        await interaction.response.send_message(
            f"У пользователя {user.mention} уже есть карточка '{cardname}'.", ephemeral=True
        )
        return

    # Добавление карточки игроку
    try:
        cardcur.execute("INSERT INTO player_cards (player_id, card_id) VALUES (?, ?)", (user.id, card_id))
        cardcon.commit()
        await interaction.response.send_message(f"Карточка '{cardname}' успешно выдана игроку {user.mention}!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Ошибка при выдаче карточки: {str(e)}", ephemeral=True)



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
# Вероятности для каждой редкости (в процентах)
rarity_chances = {
    "Обычная": 0.7,  # 70% шанс на обычную карту
    "Редкая": 0.2,  # 20% шанс на необычную карту
    "Эпическая": 0.07,  # 7% шанс на редкую карту
    "Легендарная": 0.03,  # 3% шанс на легендарную карту
}

# Шанс выпадения кейса
case_drop_chance = 0.01  # 5% шанс на выпадение кейса

def connect_to_database():
    return sqlite3.connect("cards.db")

async def try_drop_card(message: discord.Message, cardcur, cardcon):
    # Вероятность выпадения карты при каждом сообщении (например, 7%)
    drop_chance = 0.01

    # Генерация случайного числа от 0 до 1
    if random.random() > drop_chance:
        return  # Если шанс не сработал, выходим из функции

    # Генерация случайного числа от 0 до 1 для определения редкости
    random_roll = random.random()

    # Определение редкости карты на основе случайного числа
    cumulative_chance = 0
    selected_rarity = None
    for rarity, chance in rarity_chances.items():
        cumulative_chance += chance
        if random_roll <= cumulative_chance:
            selected_rarity = rarity
            break

    if not selected_rarity:
        return

    # Составляем запрос на случайную карту с нужной редкостью
    cardcur.execute("""
        SELECT name, description, tags, image_path, rarity 
        FROM cards
        WHERE rarity = ?
    """, (selected_rarity,))
    available_cards = cardcur.fetchall()

    if not available_cards:
        return

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
        return

    # Создаем встраиваемое сообщение с карточкой
    embed = discord.Embed(
        title=name,
        description=description,
        color=discord.Color.gold()
    )
    embed.add_field(name="Редкость", value=selected_rarity, inline=False)
    embed.add_field(name="Теги", value=tags, inline=False)
    embed.set_image(url=f"attachment://{image_path}")

    # Отправляем сообщение о выпадении карты
    await message.channel.send(
        f"Поздравляем, {message.author.mention}! Вы получили новую карту:",
        embed=embed,
        file=discord.File(f"cardsPNG/{image_path}", filename=image_path), delete_after=5
    )

    # Получаем ID карты
    cardcur.execute("SELECT id FROM cards WHERE name = ?", (name,))
    card_id = cardcur.fetchone()[0]

    # Добавляем карту пользователю
    cardcur.execute("INSERT INTO player_cards (player_id, card_id) VALUES (?, ?)", (message.author.id, card_id))
    cardcon.commit()

    print(
        f"Карточка '{name}' с редкостью '{selected_rarity}' была добавлена пользователю {message.author.name}.")

async def try_drop_case(message: discord.Message, cardcur, cardcon):
    # Генерация случайного числа от 0 до 1 для проверки шанса выпадения кейса
    if random.random() > case_drop_chance:
        return

    # Составляем запрос для получения случайного кейса
    cardcur.execute("SELECT id, name, description, image_path FROM cases")
    available_cases = cardcur.fetchall()

    if not available_cases:
        return

    # Выбираем случайный кейс
    case = random.choice(available_cases)
    case_id, name, description, image_path = case

    # Проверяем, есть ли у пользователя уже этот кейс
    cardcur.execute("""
        SELECT 1 FROM player_cases
        WHERE player_id = ? AND case_id = ?
    """, (message.author.id, case_id))

    if cardcur.fetchone():
        return

    # Создаем встраиваемое сообщение о выпадении кейса
    embed = discord.Embed(
        title=f"Новый кейс: {name}",
        description=description,
        color=discord.Color.gold()
    )
    embed.set_image(url=f"attachment://{image_path}")

    # Отправляем сообщение о выпадении кейса
    await message.channel.send(
        f"Удача на вашей стороне, {message.author.mention}! Вы получили новый кейс:",
        embed=embed,
        file=discord.File(f"casesPNG/{image_path}", filename=image_path), delete_after=5
    )

    # Добавляем кейс пользователю
    cardcur.execute("INSERT INTO player_cases (player_id, case_id) VALUES (?, ?)", (message.author.id, case_id))
    cardcon.commit()

    print(f"Кейс '{name}' был добавлен пользователю {message.author.name}.")


async def get_card_by_name(card_name, cardcur):
    cardcur.execute("SELECT * FROM cards WHERE name = ?", (card_name,))
    return cardcur.fetchone()

