from aiogram.fsm.state import State, StatesGroup


class SalaryFlow(StatesGroup):
    waiting_rate = State()

    # Для actions.py (начисление, штраф)
    action_date = State()
    action_value = State()

    # Для advance.py (аванс, ЗП)
    advance_date = State()
    advance_value = State()

    # Отмена
    waiting_undo_date = State()
