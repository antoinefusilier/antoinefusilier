from .core.containers import MainContainer
from apollonai.core.cli.core_cli import CoreCli
from apollonai.core.api.core_api import CoreApi
from apollonai.core.server import ServerRunner
from apollonai.core.config.vault_config import VaultConfig
# import pygame
# pygame.mixer.init()
# pygame.mixer.music.load("sounds/456101__burghrecords__future-ambience-background.wav")
# pygame.mixer.music.play(loops=-1, start=0.0)  # Loop indefinitely
# import argparse
# parser = argparse.ArgumentParser(description="ApollonAI Application")
# parser.add_argument(
#     "--cli",
#     action="store_true",
#     help="Activate command-line interface mode"
# )
# cli_args = parser.parse_args()
config = VaultConfig()
config.run()
################################################################
# Main Container - Dependency Injection
################################################################
container = MainContainer()
################################################################
# API - FastAPI
################################################################
api = CoreApi(container)
################################################################
# Server - Uvicorn
################################################################
server = ServerRunner(container, api)
################################################################
# CLI - Typer
################################################################
cli = CoreCli(container, server)
################################################################