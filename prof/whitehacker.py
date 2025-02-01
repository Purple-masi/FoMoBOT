import discord
from discord.ui import View, Select
import random
from ranking import add_rating_points  # Импортируем функцию работы с рейтингом
from asyncio import sleep

class WhiteHackerGameView(View):
    def __init__(self, user, channel, db_cursor, db_connection, bot):
        super().__init__(timeout=None)
        self.user = user
        self.channel = channel
        self.db_cursor = db_cursor
        self.db_connection = db_connection
        self.bot = bot
        self.hacker = None
        self.score = 0
        self.success_chance = 0.1
        self.game_active = False
        self.remaining_time = 30  # Время на игру

    async def select_hacker(self):
        self.clear_items()
        hackers = []
        self.db_cursor.execute("SELECT id, nickname, hack_success_chance FROM users WHERE stolen_money > 0")
        for row in self.db_cursor.fetchall():
            hacker_id, hacker_name, hack_success_chance = row
            hackers.append((hacker_id, hacker_name, hack_success_chance))

        if not hackers:
            await self.channel.send("Нет доступных хакеров с украденными деньгами.")
            await self.channel.delete()
            return

        hacker_options = [
            discord.SelectOption(label=f"{hacker_name} (Шанс: {hack_success_chance:.0%})", value=str(hacker_id))
            for hacker_id, hacker_name, hack_success_chance in hackers
        ]

        hacker_select = HackerSelect(self, hacker_options)
        self.add_item(hacker_select)

        await self.channel.send("Выберите хакера для возврата украденных денег:", view=self)

    async def start_game(self):
        if not self.hacker:
            await self.channel.send("Вы должны выбрать хакера перед началом игры!", ephemeral=True)
            return

        self.game_active = True
        self.score = 0
        self.success_chance = 0.1
        await self.channel.send(
            f"Игра началась! Ваша цель: {self.hacker['name']}. Вам нужно набрать шанс успеха {self.hacker['success_chance']:.0%} или больше. У вас есть {self.remaining_time} секунд."
        )

        self.bot_task = self.bot.loop.create_task(self.game_timer())
        await self.send_question()

    async def game_timer(self):
        while self.remaining_time > 0 and self.game_active:
            await sleep(1)
            self.remaining_time -= 1

        if self.game_active:
            self.game_active = False
            await self.channel.send("Время вышло! Игра завершена.")
            await self.attempt_retrieve()

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
                await self.channel.send(f"Шанс успешного возврата уменьшен. Текущий шанс: {self.success_chance:.0%}")
                return

            if user_answer == self.current_answer:
                self.score += 1
                self.success_chance += 0.05
                await self.channel.send(f"Правильно! Шанс успешного возврата увеличен. Текущий шанс: {self.success_chance:.0%}")
            else:
                self.success_chance -= 0.1
                if self.success_chance < 0:
                    self.success_chance = 0
                await self.channel.send(f"Неправильно! Шанс успешного возврата уменьшен. Текущий шанс: {self.success_chance:.0%}")

        except Exception as e:
            await self.channel.send(f"Произошла ошибка: {str(e)}")

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

    async def attempt_retrieve(self):
        self.game_active = False
        if self.success_chance >= self.hacker['success_chance']:
            self.db_cursor.execute("SELECT stolen_money FROM users WHERE id = ?", (self.hacker['id'],))
            stolen_money = self.db_cursor.fetchone()[0]
            retrieved_money = stolen_money

            self.db_cursor.execute("UPDATE users SET money = money - ? WHERE id = ?",
                                   (retrieved_money, self.hacker['id']))
            self.db_cursor.execute("UPDATE users SET money = money + ? WHERE id = ?", (retrieved_money, self.user.id))
            self.db_cursor.execute("UPDATE users SET stolen_money = 0 WHERE id = ?", (self.hacker['id'],))
            self.db_connection.commit()
            await self.channel.send(f"Вы успешно вернули {retrieved_money} монет у {self.hacker['name']}!")
        else:
            await self.channel.send("Не удалось превзойти шанс успеха хакера. Попробуйте снова позже.")
        await self.channel.delete()

class HackerSelect(discord.ui.Select):
    def __init__(self, parent_view, options):
        super().__init__(placeholder="Выберите хакера", options=options)
        self.parent_view = parent_view

    async def callback(self, interaction):
        if interaction.user != self.parent_view.user:
            await interaction.response.send_message("Это не для вас!", ephemeral=True)
            return

        hacker_id = int(self.values[0])
        self.parent_view.db_cursor.execute("SELECT nickname, hack_success_chance FROM users WHERE id = ?", (hacker_id,))
        hacker_name, hack_success_chance = self.parent_view.db_cursor.fetchone()
        self.parent_view.hacker = {"id": hacker_id, "name": hacker_name, "success_chance": hack_success_chance}
        await self.parent_view.channel.send(f"Вы выбрали хакера: {hacker_name}.")
        await self.parent_view.start_game()

async def start_white_hacker_job(user, guild, db_cursor, db_connection, bot):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await guild.create_text_channel(f"белый_хакер {user.name}", overwrites=overwrites)
    view = WhiteHackerGameView(user, channel, db_cursor, db_connection, bot)
    await view.select_hacker()