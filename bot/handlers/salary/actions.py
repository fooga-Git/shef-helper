import logging
from datetime import date

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User, SalaryEntry
from bot.keyboards.salary import date_kb
from bot.services.salary import parse_date, validate_date, unit_for
from bot.services.salary_actions import ACTIONS, ACCRUAL
from bot.services.salary_states import SalaryFlow

logger = logging.getLogger(__name__)
router = Router(name="sal_actions")


# ---------- Шаг 1: пользователь нажал «Начислить» или «Штраф» ----------

@router.callback_query(F.data.regexp(r"^sal_(accrual|penalty)$"))
async def start_action(callback: CallbackQuery, state: FSMContext) -> None:
    action_name = callback.data.replace("sal_", "")
    action = ACTIONS[action_name]

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

    if not user:
        return

    # для начисления — свой prompt в зависимости от ставки
    if action_name == ACCRUAL.name:
        if user.rate_type == "hour":
            prompt = "Введи количество часов:"
        else:
            prompt = "Введи коэффициент смены:"
    else:
        prompt = action.prompt

    await state.update_data(action=action_name)
    await callback.message.edit_text(prompt, reply_markup=date_kb(action_name))
    await callback.answer()


# ---------- Шаг 2: выбор «сегодня» / «другая дата» ----------

@router.callback_query(F.data.regexp(r"^(accrual|penalty)_today$"))
async def date_today(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(target_date=date.today().isoformat())
    await callback.message.edit_text("Введи значение:")
    await state.set_state(SalaryFlow.action_value)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^(accrual|penalty)_other$"))
async def date_other(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "📆 Введи дату в формате <code>ДД.ММ</code> или <code>ДД.ММ.ГГГГ</code>:"
    )
    await state.set_state(SalaryFlow.action_date)
    await callback.answer()


# ---------- Шаг 3: ввод даты (если выбрано «другая») ----------

@router.message(SalaryFlow.action_date)
async def date_input(message: Message, state: FSMContext) -> None:
    d = await parse_date(message.text)
    if not d:
        await message.answer("Неверный формат. Пример: <code>05.10</code>")
        return

    err = await validate_date(message.from_user.id, d)
    if err:
        await message.answer(err)
        return

    await state.update_data(target_date=d.isoformat())
    await message.answer("Введи значение:")
    await state.set_state(SalaryFlow.action_value)


# ---------- Шаг 4: ввод значения и сохранение ----------

@router.message(SalaryFlow.action_value)
async def value_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    action_name = data.get("action")
    if not action_name:
        await state.clear()
        return

    action = ACTIONS[action_name]

    try:
        value = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("Введи число.")
        return

    if value <= 0:
        await message.answer("Число должно быть больше 0.")
        return

    target_date_str = data.get("target_date")
    target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if not user:
            await state.clear()
            return

        # защита от двойного начисления
        if action.is_accrual:
            existing = await session.execute(
                select(SalaryEntry).where(
                    SalaryEntry.telegram_id == user.telegram_id,
                    SalaryEntry.entry_type == action.name,
                    SalaryEntry.entry_date == target_date,
                )
            )
            if existing.scalar_one_or_none():
                await state.clear()
                await message.answer(f"❌ За {target_date.strftime('%d.%m')} уже начислено.")
                return

        # считаем amount
        if action.is_accrual:
            amount = float(user.rate_amount) * value
        else:
            amount = value  # для штрафа value = сумма

        entry = SalaryEntry(
            telegram_id=user.telegram_id,
            entry_type=action.name,
            value=value,
            amount=action.sign * amount,
            year=target_date.year,
            month=target_date.month,
            entry_date=target_date,
        )
        session.add(entry)
        await session.commit()

        unit = unit_for(user)

    logger.info("action=%s date=%s value=%s user=%s", action_name, target_date, value, user.telegram_id)
    await state.clear()

    if action.is_accrual:
        await message.answer(f"✅ Начислено за {target_date.strftime('%d.%m')}: {action.sign * amount:.0f} ₽ ({value:g} {unit})")
    else:
        await message.answer(f"✅ {action.label} за {target_date.strftime('%d.%m')}: {action.sign * amount:.0f} ₽")
