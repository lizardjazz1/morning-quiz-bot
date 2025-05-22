# storage/state_manager.py

class StateManager:
    def __init__(self):
        self.current_poll = {}  # {poll_id: {...}}
        self.current_quiz_session = {}  # {chat_id: {...}}
        self.user_scores = {}  # {chat_id: {user_id: {...}}}

state = StateManager()