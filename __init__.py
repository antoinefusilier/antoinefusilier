import os
from .config_loader_service import PythonConfigRetriever

base_dir = os.path.dirname(__file__)
retriever = PythonConfigRetriever(base_dir)
settings = retriever.retrieve_configs()
