from enum import Enum

class Vote(Enum):
    YES = "Yes"
    NO = "No"
    CANT_VOTE = "Cant_Vote"

class Alignment(Enum):
    GOOD = "Good"
    EVIL = "Evil"

class Phase(Enum):
    SETUP = "Setup"
    NIGHT = "Night"
    DAY = "Day" 