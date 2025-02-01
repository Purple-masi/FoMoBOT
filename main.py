import discord
from discord.ui import Button, View
import yt_dlp
import sqlite3
import importlib.util
import random
from prof.cleaner_work import start_cleaner_job
from prof.hacker_work import start_hacker_job
from discord.ext import commands
from discord import app_commands, ui, Interaction, Embed, File
import asyncio
import time
from card_system import show_card, add_card_to_db, give_card_to_player, delete_card_from_db, remove_card_from_player, try_drop_card, try_drop_case
from prof.whitehacker import start_white_hacker_job

# Укажите ваш токен здесь
token = ""

conn = sqlite3.connect(r"discord.db")
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, nickname TEXT, mention TEXT, money INTEGER, rating_point INTEGER, rating_level INTEGER, last_work_timestamp INTEGER)")
cur.row_factory = sqlite3.Row
conn.commit()


# Подключение к базе данных
cardcon = sqlite3.connect("cards.db")
cardcur = cardcon.cursor()

# Создание таблиц, если они не существуют
cardcur.execute("""
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    description TEXT,
    tags TEXT,
    image_path TEXT,
    rarity TEXT
)
""")
cardcur.execute("""
CREATE TABLE IF NOT EXISTS player_cards (
    player_id INTEGER,
    card_id INTEGER,
    FOREIGN KEY (card_id) REFERENCES cards(id)
)
""")

cardcur.execute("""
CREATE TABLE IF NOT EXISTS marketplace (
    card_id INTEGER,
    player_id INTEGER,
    price INTEGER,
    FOREIGN KEY (card_id) REFERENCES cards(id),
    FOREIGN KEY (player_id) REFERENCES users(id)
)
""")

cardcur.execute("""
    CREATE TABLE IF NOT EXISTS player_cases (
        player_id INTEGER,
        case_id INTEGER,
        PRIMARY KEY (player_id, case_id)
    )
""")

cardcon.commit()


# Создаем бот с командным префиксом и включаем слэш-команды
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Бот {bot.user.name} готов к работе!")
    activity = discord.Activity(type=discord.ActivityType.listening, name="Дотерская Общага 2")
    await bot.change_presence(status=discord.Status.dnd, activity=activity)

    try:
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} команд.")
    except Exception as e:
        print(f"Ошибка при синхронизации команд: {e}")

# Отправка приветственного сообщения новым пользователям
@bot.event
async def on_member_join(member):
    # Добавление записи в базу данных
    cur.execute(f"SELECT id FROM users WHERE id={member.id}")
    if cur.fetchone() is None:
        cur.execute(
            f"INSERT INTO users (id, nickname, mention, money, rating) VALUES ({member.id}, '{member.name}', '<@{member.id}>', 1000, 0)"
        )
        conn.commit()

    # Получение роли "житак общаги"
    role_name = "житак общаги"
    guild = member.guild  # Получаем сервер, к которому присоединился участник
    role = discord.utils.get(guild.roles, name=role_name)  # Ищем роль по имени

    # Выдача роли
    if role:
        await member.add_roles(role)
        print(f"Роль '{role_name}' выдана участнику {member.name}.")
    else:
        print(f"Роль '{role_name}' не найдена на сервере {guild.name}.")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Добавляем случайную карту с шансом 0,3%
    await try_drop_card(message, cardcur, cardcon)
    await try_drop_case(message,cardcur,cardcon)

    # Дальше идёт обработка других команд
    await bot.process_commands(message)

# Команда для регистрации всех участников на сервере
@bot.tree.command(name="register_all", description="Зарегистрировать всех участников сервера в базе данных")
async def register_all(interaction: discord.Interaction):
    guild = interaction.guild  # Получаем сервер (гильдию)
    if not guild:
        await interaction.response.send_message("Не удалось получить информацию о сервере.", ephemeral=True)
        return

    new_users = 0
    # Используем асинхронный цикл для получения участников
    async for member in guild.fetch_members():
        cur.execute(f"SELECT id FROM users WHERE id={member.id}")
        if cur.fetchone() is None:  # Если участник не зарегистрирован
            cur.execute(
                f"INSERT INTO users (id, nickname, mention, money, rating_point, rating_level) VALUES ({member.id}, '{member.name}', '<@{member.id}>', 1000, 0, 1)"
            )
            new_users += 1

    conn.commit()

    if new_users > 0:
        await interaction.response.send_message(f"Зарегистрировано {new_users} новых пользователей.", ephemeral=True)
    else:
        await interaction.response.send_message("Все участники уже зарегистрированы.", ephemeral=True)


@bot.tree.command(name="profile", description="Посмотреть профиль участника")
@app_commands.describe(user="Пользователь, чей профиль вы хотите посмотреть")
async def profile(interaction: discord.Interaction, user: discord.User = None):
    # Если не указан другой пользователь, показываем профиль текущего пользователя
    if not user:
        user = interaction.user

    # Получаем данные пользователя из базы данных
    cur.execute(f"SELECT money, rating_point, rating_level, stolen_money FROM users WHERE id={user.id}")
    result = cur.fetchone()

    # Получаем последний полученный кейс пользователя
    cardcur.execute(
        """
        SELECT cases.id, cases.name, cases.description, cases.image_path, cases.contents
        FROM cases
        JOIN player_cases ON cases.id = player_cases.case_id
        WHERE player_cases.player_id = ?
        """, (user.id,)
    )

    cases = [
        {"id": row[0], "name": row[1], "description": row[2], "image_path": row[3], "contents": row[4]} for row in
        cardcur.fetchall()
    ]

    last_case_name = cases[0]["name"] if cases else "Нету"

    if result:
        money = result[0]
        rating_point = result[1]
        rating_level = result[2]
        stolen_money = result[3]

        # Рассчитываем опыт до следующего уровня
        experience_needed = 100 + (rating_level * 20)
        experience_to_next_level = experience_needed - rating_point

        # Получаем картинку профиля пользователя
        avatar_url = user.avatar.url if user.avatar else user.default_avatar.url

        # Создаём Embed для отображения профиля
        embed = Embed(title=f"Профиль {user.name}", description=f"Никнейм: {user.name}", color=discord.Color.blue())
        embed.set_thumbnail(url=avatar_url)
        embed.add_field(name="Уровень", value=rating_level, inline=False)
        embed.add_field(name="Опыт до следующего уровня", value=f"{experience_to_next_level} опыта", inline=False)
        embed.add_field(name="Деньги", value=f"{money} монет", inline=False)
        if stolen_money > 0:
            embed.add_field(name="Недавние кражи", value=f"Украл {stolen_money} монет", inline=False)
        else:
            embed.add_field(name="Недавние кражи", value=f"Нету", inline=False)
        embed.add_field(name="Случайный кейс", value=last_case_name, inline=False)


        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # Если пользователь не найден в базе данных
        await interaction.response.send_message(f"Пользователь {user.name} не зарегистрирован в системе.", ephemeral=True)


@bot.tree.command(name="work", description="Выберите профессию для заработка денег")
async def work(interaction: discord.Interaction):
    # Получаем данные пользователя
    cur.execute("SELECT money, rating_point, rating_level, last_work_timestamp FROM users WHERE id = ?",
                (interaction.user.id,))
    result = cur.fetchone()

    if not result:
        await interaction.response.send_message("Вы не зарегистрированы в системе. Используйте команду /balance.",
                                                ephemeral=True)
        return

    money, points, level, last_work_timestamp = result

    # Проверяем, если last_work_timestamp отсутствует (None), задаем начальное значение
    if last_work_timestamp is None:
        last_work_timestamp = 0

    # Check cooldown (24 hours)
    current_time = int(time.time())
    cooldown_time = 2 * 60 * 60  # 24 hours in seconds
    time_diff = current_time - last_work_timestamp

    if time_diff < cooldown_time:
        remaining_time = cooldown_time - time_diff
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        await interaction.response.send_message(f"Вы можете использовать команду снова через {hours}ч {minutes}м.",
                                                ephemeral=True)
        return

    # Define available professions
    professions = {
        "Уборщик": 0,
        "Хакер": 10,
        "Белый хакер": 30,
        "Писатель": 50
    }

    options = [
        discord.SelectOption(label=job, description=f"Требуется рейтинг: {req_rating}", value=job)
        for job, req_rating in professions.items()
        if level >= req_rating
    ]

    if not options:
        await interaction.response.send_message("У вас недостаточно рейтинга для выбора профессии.", ephemeral=True)
        return

    # Create a dropdown for profession selection
    class ProfessionDropdown(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="Выберите профессию",
                min_values=1,
                max_values=1,
                options=options
            )

        async def callback(self, interaction: discord.Interaction):
            selected_profession = self.values[0]

            if selected_profession == "Уборщик":
                # Обновление времени последней работы
                cur.execute(
                    "UPDATE users SET last_work_timestamp = ? WHERE id = ?", (current_time, interaction.user.id))
                conn.commit()

                # Запуск мини-игры для уборщика
                try:
                    await start_cleaner_job(interaction.user, interaction.guild, cur, conn)
                    await interaction.response.send_message(
                        f"Вы выбрали профессию '{selected_profession}'! Ваша работа началась.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Ошибка при запуске работы: {e}", ephemeral=True)
                    print(e)
            elif selected_profession == "Хакер":
                # Обновление времени последней работы
                cur.execute(
                    "UPDATE users SET last_work_timestamp = ? WHERE id = ?", (current_time, interaction.user.id))
                conn.commit()

                # Запуск мини-игры для хакера
                try:
                    await start_hacker_job(interaction.user, interaction.guild, cur, conn, bot)
                    await interaction.response.send_message(
                        f"Вы выбрали профессию '{selected_profession}'! Ваша работа началась.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Ошибка при запуске работы: {e}", ephemeral=True)
                    print(e)
            elif selected_profession == "Белый хакер":
                # Обновление времени последней работы
                cur.execute(
                    "UPDATE users SET last_work_timestamp = ? WHERE id = ?", (current_time, interaction.user.id))
                conn.commit()

                # Запуск мини-игры для хакера
                try:
                    await start_white_hacker_job(interaction.user, interaction.guild, cur, conn, bot)
                    await interaction.response.send_message(
                        f"Вы выбрали профессию '{selected_profession}'! Ваша работа началась.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Ошибка при запуске работы: {e}", ephemeral=True)
                    print(e)
            else:
                # Для остальных профессий загружается модуль из соответствующего файла
                file_path = f"prof/{selected_profession}.py"

                try:
                    spec = importlib.util.spec_from_file_location("profession", file_path)
                    profession_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(profession_module)

                    # Call the `execute` function from the selected profession file
                    earn_amount = profession_module.execute()

                    # Update the user's money and last work timestamp
                    cur.execute(
                        "UPDATE users SET money = money + ?, last_work_timestamp = ? WHERE id = ?",
                        (earn_amount, current_time, interaction.user.id))
                    conn.commit()

                    await interaction.response.send_message(f"Вы заработали {earn_amount} монет как {selected_profession}!",
                                                            ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Ошибка при выполнении работы: {e}", ephemeral=True)

            # Удаляем представление (выпадающий список)
            self.disabled = True
            # Попробуем обновить сообщение без ошибки
            await interaction.followup.edit_message(interaction.message.id, view=None)

    class ProfessionView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(ProfessionDropdown())

    await interaction.response.send_message("Выберите профессию для работы:", view=ProfessionView(), ephemeral=True)

# Команда для очистки чата на определённое количество сообщений
@bot.tree.command(name="clear", description="Очистить чат на определённое количество сообщений")
@app_commands.describe(amount="Количество сообщений для удаления")
async def clear(interaction: discord.Interaction, amount: int):
    # Проверяем, что пользователь является модератором (или имеет нужные права)
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("У вас нет прав для выполнения этой команды.", ephemeral=True)
        return

    # Убедимся, что количество сообщений для удаления в пределах разумного
    if amount < 1 or amount > 300:
        await interaction.response.send_message("Пожалуйста, укажите количество сообщений от 1 до 300.", ephemeral=True)
        return

    # Очищаем чат
    try:
        await interaction.channel.purge(limit=amount)
        print(f"очищено {amount} сообщений в {interaction.channel}")
    except discord.Forbidden:
        await interaction.response.send_message("У меня нет прав на удаление сообщений в этом канале.", ephemeral=True)
    except discord.HTTPException:
        await interaction.response.send_message("Произошла ошибка при попытке очистить чат.", ephemeral=True)

# Каторга
class CatorgaView(View):
    def __init__(self, user: discord.Member, shadow_role: discord.Role, resident_role: discord.Role, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.user = user
        self.shadow_role = shadow_role
        self.resident_role = resident_role
        self.channel = channel
        self.progress = 0

    @discord.ui.button(label="Нажми меня", style=discord.ButtonStyle.danger)
    async def press_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.user:
            await interaction.response.send_message("Это не для тебя!", ephemeral=True)
            return

        if random.randint(1, 100) <= 5:  # 5% шанс
            self.progress += 1
            progress_bar = "".join(["🟩" if i < self.progress else "🟥" for i in range(5)])

            if self.progress == 5:
                await interaction.response.edit_message(content="Поздравляю! Вы выбрались с каторги!", view=None)
                print(f"{self.user.name} Выбрался из каторги")
                await self.channel.delete()
                await self.user.remove_roles(self.shadow_role)
                await self.user.add_roles(self.resident_role)
                return

            await interaction.response.edit_message(content=f"Привет. Ты попал на каторгу. Чтобы отсюда выбраться нужно нажать на эту кнопку пока полоска полностью не заполниться. Удачи! \n Прогресс {progress_bar}", view=self)
        else:
            await interaction.response.send_message("Неудача! Попробуйте снова.", ephemeral=True)

@bot.tree.command(name="catorga", description="Отправить пользователя на каторгу")
@app_commands.describe(user="Пользователь, который будет отправлен на каторгу")
async def catorga(interaction: discord.Interaction, user: discord.Member):
    guild = interaction.guild

    # Создаём роль "Теневой Бан"
    shadow_role_name = "Теневой Бан"
    shadow_role = discord.utils.get(guild.roles, name=shadow_role_name)
    if not shadow_role:
        shadow_role = await guild.create_role(name=shadow_role_name, permissions=discord.Permissions(read_messages=False, send_messages=False))

    # Проверяем существование роли "Житак Общаги"
    resident_role_name = "житак общаги"
    resident_role = discord.utils.get(guild.roles, name=resident_role_name)

    # Добавляем роль "Теневой Бан" и удаляем "Житак Общаги"
    await user.add_roles(shadow_role)
    if resident_role:
        await user.remove_roles(resident_role)

    # Создаём отдельный канал
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await guild.create_text_channel(f"каторга-{user.name}", overwrites=overwrites)

    # Отправляем сообщение в канал
    progress_bar = "🟥🟥🟥🟥🟥"
    view = CatorgaView(user, shadow_role, resident_role, channel)
    await channel.send(f"Привет. Ты попал на каторгу. Чтобы отсюда выбраться нужно нажать на эту кнопку пока полоска полностью не заполниться. Удачи! \n Прогресс {progress_bar}", view=view)

    await interaction.response.send_message(f"Пользователь {user.mention} отправлен на каторгу.", ephemeral=True)
    print(f"Отправил на каторгу {user.name}, игроком {interaction.user.name}")


@bot.tree.command(name="card", description="Показать информацию о карточке")
async def card(interaction: Interaction):
    # Передаем подключение к базе данных
    await show_card(interaction, cardcur)

@bot.tree.command(name="addcard", description="Добавить новую карточку в базу данных")
@app_commands.describe(
    name="Имя карточки",
    description="Описание карточки",
    tag="Выберите, доступна ли карточка для продажи (да/нет)",
    image="Название файла изображения",
    rarity="Редкость карты"
)
@app_commands.choices(
    tag=[
        app_commands.Choice(name="Да (для продажи)", value="Для продажи"),
        app_commands.Choice(name="Нет (не для продажи)", value="Не для продажи")],
    rarity=[
        app_commands.Choice(name="Обычная", value="Обычная"),
        app_commands.Choice(name="Редкая", value="Редкая"),
        app_commands.Choice(name="Эпическая", value="Эпическая"),
        app_commands.Choice(name="Легендарная", value="Легендарная"),
        app_commands.Choice(name="Уникальная", value="Уникальная")
    ]
)
async def addcard(interaction: Interaction, name: str, description: str, tag: str, image: str, rarity: str):
    await add_card_to_db(interaction, name, description, tag, image, rarity, cardcur, cardcon)

@bot.tree.command(name="givecard", description="Выдать карточку игроку")
@app_commands.describe(user="Пользователь, которому выдаётся карточка", cardname="Имя карточки")
async def givecard(interaction: discord.Interaction, user: discord.Member, cardname: str):
    await give_card_to_player(interaction, user, cardname, cardcur, cardcon)

@bot.tree.command(name="deletecard", description="Удалить карточку из базы данных по имени")
@app_commands.describe(name="Имя карточки, которую нужно удалить")
async def deletecard(interaction: Interaction, name: str):
    await delete_card_from_db(interaction, name, cardcur, cardcon)

@bot.tree.command(name="removecard", description="Отнять карточку у пользователя")
@app_commands.describe(user="Пользователь, у которого нужно отнять карточку", name="Имя карточки")
async def removecard(interaction: Interaction, user: discord.User, name: str):
    await remove_card_from_player(interaction, user, name, cardcur, cardcon)


from ranking import set_rating


@bot.tree.command(name="set_stats", description="Изменить статистику участника (очки и уровень рейтинга)")
@app_commands.describe(user="Пользователь, чья статистика будет изменена", money="Новые деньги",
                       points="Очки рейтинга", level="Уровень рейтинга")
async def set_stats(interaction: discord.Interaction, user: discord.User, money: int = None,
                    points: int = None, level: int = None):
    # Проверка прав
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("У вас нет прав для выполнения этой команды.", ephemeral=True)
        return

    # Получение текущих значений из базы данных
    cur.execute("SELECT money, rating_point, rating_level FROM users WHERE id = ?", (user.id,))
    result = cur.fetchone()

    if not result:
        await interaction.response.send_message("Этот пользователь не зарегистрирован в системе.", ephemeral=True)
        return

    current_money, current_points, current_level = result

    # Обновление денег
    if money is not None:
        cur.execute("UPDATE users SET money = ? WHERE id = ?", (money, user.id))

    # Обновление рейтинга
    updated_points = points if points is not None else current_points
    updated_level = level if level is not None else current_level

    cur.execute("UPDATE users SET rating_point = ?, rating_level = ? WHERE id = ?", (updated_points, updated_level, user.id))
    while updated_points >= 100 + (updated_level * 20):
        updated_points -= 100 + (updated_level * 20)  # Вычитаем очки до следующего уровня
        updated_level += 1  # Увеличиваем уровень

        # Логируем изменение очков и уровня
        print(f"Новые очки: {updated_points}, Новый Уровень: {updated_level} у {user.name}")

        # Прерывание цикла, если количество очков стало слишком малым
        if updated_points < 0:
            updated_points = 0
            break
    # Сохраняем изменения в базе данных
    cur.execute("UPDATE users SET rating_point = ?, rating_level = ? WHERE id = ?",
                (updated_points, updated_level, interaction.user.id))
    conn.commit()
    conn.commit()

    await interaction.response.send_message(f"Статистика {user.mention} обновлена:\n"
                                            f"Деньги: {money or current_money}\n"
                                            f"Очки рейтинга: {updated_points}\n"
                                            f"Уровень: {updated_level}", ephemeral=True)


from marketplace import MarketView, add_to_market, buy_card

@bot.tree.command(name="market", description="Просмотреть торговую площадку")
async def market(interaction: Interaction):
    # Создаем экземпляр MarketView, передавая нужные параметры
    view = MarketView(market_cur, cardcur)
    await view.send_market(interaction)


@bot.tree.command(name="sell", description="Выставить карточку на продажу")
@app_commands.describe(card_name="Название карточки, которую хотите продать", price="Цена продажи")
async def sell(interaction: Interaction, card_name: str, price: int):
    # Получаем ID карточки по названию
    cardcur.execute("SELECT id FROM cards WHERE name = ?", (card_name,))
    card_data = cardcur.fetchone()

    if not card_data:
        await interaction.response.send_message("Карточка с таким названием не найдена.", ephemeral=True)
        return

    card_id = card_data[0]

    # Проверяем, есть ли карточка у пользователя
    cardcur.execute("SELECT * FROM player_cards WHERE player_id = ? AND card_id = ?", (interaction.user.id, card_id))
    if not cardcur.fetchone():
        await interaction.response.send_message("У вас нет такой карточки.", ephemeral=True)
        return

    # Добавляем карточку на рынок
    await add_to_market(interaction, interaction.user.id, card_name, price, card_cur=cardcur)


# Инициализация баз данных
market_db = sqlite3.connect("marketplace.db")
market_cur = market_db.cursor()

@bot.tree.command(name="buy", description="Купить карточку с торговой площадки")
async def buy(interaction: Interaction, listing_id: int):
    """Купить карточку по ID предложения."""
    # Получаем информацию о балансе покупателя
    cur.execute("SELECT money FROM users WHERE id = ?", (interaction.user.id,))
    buyer_data = cur.fetchone()

    if not buyer_data:
        await interaction.response.send_message("Вы не зарегистрированы в системе.", ephemeral=True)
        return

    buyer_balance = buyer_data[0]
    await buy_card(interaction, interaction.user.id, listing_id, buyer_balance, cardcur, market_cur, market_db)

from card_system import add_case, show_cases, CaseView

@bot.tree.command(name="add_case")
@app_commands.describe(name="Название кейса", description="Описание кейса", image_path="Путь к изображению", card_list="Список карточек через запятую")
async def add_case_command(interaction: Interaction, name: str, description: str, image_path: str, card_list: str):
    await add_case(interaction, name, description, image_path, card_list)

@bot.tree.command(name="case")
async def case_command(interaction: Interaction):
    cur.execute(f'SELECT id FROM users WHERE id={interaction.user.id}')
    user_id = cur.fetchone()
    view = CaseView(cardcur, user_id)
    await show_cases(interaction)

bot.run(token)
