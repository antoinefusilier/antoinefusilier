# core/containers.py
import pprint
from dependency_injector import containers, providers
from dynaconf import Dynaconf


from apollonai.core.config.db_config import CoreDbConfigContainer

# from apollonai.modules.init.container import InitContainer
# from apollonai.modules.proj.container import ProjContainer
from apollonai.modules.repo.container import RepoContainer
from apollonai.modules.sol.container import SolContainer
from apollonai.modules.db.container import DbContainer
from apollonai.modules.ent.container import EntContainer
from apollonai.modules.fe.container import FeContainer
from apollonai.modules.step.container import StepContainer
from apollonai.modules.df.container import DfContainer
from apollonai.modules.res.container import ResContainer
from apollonai.modules.file.container import FileContainer
from apollonai.modules.tts.container import TtsContainer
from  apollonai.modules.bp.container import BpContainer
from apollonai.core.config import settings
import pprint

from apollonai.core.config.elasticsearch import start_elastic_docker, clean_docker

class MainContainer(containers.DeclarativeContainer):
    """
    MainContainer is the Dependency Injection (DI) root container for the application.

    It centralizes configuration and orchestrates submodule containers.

    Attributes:
        config (providers.Configuration): Global application configuration provider.
        init (providers.Container): DI container for Init module.
        proj (providers.Container): DI container for Project module.
        repo (providers.Container): DI container for Repository module.
        sol (providers.Container): DI container for Subject of Law module.
    """
    # Global configuration provider

    # clean_docker()
    
    # 1. Load settings from the environment
    config = providers.Configuration()
    config.override(settings)


    start_elastic_docker(config.SETTINGS_DICT.apps.elastic)

    tts = providers.Container(
        TtsContainer,
        config=config,
    )

    # tts.tts_service().speak("Starting ApollonAI system.")
        # init = providers.Container(
        #     InitContainer,
        #     config=config
        # )
        # init.init_service().mount_docker_containers()


    # tts.tts_service().speak("Starting database configuration container.")
    db_config = providers.Container(
        CoreDbConfigContainer,
        config=config
    )
    # # Provide merged config at init
    def __init__(self):
        super().__init__()

    # --- Submodule Containers ---
    

    # proj = providers.Container(
    #     ProjContainer,
    #     config=config,
    #     session=db_config.session,
    # )
    # tts.tts_service().speak("Starting repository container.")

    repo = providers.Container(
        RepoContainer,
        config=config
    )
    # tts.tts_service().speak("Starting subject of law container.")

    sol = providers.Container(
        SolContainer,
        config=config
    )

    # tts.tts_service().speak("Starting database container.")

    db = providers.Container(
        DbContainer,
        config=config
    )

    # tts.tts_service().speak("Starting blueprint container.")


    bp = providers.Container(
            BpContainer,
            config=config,
            # session=db_config.session,
        )
    

    ent = providers.Container(
        EntContainer,
        config=config,
        BpContainer=bp,
    )

    step = providers.Container(
        StepContainer,
        config=config,
    )

    res = providers.Container(
        ResContainer,
        config=config,
    )

    file = providers.Container(
        FileContainer,
        config=config,
    )

    df = providers.Container(
        DfContainer,
        config=config,
        ResourceContainer=res,
        StepContainer=step,
        FileContainer=file
    )

    fe = providers.Container(
        FeContainer,
        config=config,
        StepContainer=step,
        DfContainer=df,
        DbContainer=db,
        BpContainer=bp,
        EntContainer=ent,
    )

    
    #     # entity_service=providers.DelegatedSingleton("apollonai.modules.bp.service.Service"),

    # --- Optional: Placeholders for future containers ---
    # step = providers.DelegatedSingleton("apollonai.modules.step.containers.StepContainer")
    # df = providers.DelegatedSingleton("apollonai.modules.df.containers.DfContainer")
    # db = providers.DelegatedSingleton("apollonai.modules.db.containers.DbContainer")
    # fe = providers.DelegatedSingleton("apollonai.modules.fe.containers.FeContainer")
    # res = providers.DelegatedSingleton("apollonai.modules.res.containers.ResContainer")