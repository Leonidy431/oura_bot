#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Oura Ring Telegram Bot.

Telegram-бот для получения данных с Oura Ring через официальный API v2.
Поддерживает все доступные эндпоинты: сон, активность, готовность,
пульс, стресс, SpO2, тренировки, сессии и персональную информацию.

Автор: Oura Bot Team
Лицензия: MIT
Версия: 2.0.0

Для развертывания на Railway:
1. Создайте проект на Railway
2. Подключите репозиторий
3. Установите переменные окружения:
   - TELEGRAM_BOT_TOKEN: токен Telegram бота
   - OURA_PAT: персональный токен доступа Oura API

Документация Oura API: https://cloud.ouraring.com/v2/docs
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования в формате, удобном для Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Конфигурация
# =============================================================================

# Токен Telegram бота (из переменных окружения или значение по умолчанию)
TELEGRAM_BOT_TOKEN: str = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "7974975472:AAEwabxrx0npIrgYt-pGSxkM2ytEaTPlwdQ"
)

# Персональный токен доступа Oura API
OURA_PAT: Optional[str] = os.getenv("OURA_PAT")

# Базовый URL Oura API v2
OURA_API_BASE: str = "https://api.ouraring.com/v2/usercollection"


# =============================================================================
# Вспомогательные функции для работы с API
# =============================================================================

def get_date_range(days_back: int = 1) -> tuple[str, str]:
    """
    Получить диапазон дат для запроса к API.

    Args:
        days_back: Количество дней назад от текущей даты.

    Returns:
        Кортеж из двух строк: (start_date, end_date) в формате YYYY-MM-DD.
    """
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days_back)
    return str(start_date), str(end_date)


async def fetch_oura_data(
    endpoint: str,
    use_datetime: bool = False,
    days_back: int = 1
) -> dict[str, Any]:
    """
    Получить данные из Oura API.

    Args:
        endpoint: Название эндпоинта API (например, 'daily_sleep').
        use_datetime: Использовать datetime параметры вместо date.
        days_back: Количество дней назад для запроса данных.

    Returns:
        Словарь с данными от API или словарь с ключом 'error'.

    Raises:
        aiohttp.ClientError: При ошибке сетевого запроса.
    """
    if not OURA_PAT:
        logger.error("OURA_PAT не установлен")
        return {"error": "Токен Oura API не настроен. Установите OURA_PAT."}

    headers = {"Authorization": f"Bearer {OURA_PAT}"}
    start_date, end_date = get_date_range(days_back)

    # Некоторые эндпоинты требуют datetime вместо date
    if use_datetime:
        params = {
            "start_datetime": f"{start_date}T00:00:00+00:00",
            "end_datetime": f"{end_date}T23:59:59+00:00"
        }
    else:
        params = {"start_date": start_date, "end_date": end_date}

    url = f"{OURA_API_BASE}/{endpoint}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Успешный запрос к {endpoint}")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Ошибка API {endpoint}: {response.status} - {error_text}"
                    )
                    return {"error": f"Ошибка API: {response.status}"}
    except aiohttp.ClientError as e:
        logger.error(f"Сетевая ошибка при запросе {endpoint}: {e}")
        return {"error": f"Сетевая ошибка: {str(e)}"}


async def fetch_personal_info() -> dict[str, Any]:
    """
    Получить персональную информацию пользователя.

    Этот эндпоинт не требует параметров даты.

    Returns:
        Словарь с персональными данными или ошибкой.
    """
    if not OURA_PAT:
        return {"error": "Токен Oura API не настроен. Установите OURA_PAT."}

    headers = {"Authorization": f"Bearer {OURA_PAT}"}
    url = f"{OURA_API_BASE}/personal_info"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Ошибка API: {response.status}"}
    except aiohttp.ClientError as e:
        return {"error": f"Сетевая ошибка: {str(e)}"}


def format_duration(seconds: Optional[int]) -> str:
    """
    Форматировать длительность из секунд в читаемый формат.

    Args:
        seconds: Количество секунд.

    Returns:
        Строка в формате "Xч Yм" или "N/A" если данные отсутствуют.
    """
    if seconds is None:
        return "N/A"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}ч {minutes}м"


def safe_get(data: dict, *keys: str, default: Any = "N/A") -> Any:
    """
    Безопасное получение вложенных значений из словаря.

    Args:
        data: Исходный словарь.
        *keys: Последовательность ключей для навигации.
        default: Значение по умолчанию.

    Returns:
        Значение по указанному пути или default.
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        if result is None:
            return default
    return result


# =============================================================================
# Обработчики команд Telegram
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /start.

    Отправляет приветственное сообщение со списком доступных команд.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    welcome_text = """
Добро пожаловать в Oura Ring Bot!

Доступные команды:

ДАННЫЕ О СНЕ:
/sleep - Детальные данные о сне
/daily_sleep - Дневная оценка сна
/sleep_time - Рекомендуемое время сна

АКТИВНОСТЬ:
/activity - Дневная активность
/steps - Количество шагов
/calories - Сожженные калории

ЗДОРОВЬЕ:
/readiness - Готовность организма
/heart_rate - Данные пульса
/hrv - Вариабельность сердечного ритма
/spo2 - Уровень кислорода в крови
/stress - Уровень стресса

ТРЕНИРОВКИ И СЕССИИ:
/workouts - Тренировки
/sessions - Сессии медитации/отдыха
/tags - Пользовательские теги

ПРОЧЕЕ:
/profile - Информация профиля
/ring - Информация о кольце
/summary - Общая сводка за день
/help - Справка по командам

Для получения данных необходимо установить OURA_PAT.
    """
    await update.message.reply_text(welcome_text.strip())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /help.

    Отправляет справочную информацию о боте.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    help_text = """
Oura Ring Bot - Справка

Этот бот позволяет получать данные с вашего Oura Ring через Telegram.

Для работы бота необходимо:
1. Получить Personal Access Token на https://cloud.ouraring.com/personal-access-tokens
2. Установить переменную окружения OURA_PAT

Все данные запрашиваются за последние сутки.

Исходный код: GitHub
Документация API: https://cloud.ouraring.com/v2/docs
    """
    await update.message.reply_text(help_text.strip())


async def cmd_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /sleep - детальные данные о периодах сна.

    Возвращает полную информацию о каждом периоде сна:
    - Время засыпания и пробуждения
    - Длительность фаз сна (глубокий, легкий, REM)
    - Пульс и HRV во сне
    - Эффективность сна

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("sleep")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о сне за указанный период.")
        return

    for i, sleep in enumerate(data["data"], 1):
        # Основные метрики
        bedtime_start = sleep.get("bedtime_start", "N/A")
        bedtime_end = sleep.get("bedtime_end", "N/A")
        total_duration = format_duration(sleep.get("total_sleep_duration"))
        time_in_bed = format_duration(sleep.get("time_in_bed"))

        # Фазы сна
        deep = format_duration(sleep.get("deep_sleep_duration"))
        light = format_duration(sleep.get("light_sleep_duration"))
        rem = format_duration(sleep.get("rem_sleep_duration"))
        awake = format_duration(sleep.get("awake_time"))

        # Физиологические показатели
        avg_hr = sleep.get("average_heart_rate", "N/A")
        lowest_hr = sleep.get("lowest_heart_rate", "N/A")
        avg_hrv = sleep.get("average_hrv", "N/A")
        avg_breath = sleep.get("average_breath", "N/A")

        # Качество сна
        efficiency = sleep.get("efficiency", "N/A")
        latency = sleep.get("latency", "N/A")
        restless = sleep.get("restless_periods", "N/A")
        sleep_type = sleep.get("type", "N/A")

        text = f"""
Сон #{i} ({sleep_type})

ВРЕМЯ:
  Начало: {bedtime_start}
  Конец: {bedtime_end}
  В кровати: {time_in_bed}
  Общий сон: {total_duration}

ФАЗЫ СНА:
  Глубокий: {deep}
  Легкий: {light}
  REM: {rem}
  Бодрствование: {awake}

ФИЗИОЛОГИЯ:
  Средний пульс: {avg_hr} уд/мин
  Мин. пульс: {lowest_hr} уд/мин
  Средний HRV: {avg_hrv} мс
  Дыхание: {avg_breath} вд/мин

КАЧЕСТВО:
  Эффективность: {efficiency}%
  Задержка засыпания: {latency} сек
  Беспокойных периодов: {restless}
        """
        await update.message.reply_text(text.strip())


async def cmd_daily_sleep(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /daily_sleep - дневная оценка сна.

    Возвращает общую оценку сна за день и факторы,
    влияющие на эту оценку.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("daily_sleep")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных об оценке сна.")
        return

    sleep = data["data"][-1]  # Последняя запись
    day = sleep.get("day", "N/A")
    score = sleep.get("score", "N/A")

    # Факторы оценки
    contributors = sleep.get("contributors", {})
    deep_sleep = contributors.get("deep_sleep", "N/A")
    efficiency = contributors.get("efficiency", "N/A")
    latency = contributors.get("latency", "N/A")
    rem_sleep = contributors.get("rem_sleep", "N/A")
    restfulness = contributors.get("restfulness", "N/A")
    timing = contributors.get("timing", "N/A")
    total_sleep = contributors.get("total_sleep", "N/A")

    text = f"""
Оценка сна за {day}

ОБЩАЯ ОЦЕНКА: {score}/100

ФАКТОРЫ ОЦЕНКИ:
  Общая продолжительность: {total_sleep}
  Глубокий сон: {deep_sleep}
  REM сон: {rem_sleep}
  Эффективность: {efficiency}
  Спокойствие: {restfulness}
  Задержка засыпания: {latency}
  Время отхода ко сну: {timing}
    """
    await update.message.reply_text(text.strip())


async def cmd_sleep_time(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /sleep_time - рекомендуемое время сна.

    Возвращает оптимальное время отхода ко сну на основе
    анализа паттернов пользователя.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("sleep_time")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет рекомендаций по времени сна.")
        return

    sleep_time = data["data"][-1]
    day = sleep_time.get("day", "N/A")
    status = sleep_time.get("status", "N/A")
    recommendation = sleep_time.get("recommendation", "N/A")

    optimal = sleep_time.get("optimal_bedtime", {})
    start_offset = optimal.get("start_offset", "N/A")
    end_offset = optimal.get("end_offset", "N/A")

    text = f"""
Рекомендации по сну на {day}

Статус: {status}
Рекомендация: {recommendation}

ОПТИМАЛЬНОЕ ВРЕМЯ:
  Начало окна: {start_offset}
  Конец окна: {end_offset}
    """
    await update.message.reply_text(text.strip())


async def cmd_activity(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /activity - данные о дневной активности.

    Возвращает полную информацию об активности за день:
    - Шаги и калории
    - Время активности по интенсивности
    - MET-минуты
    - Оценка активности

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("daily_activity")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных об активности.")
        return

    activity = data["data"][-1]
    day = activity.get("day", "N/A")
    score = activity.get("score", "N/A")

    # Основные метрики
    steps = activity.get("steps", "N/A")
    active_cal = activity.get("active_calories", "N/A")
    total_cal = activity.get("total_calories", "N/A")
    target_cal = activity.get("target_calories", "N/A")
    distance = activity.get("equivalent_walking_distance", "N/A")

    # Время активности
    high_activity = activity.get("high_activity_time", "N/A")
    medium_activity = activity.get("medium_activity_time", "N/A")
    low_activity = activity.get("low_activity_time", "N/A")
    sedentary = activity.get("sedentary_time", "N/A")
    resting = activity.get("resting_time", "N/A")

    # MET
    avg_met = activity.get("average_met_minutes", "N/A")
    met_inactive = activity.get("met", {}).get("inactive", "N/A") if isinstance(
        activity.get("met"), dict
    ) else "N/A"

    # Факторы оценки
    contributors = activity.get("contributors", {})
    meet_daily_targets = contributors.get("meet_daily_targets", "N/A")
    move_every_hour = contributors.get("move_every_hour", "N/A")
    recovery_time = contributors.get("recovery_time", "N/A")
    stay_active = contributors.get("stay_active", "N/A")
    training_frequency = contributors.get("training_frequency", "N/A")
    training_volume = contributors.get("training_volume", "N/A")

    text = f"""
Активность за {day}

ОЦЕНКА: {score}/100

ОСНОВНЫЕ ПОКАЗАТЕЛИ:
  Шаги: {steps}
  Активные калории: {active_cal} ккал
  Всего калорий: {total_cal} ккал
  Цель калорий: {target_cal} ккал
  Экв. дистанция: {distance} м

ВРЕМЯ АКТИВНОСТИ:
  Высокая: {high_activity} мин
  Средняя: {medium_activity} мин
  Низкая: {low_activity} мин
  Сидячее: {sedentary} мин
  Отдых: {resting} мин

MET:
  Средний MET: {avg_met}

ФАКТОРЫ ОЦЕНКИ:
  Достижение целей: {meet_daily_targets}
  Движение каждый час: {move_every_hour}
  Время восстановления: {recovery_time}
  Поддержание активности: {stay_active}
  Частота тренировок: {training_frequency}
  Объем тренировок: {training_volume}
    """
    await update.message.reply_text(text.strip())


async def cmd_steps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /steps - быстрый просмотр шагов.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("daily_activity")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о шагах.")
        return

    activity = data["data"][-1]
    steps = activity.get("steps", "N/A")
    day = activity.get("day", "N/A")

    await update.message.reply_text(f"Шаги за {day}: {steps}")


async def cmd_calories(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /calories - быстрый просмотр калорий.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("daily_activity")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о калориях.")
        return

    activity = data["data"][-1]
    day = activity.get("day", "N/A")
    active = activity.get("active_calories", "N/A")
    total = activity.get("total_calories", "N/A")
    target = activity.get("target_calories", "N/A")

    text = f"""
Калории за {day}

Активные: {active} ккал
Всего: {total} ккал
Цель: {target} ккал
    """
    await update.message.reply_text(text.strip())


async def cmd_readiness(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /readiness - данные о готовности организма.

    Возвращает оценку готовности и факторы, влияющие на неё:
    - Баланс активности
    - Температура тела
    - HRV баланс
    - Качество сна
    - Индекс восстановления

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("daily_readiness")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о готовности.")
        return

    readiness = data["data"][-1]
    day = readiness.get("day", "N/A")
    score = readiness.get("score", "N/A")

    # Температура
    temp_deviation = readiness.get("temperature_deviation", "N/A")
    temp_trend = readiness.get("temperature_trend_deviation", "N/A")

    # Факторы оценки
    contributors = readiness.get("contributors", {})
    activity_balance = contributors.get("activity_balance", "N/A")
    body_temperature = contributors.get("body_temperature", "N/A")
    hrv_balance = contributors.get("hrv_balance", "N/A")
    previous_day = contributors.get("previous_day_activity", "N/A")
    previous_night = contributors.get("previous_night", "N/A")
    recovery_index = contributors.get("recovery_index", "N/A")
    resting_hr = contributors.get("resting_heart_rate", "N/A")
    sleep_balance = contributors.get("sleep_balance", "N/A")

    text = f"""
Готовность за {day}

ОЦЕНКА: {score}/100

ТЕМПЕРАТУРА:
  Отклонение: {temp_deviation}°C
  Тренд: {temp_trend}°C

ФАКТОРЫ ОЦЕНКИ:
  Баланс активности: {activity_balance}
  Температура тела: {body_temperature}
  Баланс HRV: {hrv_balance}
  Активность вчера: {previous_day}
  Сон прошлой ночью: {previous_night}
  Индекс восстановления: {recovery_index}
  Пульс покоя: {resting_hr}
  Баланс сна: {sleep_balance}
    """
    await update.message.reply_text(text.strip())


async def cmd_heart_rate(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /heart_rate - данные о пульсе.

    Возвращает последние измерения пульса с указанием
    времени и источника данных.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("heartrate", use_datetime=True)

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о пульсе.")
        return

    # Берем последние 10 измерений
    hr_data = data["data"][-10:]

    text = "Последние измерения пульса:\n\n"
    for hr in hr_data:
        bpm = hr.get("bpm", "N/A")
        source = hr.get("source", "N/A")
        timestamp = hr.get("timestamp", "N/A")
        text += f"  {timestamp}: {bpm} уд/мин ({source})\n"

    # Статистика
    all_bpm = [hr.get("bpm", 0) for hr in data["data"] if hr.get("bpm")]
    if all_bpm:
        avg_bpm = sum(all_bpm) // len(all_bpm)
        min_bpm = min(all_bpm)
        max_bpm = max(all_bpm)
        text += f"\nСТАТИСТИКА ЗА ПЕРИОД:\n"
        text += f"  Средний: {avg_bpm} уд/мин\n"
        text += f"  Минимум: {min_bpm} уд/мин\n"
        text += f"  Максимум: {max_bpm} уд/мин\n"
        text += f"  Измерений: {len(all_bpm)}"

    await update.message.reply_text(text)


async def cmd_hrv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /hrv - вариабельность сердечного ритма.

    Извлекает данные HRV из информации о сне.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("sleep")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о HRV.")
        return

    sleep = data["data"][-1]
    avg_hrv = sleep.get("average_hrv", "N/A")
    day = sleep.get("bedtime_start", "N/A")[:10] if sleep.get("bedtime_start") else "N/A"

    # HRV данные по интервалам (если есть)
    hrv_data = sleep.get("hrv", {})
    if hrv_data and isinstance(hrv_data, dict):
        hrv_items = hrv_data.get("items", [])
        if hrv_items:
            valid_hrv = [h for h in hrv_items if h is not None]
            if valid_hrv:
                min_hrv = min(valid_hrv)
                max_hrv = max(valid_hrv)
            else:
                min_hrv = max_hrv = "N/A"
        else:
            min_hrv = max_hrv = "N/A"
    else:
        min_hrv = max_hrv = "N/A"

    text = f"""
HRV (вариабельность сердечного ритма)

Дата: {day}
Средний HRV: {avg_hrv} мс
Минимум: {min_hrv} мс
Максимум: {max_hrv} мс

HRV - ключевой показатель восстановления и стресса.
Высокий HRV = хорошее восстановление.
    """
    await update.message.reply_text(text.strip())


async def cmd_spo2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /spo2 - уровень кислорода в крови.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("daily_spo2")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных SpO2.")
        return

    spo2 = data["data"][-1]
    day = spo2.get("day", "N/A")

    spo2_percentage = spo2.get("spo2_percentage", {})
    if isinstance(spo2_percentage, dict):
        average = spo2_percentage.get("average", "N/A")
    else:
        average = spo2_percentage if spo2_percentage else "N/A"

    text = f"""
SpO2 (кислород в крови) за {day}

Средний уровень: {average}%

Норма: 95-100%
<95%: возможна гипоксия
    """
    await update.message.reply_text(text.strip())


async def cmd_stress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /stress - данные о стрессе.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("daily_stress")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о стрессе.")
        return

    stress = data["data"][-1]
    day = stress.get("day", "N/A")
    stress_high = stress.get("stress_high", "N/A")
    recovery_high = stress.get("recovery_high", "N/A")
    day_summary = stress.get("day_summary", "N/A")

    text = f"""
Стресс за {day}

Сводка дня: {day_summary}
Время высокого стресса: {stress_high} мин
Время восстановления: {recovery_high} мин
    """
    await update.message.reply_text(text.strip())


async def cmd_workouts(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /workouts - данные о тренировках.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("workout")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о тренировках.")
        return

    text = "Тренировки:\n\n"
    for i, workout in enumerate(data["data"], 1):
        activity = workout.get("activity", "N/A")
        label = workout.get("label", "")
        day = workout.get("day", "N/A")
        start = workout.get("start_datetime", "N/A")
        end = workout.get("end_datetime", "N/A")
        calories = workout.get("calories", "N/A")
        distance = workout.get("distance", "N/A")
        intensity = workout.get("intensity", "N/A")
        source = workout.get("source", "N/A")

        text += f"""
Тренировка #{i}: {activity} {label}
  Дата: {day}
  Начало: {start}
  Конец: {end}
  Калории: {calories} ккал
  Дистанция: {distance} м
  Интенсивность: {intensity}
  Источник: {source}
"""

    await update.message.reply_text(text.strip())


async def cmd_sessions(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /sessions - сессии медитации/отдыха.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("session")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о сессиях.")
        return

    text = "Сессии отдыха/медитации:\n\n"
    for i, session in enumerate(data["data"], 1):
        session_type = session.get("type", "N/A")
        day = session.get("day", "N/A")
        start = session.get("start_datetime", "N/A")
        end = session.get("end_datetime", "N/A")
        mood = session.get("mood", "N/A")

        hr = session.get("heart_rate", {})
        if isinstance(hr, dict):
            avg_hr = hr.get("average", "N/A")
        else:
            avg_hr = "N/A"

        hrv = session.get("heart_rate_variability", {})
        if isinstance(hrv, dict):
            avg_hrv = hrv.get("average", "N/A")
        else:
            avg_hrv = "N/A"

        text += f"""
Сессия #{i}: {session_type}
  Дата: {day}
  Начало: {start}
  Конец: {end}
  Настроение: {mood}
  Средний пульс: {avg_hr} уд/мин
  Средний HRV: {avg_hrv} мс
"""

    await update.message.reply_text(text.strip())


async def cmd_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /tags - пользовательские теги.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("tag")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет тегов за указанный период.")
        return

    text = "Пользовательские теги:\n\n"
    for tag in data["data"]:
        tag_type = tag.get("tag_type_code", "N/A")
        day = tag.get("day", tag.get("start_day", "N/A"))
        comment = tag.get("comment", "")
        tag_text = tag.get("text", "")

        text += f"  [{day}] {tag_type}"
        if tag_text:
            text += f": {tag_text}"
        if comment:
            text += f" ({comment})"
        text += "\n"

    await update.message.reply_text(text.strip())


async def cmd_profile(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /profile - персональная информация.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_personal_info()

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    user_id = data.get("id", "N/A")
    age = data.get("age", "N/A")
    weight = data.get("weight", "N/A")
    height = data.get("height", "N/A")
    sex = data.get("biological_sex", "N/A")
    email = data.get("email", "N/A")

    text = f"""
Профиль пользователя

ID: {user_id}
Email: {email}
Возраст: {age} лет
Пол: {sex}
Вес: {weight} кг
Рост: {height} см
    """
    await update.message.reply_text(text.strip())


async def cmd_ring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /ring - информация о кольце.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    data = await fetch_oura_data("ring_configuration")

    if "error" in data:
        await update.message.reply_text(f"Ошибка: {data['error']}")
        return

    if not data.get("data"):
        await update.message.reply_text("Нет данных о кольце.")
        return

    ring = data["data"][-1] if data["data"] else {}
    color = ring.get("color", "N/A")
    design = ring.get("design", "N/A")
    firmware = ring.get("firmware_version", "N/A")
    hardware = ring.get("hardware_type", "N/A")
    size = ring.get("size", "N/A")
    setup_at = ring.get("set_up_at", "N/A")

    text = f"""
Информация о кольце Oura

Цвет: {color}
Дизайн: {design}
Размер: {size}
Тип оборудования: {hardware}
Версия прошивки: {firmware}
Дата настройки: {setup_at}
    """
    await update.message.reply_text(text.strip())


async def cmd_summary(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик команды /summary - общая сводка за день.

    Собирает ключевые показатели из всех категорий данных.

    Args:
        update: Объект обновления Telegram.
        context: Контекст выполнения команды.
    """
    # Загружаем все данные параллельно
    sleep_data = await fetch_oura_data("daily_sleep")
    activity_data = await fetch_oura_data("daily_activity")
    readiness_data = await fetch_oura_data("daily_readiness")

    today = datetime.utcnow().date()

    # Сон
    sleep_score = "N/A"
    if sleep_data.get("data"):
        sleep_score = sleep_data["data"][-1].get("score", "N/A")

    # Активность
    activity_score = "N/A"
    steps = "N/A"
    calories = "N/A"
    if activity_data.get("data"):
        activity = activity_data["data"][-1]
        activity_score = activity.get("score", "N/A")
        steps = activity.get("steps", "N/A")
        calories = activity.get("active_calories", "N/A")

    # Готовность
    readiness_score = "N/A"
    if readiness_data.get("data"):
        readiness_score = readiness_data["data"][-1].get("score", "N/A")

    text = f"""
Сводка за {today}

ОЦЕНКИ:
  Сон: {sleep_score}/100
  Активность: {activity_score}/100
  Готовность: {readiness_score}/100

АКТИВНОСТЬ:
  Шаги: {steps}
  Калории: {calories} ккал

Используйте отдельные команды для детальной информации.
    """
    await update.message.reply_text(text.strip())


# =============================================================================
# Главная функция
# =============================================================================

def main() -> None:
    """
    Точка входа в приложение.

    Создает и запускает Telegram бота с настроенными обработчиками команд.
    Бот работает в режиме long polling.
    """
    # Проверка конфигурации
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        raise ValueError("Необходимо установить TELEGRAM_BOT_TOKEN")

    if not OURA_PAT:
        logger.warning(
            "OURA_PAT не установлен. Бот запустится, но API запросы "
            "не будут работать."
        )

    # Создание приложения
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрация обработчиков команд
    commands = [
        ("start", cmd_start),
        ("help", cmd_help),
        ("sleep", cmd_sleep),
        ("daily_sleep", cmd_daily_sleep),
        ("sleep_time", cmd_sleep_time),
        ("activity", cmd_activity),
        ("steps", cmd_steps),
        ("calories", cmd_calories),
        ("readiness", cmd_readiness),
        ("heart_rate", cmd_heart_rate),
        ("hrv", cmd_hrv),
        ("spo2", cmd_spo2),
        ("stress", cmd_stress),
        ("workouts", cmd_workouts),
        ("sessions", cmd_sessions),
        ("tags", cmd_tags),
        ("profile", cmd_profile),
        ("ring", cmd_ring),
        ("summary", cmd_summary),
    ]

    for command, handler in commands:
        app.add_handler(CommandHandler(command, handler))

    logger.info("Бот запускается...")
    logger.info(f"Доступные команды: {[cmd for cmd, _ in commands]}")

    # Запуск бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
