from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.tasks import create_broker
from app.tasks import setup_worker

settings = get_settings()
configure_logging(settings.log_level, settings.log_json)
broker = setup_worker(create_broker(settings), settings)
