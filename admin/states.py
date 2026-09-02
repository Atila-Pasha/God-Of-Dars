from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    search = State()
    resource_coin = State()
    resource_diamond = State()
    resource_banana = State()


class BroadcastStates(StatesGroup):
    content = State()


class BuffetStates(StatesGroup):
    convert_amount = State()


class QuestionStates(StatesGroup):
    text = State()
    answer = State()
    hours = State()
    coin = State()
    diamond = State()
    banana = State()


class TeacherStates(StatesGroup):
    name = State()
    damage = State()
    max_hp = State()
    purchase_price = State()
    upgrade_price = State()
    unlock_level = State()
    ability_text = State()
