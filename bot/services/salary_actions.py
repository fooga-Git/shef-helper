from dataclasses import dataclass


@dataclass(frozen=True)
class ActionConfig:
    name: str           # ключ, который храним в data["action"]
    prompt: str         # что спросить
    sign: int           # +1 для начислений, -1 для вычетов
    is_accrual: bool    # требует ли проверки "одна смена в день"


ACCRUAL = ActionConfig(
    name="accrual",
    prompt="Введи коэффициент смены:",
    sign=+1,
    is_accrual=True,
)

PENALTY = ActionConfig(
    name="penalty",
    prompt="Введи сумму штрафа:",
    sign=-1,
    is_accrual=False,
)

ADVANCE = ActionConfig(
    name="advance",
    prompt="Введи сумму аванса:",
    sign=-1,
    is_accrual=False,
)

ACTIONS: dict[str, ActionConfig] = {
    ACCRUAL.name: ACCRUAL,
    PENALTY.name: PENALTY,
    ADVANCE.name: ADVANCE,
}
