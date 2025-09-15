import importlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apollonai.core.containers import MainContainer  

class CoreApi():

    def __init__(self, container: MainContainer):
        for mod in [
            "apollonai.modules.init.services",
            "apollonai.modules.init.controllers",
            "apollonai.modules.proj.services",
            "apollonai.modules.proj.controllers",
            "apollonai.modules.repo.services",
            "apollonai.modules.repo.controllers",
            # ... add the rest ...
        ]:
            importlib.import_module(mod)


        self.app = FastAPI(title="ApollonAI API")

        origins = [
            "http://localhost:3000",  # your Next.js dev server
        ]

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # self.app.include_router(container.init().init_controller().router, prefix="/api/init", tags=["init"])
        # self.app.include_router(container.init().kubernetes_cluster_controller().router, prefix="/api/kube", tags=["kubernetes"])
        # self.app.include_router(container.proj().proj_controller().router, prefix="/api/projects", tags=["project"])
        self.app.include_router(container.repo().repo_controller().router, prefix="/api/repos", tags=["repo"])
        self.app.include_router(container.sol().sol_controller().router, prefix="/api/sols", tags=["sol"])


        # ==============================
        # MCP
        # ==============================
        self.mcp = 0    