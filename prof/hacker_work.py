import discord
from discord.ui import View, Select
import random
from ranking import add_rating_points  # Импортируем функцию работы с рейтингом
from asyncio import sleep

class HackerGameView(View):
    def __init__(self, user, channel, db_cursor, db_connection, bot):
        super().__init__(timeout=None)
        self.user = user
        self.channel = channel
        self.db_cursor = db_cursor
        self.db_connection = db_connection
        self.bot = bot  # Store the bot instance
        self.victim = None
        self.score = 0
        self.success_chance = 0.1
        self.game_active = False
        self.remaining_time = 30  # Общее время на игру теперь 20 секунд

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
            f"Игра началась! Цель: {self.victim['name']}. У вас есть {self.remaining_time} секунд, чтобы решить как можно больше примеров.")

        # Start the game timer using the bot's event loop
        self.bot_task = self.bot.loop.create_task(self.game_timer())  # Use self.bot here
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
                await self.channel.send(f"Правильно! Шанс взлома увеличен на 5%. Текущий шанс: {self.success_chance:.0%}")
            else:
                self.success_chance -= 0.1
                if self.success_chance < 0:
                    self.success_chance = 0
                await self.channel.send(f"Неправильно! Шанс взлома уменьшен на 10%. Текущий шанс: {self.success_chance:.0%}")

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
            self.db_cursor.execute("UPDATE users SET money = money - ? WHERE id = ?", (stolen_money, self.victim['id']))
            self.db_cursor.execute("UPDATE users SET money = money + ? WHERE id = ?", (stolen_money, self.user.id))
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
            await self.channel.send(f"Взлом успешен! Вы украли {stolen_money} монет у {self.victim['name']}.")
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

# Assuming this is in your main bot class or cog
async def start_hacker_job(user, guild, db_cursor, db_connection, bot):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await guild.create_text_channel(f"хакер {user.name}", overwrites=overwrites)

    # Pass the bot instance when creating the view
    view = HackerGameView(user, channel, db_cursor, db_connection, bot)
    await view.select_victim()
