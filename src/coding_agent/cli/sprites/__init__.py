"""Embedded pixel sprites for the mascot rail."""

from coding_agent.cli.sprites.bank import MascotBank, get_bank, reset_bank
from coding_agent.cli.sprites.pack import POSES, discover_packs, load_pack

__all__ = [
    "POSES",
    "MascotBank",
    "discover_packs",
    "get_bank",
    "load_pack",
    "reset_bank",
]
