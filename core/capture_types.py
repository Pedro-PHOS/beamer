"""Key results shared by capture backends and their consumers."""

import unicodedata


class DeadKey:
    def __init__(self, character: str) -> None:
        self.character = character


class TextInput:
    def __init__(self, text: str) -> None:
        self.text = text


def compose_dead_key(dead_key, character):
    name = unicodedata.name(dead_key, "")
    if name.startswith("MODIFIER LETTER "):
        name = name[len("MODIFIER LETTER "):]
    try:
        combining = unicodedata.lookup("COMBINING " + name)
    except KeyError:
        return TextInput(dead_key + character)
    composed = unicodedata.normalize("NFC", character + combining)
    return composed if len(composed) == 1 else TextInput(dead_key + character)
