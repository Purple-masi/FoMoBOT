import sqlite3

def calculate_required_points(level: int) -> int:
    """
    Вычисляет количество очков, необходимых для достижения следующего уровня.
    Формула: 100 + (текущий уровень * 20).
    """
    return 100 + (level * 20)

def add_rating_points(user_id: int, points: int, cursor, connection):
    """
    Добавляет очки рейтинга пользователю, обновляет уровень при необходимости.
    """
    # Получаем текущие данные пользователя
    cursor.execute("SELECT rating_point, rating_level FROM users WHERE id = ?", (user_id,))
    result = cursor.fetchone()

    if not result:
        raise ValueError(f"Пользователь с ID {user_id} не найден в базе данных.")

    current_points, current_level = result
    current_points += points  # Добавляем очки рейтинга

    # Проверяем, достигнут ли новый уровень
    while current_points >= calculate_required_points(current_level):
        current_points -= calculate_required_points(current_level)
        current_level += 1

    # Обновляем данные в базе
    cursor.execute(
        "UPDATE users SET rating_point = ?, rating_level = ? WHERE id = ?",
        (current_points, current_level, user_id)
    )
    connection.commit()

    return current_points, current_level

def set_rating(user_id: int, points: int, level: int, cursor, connection):
    """
    Устанавливает очки и уровень рейтинга пользователя.
    """
    cursor.execute(
        "UPDATE users SET rating_point = ?, rating_level = ? WHERE id = ?",
        (points, level, user_id)
    )
    connection.commit()

def main():
    # Подключение к базе данных
    connection = sqlite3.connect('users.db')
    cursor = connection.cursor()

    # Пример использования функций
    try:
        user_id = 1  # Идентификатор пользователя

        # Добавление очков рейтинга
        new_points, new_level = add_rating_points(user_id, 50, cursor, connection)
        print(f"Пользователь {user_id} теперь имеет {new_points} очков и уровень {new_level}.")

        # Установка конкретных значений рейтинга
        set_rating(user_id, 20, 2, cursor, connection)
        print(f"Пользователю {user_id} установлен уровень 2 с 20 очками.")

    except ValueError as e:
        print(e)

    finally:
        # Закрываем соединение с базой данных
        connection.close()

if __name__ == "__main__":
    main()
