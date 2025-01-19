import discord
from discord.ui import View, Button
import random
from asyncio import sleep
from ranking import add_rating_points  # Импортируем функцию работы с рейтингом


class CleanerGameView(View):
    def __init__(self, user, channel, db_cursor, db_connection):
        super().__init__(timeout=None)
        self.user = user
        self.channel = channel
        self.db_cursor = db_cursor
        self.db_connection = db_connection
        self.score = 0
        self.time_left = 10
        self.game_active = False

    async def start_game(self, interaction):
        self.game_active = True
        self.time_left = 10
        self.score = 0
        self.update_buttons()
        await self.channel.send(f"Игра началась! У вас {self.time_left} секунд.", view=self)
        while self.time_left > 0 and self.game_active:
            await sleep(1)
            self.time_left -= 1
            if self.time_left == 0:
                await self.end_game()

    def update_buttons(self):
        self.clear_items()
        poop_button_index = random.randint(0, 7)
        for i in range(8):
            if i == poop_button_index:
                self.add_item(CorrectButton(self))
            else:
                self.add_item(WrongButton(self))

    async def end_game(self):
        self.game_active = False
        earnings = self.score * 5

        # Начисляем деньги
        self.db_cursor.execute("UPDATE users SET money = money + ? WHERE id = ?", (earnings, self.user.id))

        # Добавляем очки рейтинга
        self.db_cursor.execute("SELECT rating_point, rating_level FROM users WHERE id = ?", (self.user.id,))
        result = self.db_cursor.fetchone()
        if result:
            current_points, current_level = result
            new_points, new_level = add_rating_points(self.user.id, 20+(current_level*10), self.db_cursor, self.db_connection)

            while new_points >= 100 + (new_level * 20):
                new_points -= 100 + (new_level * 20)  # Вычитаем очки до следующего уровня
                new_level += 1  # Увеличиваем уровень

                # Логируем изменение очков и уровня
                print(f"Новые очки: {new_points}, Новый Уровень: {new_level} у {self.user.name}")

                # Прерывание цикла, если количество очков стало слишком малым
                if new_points < 0:
                    new_points = 0
                    break

        else:
            new_points, new_level = 5, 0  # Обработать случай, если пользователь отсутствует в базе

        self.db_connection.commit()

        await self.channel.send(
            f"Игра завершена! Вы заработали {earnings} монет, получили 1 очко рейтинга и достигли уровня {new_level}."
        )
        print(
            f"Игра завершена! {self.user.name} заработал {earnings} монет, получил 1 очко рейтинга и достиг уровня {new_level}."
        )
        await self.channel.delete()


class CorrectButton(Button):
    def __init__(self, parent_view):
        super().__init__(style=discord.ButtonStyle.success, emoji="💩")
        self.parent_view = parent_view

    async def callback(self, interaction):
        if interaction.user != self.view.user or not self.view.game_active:
            await interaction.response.send_message("Это не для вас!", ephemeral=True)
            return
        self.parent_view.score += 1
        self.parent_view.update_buttons()
        await interaction.response.edit_message(
            content=f"Счёт: {self.view.score} | Осталось времени: {self.view.time_left} сек.", view=self.view)


class WrongButton(Button):
    def __init__(self, parent_view):
        super().__init__(style=discord.ButtonStyle.primary, emoji="🟦")
        self.parent_view = parent_view

    async def callback(self, interaction):
        if interaction.user != self.view.user or not self.view.game_active:
            await interaction.response.send_message("Это не для вас!", ephemeral=True)
            return
        self.parent_view.time_left = 0
        await self.parent_view.end_game()


class StartGameButton(Button):
    def __init__(self, parent_view):
        super().__init__(style=discord.ButtonStyle.green, label="Начать игру")
        self.parent_view = parent_view

    async def callback(self, interaction):
        if interaction.user != self.parent_view.user:
            await interaction.response.send_message("Это не для вас!", ephemeral=True)
            return
        await self.parent_view.start_game(interaction)


async def start_cleaner_job(user, guild, db_cursor, db_connection):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await guild.create_text_channel(f"рабочее место {user.name}", overwrites=overwrites)
    view = CleanerGameView(user, channel, db_cursor, db_connection)
    view.add_item(StartGameButton(view))
    await channel.send("Добро пожаловать на работу уборщиком! Нажмите кнопку ниже, чтобы начать игру.", view=view)
