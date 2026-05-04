from enum import Enum


class AuthError(str, Enum):
    USER_EXISTS = "user_exists"
    USER_NOT_FOUND = "user_not_found"
    WRONG_PASSWORD = "wrong_password"


class MessageError(str, Enum):
    MESSAGE_NOT_FOUND = "message_not_found"
    FORBIDDEN = "forbidden"


class WSEventType(str, Enum):
    MESSAGE_CREATED = "message.created"
    MESSAGE_UPDATED = "message.updated"
    MESSAGE_DELETED = "message.deleted"


MSG_LIMIT_DEFAULT = 50
MSG_LIMIT_MAX = 100
