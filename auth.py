from flask_login import UserMixin

import database as db


class User(UserMixin):
    def __init__(self, id: int, username: str, email: str):
        self.id = id
        self.username = username
        self.email = email


def load_user(user_id: str):
    row = db.get_user_by_id(int(user_id))
    if row:
        return User(row["id"], row["username"], row["email"])
    return None
