from aiogram.fsm.state import State, StatesGroup


class SalaryFlow(StatesGroup):
    waiting_rate = State()
    waiting_accrual = State()
    waiting_accrual_date = State()
    waiting_penalty = State()
    waiting_penalty_date = State()
    waiting_advance_sum = State()
    waiting_salary_sum = State()
    waiting_undo_date = State()
