import discord
from discord.ui import View, Select
import random
from ranking import add_rating_points  # Импортируем функцию работы с рейтингом
from asyncio import sleep


def init_hacker_db(db_cursor, db_connection):
    """
    Проверяет наличие необходимых столбцов в таблице users и, если их нет, добавляет их.
    Колонка hack_success_chance хранит шанс успеха хакера (по умолчанию 0.1),
    а stolen_money – количество украденных средств.
    """
    db_cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in db_cursor.fetchall()]
    if 'hack_success_chance' not in columns:
        db_cursor.execute("ALTER TABLE users ADD COLUMN hack_success_chance REAL DEFAULT 0.1")
    if 'stolen_money' not in columns:
        db_cursor.execute("ALTER TABLE users ADD COLUMN stolen_money INTEGER DEFAULT 0")
    db_connection.commit()


class HackerGameView(View):
    def __init__(self, user, channel, db_cursor, db_connection, bot):
        super().__init__(timeout=None)
        self.user = user
        self.channel = channel
        self.db_cursor = db_cursor
        self.db_connection = db_connection
        self.bot = bot  # Экземпляр бота
        self.victim = None
        self.score = 0
        self.success_chance = 0.1
        self.game_active = False
        self.remaining_time = 30  # Время на игру

    async def select_victim(self):
        self.clear_items()

        victims = []
        self.db_cursor.execute("SELECT id, nickname FROM users WHERE id != ? AND money > 300", (self.user.id,))
        for row in self.db_cursor.fetchall():
            victim_id, victim_name = row
            victims.append((victim_id, victim_name))

        if not victims:
            await self.channel.send("Нет доступных жертв с балансом больше 300.")
            await self.channel.delete()
            return

        victim_options = [
            discord.SelectOption(label=victim_name, value=str(victim_id))
            for victim_id, victim_name in victims
        ]

        victim_select = VictimSelect(self, victim_options)
        self.add_item(victim_select)

        await self.channel.send("Выберите жертву для взлома:", view=self)

    async def start_game(self):
        if not self.victim:
            await self.channel.send("Вы должны выбрать жертву перед началом игры!", ephemeral=True)
            return

        self.game_active = True
        self.score = 0
        self.success_chance = 0.1
        await self.channel.send(
            f"Игра началась! Цель: {self.victim['name']}. У вас есть {self.remaining_time} секунд, чтобы решить как можно больше примеров."
        )

        # Запускаем таймер игры через цикл событий бота
        self.bot_task = self.bot.loop.create_task(self.game_timer())
        await self.send_question()

    async def game_timer(self):
        while self.remaining_time > 0 and self.game_active:
            await sleep(1)
            self.remaining_time -= 1

        if self.game_active:  # Если время истекло, завершаем игру
            self.game_active = False
            await self.channel.send("Время вышло! Игра завершена.")
            await self.attempt_hack()

    async def send_question(self):
        if not self.game_active:
            return

        question, answer = self.generate_question()
        self.current_answer = answer
        await self.channel.send(f"Пример: {question}")

        def check(m):
            return m.author == self.user and m.channel == self.channel

        try:
            msg = await self.bot.wait_for('message', check=check)
            if not self.game_active:
                return

            try:
                user_answer = int(msg.content)
            except ValueError:
                await self.channel.send("Ответ должен быть числом!")
                self.success_chance -= 0.1
                if self.success_chance < 0:
                    self.success_chance = 0
                await self.channel.send(f"Шанс взлома уменьшен на 10%. Текущий шанс: {self.success_chance:.0%}")
                return

            if user_answer == self.current_answer:
                self.score += 1
                self.success_chance += 0.05
                await self.channel.send(
                    f"Правильно! Шанс взлома увеличен на 5%. Текущий шанс: {self.success_chance:.0%}")
            else:
                self.success_chance -= 0.1
                if self.success_chance < 0:
                    self.success_chance = 0
                await self.channel.send(
                    f"Неправильно! Шанс взлома уменьшен на 10%. Текущий шанс: {self.success_chance:.0%}")

        except Exception as e:
            await self.channel.send(f"Произошла ошибка: {str(e)}")
            self.success_chance -= 0.1
            if self.success_chance < 0:
                self.success_chance = 0
            await self.channel.send(f"Шанс взлома уменьшен на 10%. Текущий шанс: {self.success_chance:.0%}")

        if self.game_active:
            await self.send_question()

    def generate_question(self):
        num1 = random.randint(1, 20)
        num2 = random.randint(1, 20)
        operation = random.choice(['+', '-', '*'])
        if operation == '+':
            return f"{num1} + {num2}", num1 + num2
        elif operation == '-':
            return f"{num1} - {num2}", num1 - num2
        elif operation == '*':
            return f"{num1} * {num2}", num1 * num2

    async def attempt_hack(self):
        self.game_active = False
        success = random.random() < self.success_chance
        if success:
            stolen_money = random.randint(50, 200)
            # Вычитаем деньги у жертвы и записываем их как украденные для хакера (то есть для игрока)
            self.db_cursor.execute("UPDATE users SET money = money - ? WHERE id = ?", (stolen_money, self.victim['id']))
            self.db_cursor.execute("UPDATE users SET stolen_money = stolen_money + ? WHERE id = ?",
                                   (stolen_money, self.user.id))
            self.db_cursor.execute("UPDATE users SET money = money + ? WHERE id = ?", (stolen_money, self.user.id))
            self.db_cursor.execute("UPDATE users SET hack_success_chance = ? WHERE id = ?",(self.success_chance, self.user.id))
            self.db_cursor.execute("SELECT rating_point, rating_level FROM users WHERE id = ?", (self.user.id,))
            result = self.db_cursor.fetchone()
            if result:
                current_points, current_level = result
                new_points, new_level = add_rating_points(self.user.id, 20 + (current_level * 10), self.db_cursor,
                                                          self.db_connection)
                while new_points >= 100 + (new_level * 20):
                    new_points -= 100 + (new_level * 20)  # Вычитаем очки до следующего уровня
                    new_level += 1  # Увеличиваем уровень
            self.db_connection.commit()
            await self.channel.send(
                f"Взлом успешен! Вы похитили {stolen_money} монет у {self.victim['name']}.\n"
                f"Сумма накопленных украденных средств: {stolen_money} монет (учтена в вашем профиле)."
            )
        else:
            await self.channel.send("Взлом провален. Попробуйте снова позже.")
        await self.channel.delete()


class VictimSelect(discord.ui.Select):
    def __init__(self, parent_view, options):
        super().__init__(placeholder="Выберите жертву для взлома", options=options)
        self.parent_view = parent_view

    async def callback(self, interaction):
        if interaction.user != self.parent_view.user:
            await interaction.response.send_message("Это не для вас!", ephemeral=True)
            return

        victim_id = int(self.values[0])
        self.parent_view.db_cursor.execute("SELECT nickname FROM users WHERE id = ?", (victim_id,))
        victim_name = self.parent_view.db_cursor.fetchone()[0]
        self.parent_view.victim = {"id": victim_id, "name": victim_name}
        await self.parent_view.channel.send(f"Вы выбрали цель: {victim_name}.")
        await self.parent_view.start_game()


# Функция запуска работы профессии хакера
async def start_hacker_job(user, guild, db_cursor, db_connection, bot):
    # Инициализируем недостающие параметры в БД, если их ещё нет
    init_hacker_db(db_cursor, db_connection)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await guild.create_text_channel(f"хакер {user.name}", overwrites=overwrites)

    view = HackerGameView(user, channel, db_cursor, db_connection, bot)
    await view.select_victim()
