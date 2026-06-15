# factory.py

from backend.config.settings import settings
from backend.integrations.nlp.base import NLPBackend
from backend.integrations.nlp.client import HFClient  # client.py
from backend.integrations.nlp.local import LocalNLPClient  # local.py


def get_nlp_backend() -> NLPBackend:
    match settings.nlp_backend:
        case "local":
            return LocalNLPClient()
        case "remote":
            return HFClient()
        case _:
            return LocalNLPClient()  # Default
