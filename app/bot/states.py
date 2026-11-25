from aiogram.fsm.state import State, StatesGroup


class NewPost(StatesGroup):
    choosing_channels = State()
    choosing_type = State()
    entering_text = State()
    entering_caption = State()
    attaching_media = State()
    creating_poll = State()
    preview = State()
    buttons_list = State()
    adding_button_text = State()
    adding_button_url = State()
    scheduling_input = State()


class EditingPublication(StatesGroup):
    waiting_text = State()
    waiting_reschedule = State()


class NewReminder(StatesGroup):
    choosing_date = State()
    custom_date = State()
    choosing_time = State()
    custom_time = State()
    entering_text = State()
    choosing_repeat = State()
    choosing_weekdays = State()
    custom_interval = State()
    confirm = State()


class ServerSettings(StatesGroup):
    terminal_password = State()
    terminal_active = State()
