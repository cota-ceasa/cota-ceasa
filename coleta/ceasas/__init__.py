"""Registro das CEASAs. Para adicionar uma nova: crie xx.py herdando de Coletor e inclua aqui."""
from .es import ColetorES

REGISTRO = {c.id: c for c in [
    ColetorES(),
    # ColetorMG(), ColetorSP(), ...
]}
