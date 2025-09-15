# apollonai/server.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
from uvicorn import Config, Server

from apollonai.core.containers import MainContainer
from apollonai.core.api.core_api import CoreApi

class ServerRunner:
    def __init__(
        self, 
        container: MainContainer, 
        api: CoreApi, 
        mcp: any,
        *, 
        max_workers: int = 10
    ):
        self.container = container
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        self.app = api.app

        # Make sure to print the host value to debug
        print(f"Host value: {self.container.config.SETTING_DICT.server.host}")

        self.config = Config(
            app=self.app,
            host=self.container.config.SETTING_DICT.server.host,
            port=self.container.config.SETTING_DICT.server.port,
            log_level="info",
            timeout_keep_alive=10,
            loop="uvloop",
            workers=1,
        )
        self.container.tts.tts_service().speak("Starting server.")
        self.server = Server(self.config)

    async def _serve_with_thread_pool(self):
        loop = asyncio.get_running_loop()
        loop.set_default_executor(self.thread_pool)
        await self.server.serve()

    def run(self):
        """Starts the FastAPI backend using Uvicorn and asyncio."""

        try:
            if asyncio.get_event_loop().is_running():
                import nest_asyncio
                nest_asyncio.apply()
                asyncio.create_task(self._serve_with_thread_pool())
            else:
                asyncio.run(self._serve_with_thread_pool())

        except Exception as e:
            # Safely format the exception object
            self.container.tts.tts_service().speak(f"Server failed: {str(e)}")
            print(f"❌ Server failed: {str(e)}")