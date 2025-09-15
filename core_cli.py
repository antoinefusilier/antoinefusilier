import typer
from ..containers import MainContainer
from apollonai.core.server import ServerRunner

class CoreCli:

    def __init__(self, container: MainContainer, server: ServerRunner):
        
        self.container = container
        self.app = typer.Typer()

        # self.app.add_typer(container.init().cli_app(), name="init")
        # self.app.add_typer(container.proj().cli_app(), name="proj")
        self.app.add_typer(container.repo().cli_app(), name="repo")
        self.app.add_typer(container.sol().cli_app(), name="sol")

        self.app.command("server")(server.run)

    def __call__(self):
        self.app()