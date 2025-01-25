import sqlite3
from discord import Embed, Interaction

conn = sqlite3.connect(r"discord.db")
cur = conn.cursor()

# Инициализация базы данных
market_db = sqlite3.connect("marketplace.db")
market_cur = market_db.cursor()

# Создание таблицы для торговли, если она не существует
market_cur.execute("""
CREATE TABLE IF NOT EXISTS marketplace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER,
    card_id INTEGER,
    price INTEGER,
    FOREIGN KEY (card_id) REFERENCES cards(id)
)
""")
market_db.commit()

from discord.ui import View, Button
from discord import ButtonStyle, Interaction, Embed

class MarketView(View):
    def __init__(self, market_cur, card_cur):
        super().__init__(timeout=None)
        self.market_cur = market_cur
        self.card_cur = card_cur

        # Создаем кнопку "Обновить"
        self.refresh_button = Button(label="🔄", style=ButtonStyle.primary)
        self.refresh_button.callback = self.refresh_market
        self.add_item(self.refresh_button)

    async def send_market(self, interaction: Interaction):
        """Отправить начальное сообщение с торговой площадкой."""
        self.market_cur.execute("SELECT id, seller_id, card_id, price FROM marketplace")
        listings = self.market_cur.fetchall()

        embed = Embed(title="Торговая площадка", description="Доступные карточки для покупки", color=0x00ff00)

        if not listings:
            embed.description = "На торговой площадке сейчас нет предложений."
        else:
            for listing_id, seller_id, card_id, price in listings:
                self.card_cur.execute("SELECT name, rarity FROM cards WHERE id = ?", (card_id,))
                card_data = self.card_cur.fetchone()
                if card_data:
                    card_name, card_rarity = card_data
                    embed.add_field(
                        name=f"ID: {listing_id} - {card_name} ({card_rarity})",
                        value=f"Продавец: <@{seller_id}>\nЦена: {price} монет",
                        inline=False
                    )

        await interaction.response.send_message(embed=embed, view=self, ephemeral=True)

    async def refresh_market(self, interaction: Interaction):
        """Обработчик кнопки обновления."""
        self.market_cur.execute("SELECT id, seller_id, card_id, price FROM marketplace")
        listings = self.market_cur.fetchall()

        embed = Embed(title="Торговая площадка", description="Доступные карточки для покупки", color=0x00ff00)

        if not listings:
            embed.description = "На торговой площадке сейчас нет предложений."
        else:
            for listing_id, seller_id, card_id, price in listings:
                self.card_cur.execute("SELECT name, rarity FROM cards WHERE id = ?", (card_id,))
                card_data = self.card_cur.fetchone()
                if card_data:
                    card_name, card_rarity = card_data
                    embed.add_field(
                        name=f"ID: {listing_id} - {card_name} ({card_rarity})",
                        value=f"Продавец: <@{seller_id}>\nЦена: {price} монет",
                        inline=False
                    )

        await interaction.response.edit_message(embed=embed, view=self)


async def add_to_market(interaction: Interaction, seller_id: int, card_name: str, price: int, card_cur: sqlite3.Cursor):
    """Добавить карточку на торговую площадку по имени."""
    card_cur.execute("SELECT id FROM cards WHERE name = ?", (card_name,))
    card = card_cur.fetchone()

    if not card:
        await interaction.response.send_message("Карточка с таким именем не найдена.", ephemeral=True)
        return

    card_id = card[0]
    card_cur.execute("SELECT * FROM player_cards WHERE player_id = ? AND card_id = ?", (seller_id, card_id))
    if not card_cur.fetchone():
        await interaction.response.send_message("У вас нет такой карточки.", ephemeral=True)
        return

    # Проверяем, есть ли уже эта карточка на рынке у этого продавца
    market_cur.execute("SELECT * FROM marketplace WHERE seller_id = ? AND card_id = ?", (seller_id, card_id))
    if market_cur.fetchone():
        await interaction.response.send_message("Вы уже выставили эту карточку на продажу.", ephemeral=True)
        return

    market_cur.execute("INSERT INTO marketplace (seller_id, card_id, price) VALUES (?, ?, ?)", (seller_id, card_id, price))
    market_db.commit()
    await interaction.response.send_message("Карточка успешно выставлена на продажу!", ephemeral=True)



async def buy_card(interaction, buyer_id, listing_id, buyer_balance, card_cur, market_cur, market_db):
    """Купить карточку на торговой площадке."""
    # Получаем информацию о предложении
    market_cur.execute("SELECT seller_id, card_id, price FROM marketplace WHERE id = ?", (listing_id,))
    listing = market_cur.fetchone()

    if not listing:
        await interaction.response.send_message("Эта карточка уже не доступна на торговой площадке.", ephemeral=True)
        return

    seller_id, card_id, price = listing

    # Проверяем, достаточно ли у покупателя монет
    if buyer_balance < price:
        await interaction.response.send_message(f"У вас недостаточно монет для покупки этой карточки. Необходимо {price} монет.", ephemeral=True)
        return

    card_cur.execute("SELECT * FROM player_cards WHERE player_id = ? AND card_id = ?", (buyer_id, card_id))
    if card_cur.fetchone():
        await interaction.response.send_message("У вас уже есть эта карточка. Покупка отклонена.", ephemeral=True)
        return

    # Проверяем, существует ли карточка
    card_cur.execute("SELECT name, rarity FROM cards WHERE id = ?", (card_id,))
    card_data = card_cur.fetchone()

    if not card_data:
        await interaction.response.send_message("Карточка не найдена.", ephemeral=True)
        return

    card_name, card_rarity = card_data

    # Переводим карточку от продавца к покупателю
    card_cur.execute("INSERT INTO player_cards (player_id, card_id) VALUES (?, ?)", (buyer_id, card_id))
    card_cur.execute("DELETE FROM player_cards WHERE player_id = ? AND card_id = ?", (seller_id, card_id))

    # Снимаем деньги с покупателя
    new_balance = buyer_balance - price
    cur.execute("UPDATE users SET money = ? WHERE id = ?", (new_balance, buyer_id))
    conn.commit()

    # Обновляем баланс продавца
    cur.execute("SELECT money FROM users WHERE id = ?", (seller_id,))
    seller_data = cur.fetchone()

    if not seller_data:
        await interaction.response.send_message("Ошибка: продавец не найден в системе.", ephemeral=True)
        return

    seller_balance = seller_data[0]
    new_seller_balance = seller_balance + price
    cur.execute("UPDATE users SET money = ? WHERE id = ?", (new_seller_balance, seller_id))
    conn.commit()  # Сохраняем изменения для продавца

    # Удаляем карточку из торговой площадки
    market_cur.execute("DELETE FROM marketplace WHERE id = ?", (listing_id,))
    market_db.commit()

    await interaction.response.send_message(f"Вы успешно купили карточку {card_name} ({card_rarity}) у <@{seller_id}> за {price} монет!", ephemeral=True)
