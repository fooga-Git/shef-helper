from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.db.base import async_session
from bot.db.models import User

router = Router(name="admin_list")

ROLE_NAMES = {
    "chef": "Шеф-повар",
    "sous_chef": "Су-шеф",
    "cook": "Повар",
}

STATIONS = [
    "Горячий цех",
    "Холодный цех",
    "Суши",
    "Гриль",
    "Кондитерский",
    "Заготовочный",
    "Раздача",
]


def format_user_line(u: User) -> str:
    role = ROLE_NAMES.get(u.role, u.role)
    if u.role == "chef":
        return f"• <b>{u.full_name}</b> — {role}"
    station = u.station or "—"
    return f"• <b>{u.full_name}</b> — {role}\n  Цех: {station}"


@router.callback_query(F.data == "admin_list")
async def show_staff(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(select(User).order_by(User.id))
        users = result.scalars().all()

    if not users:
        await callback.message.edit_text(
            "Сотрудников пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
            ]),
        )
        await callback.answer()
        return

    lines = ["👥 <b>Сотрудники</b>\n"]
    buttons = []
    for u in users:
        lines.append(format_user_line(u))
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {u.full_name}",
            callback_data=f"open_edit_{u.telegram_id}",
        )])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("open_edit_"))
async def show_edit(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split("_", 2)[2])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    role = ROLE_NAMES.get(user.role, user.role)
    text = (
        f"✏️ <b>Редактирование</b>\n\n"
        f"ФИО: {user.full_name}\n"
        f"Роль: {role}\n"
    )
    if user.role != "chef":
        text += f"Цех: {user.station or '—'}\n"

    buttons = []
    if user.role != "chef":
        buttons.append([InlineKeyboardButton(text="🏭 Сменить цех", callback_data=f"edit_station_{tg_id}")])
    buttons.append([InlineKeyboardButton(text="👔 Сменить роль", callback_data=f"edit_role_{tg_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_list")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_station_"))
async def show_stations(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split("_", 2)[2])

    buttons = []
    for station in STATIONS:
        buttons.append([InlineKeyboardButton(
            text=station,
            callback_data=f"set_station_{tg_id}_{station}",
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_edit_{tg_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text("Выбери цех:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("set_station_"))
async def set_station(callback: CallbackQuery) -> None:
    # callback: set_station_{tg_id}_{station_name}
    parts = callback.data.split("_", 3)
    tg_id = int(parts[2])
    new_station = parts[3]

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if user:
            user.station = new_station
            await session.commit()

    await callback.answer(f"Цех: {new_station}", show_alert=True)
    await show_edit(callback)


@router.callback_query(F.data.startswith("edit_role_"))
async def show_roles(callback: CallbackQuery) -> None:
    tg_id = int(callback.data.split("_", 2)[2])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Повар", callback_data=f"set_role_{tg_id}_cook")],
        [InlineKeyboardButton(text="Су-шеф", callback_data=f"set_role_{tg_id}_sous_chef")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"open_edit_{tg_id}")],
    ])
    await callback.message.edit_text("Выбери новую роль:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("set_role_"))
async def set_role(callback: CallbackQuery) -> None:
    parts = callback.data.split("_", 3)
    tg_id = int(parts[2])
    new_role = parts[3]

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if user:
            user.role = new_role
            await session.commit()

    role_name = ROLE_NAMES.get(new_role, new_role)
    await callback.answer(f"Роль: {role_name}", show_alert=True)
    await show_edit(callback)
