"""Textual client for Kilogram."""

__all__ = ["KilogramTUI"]


def __getattr__(name: str):
    if name == "KilogramTUI":
        from kilogram_tui.app import KilogramTUI

        return KilogramTUI
    raise AttributeError(name)
