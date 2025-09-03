import logging

from infrahouse_core.logging import setup_logging

DEFAULT_PROGRESS_INTERVAL = 10
UBUNTU_CODENAME = "noble"

LOG = logging.getLogger()
TERRAFORM_ROOT_DIR = "test_data"

setup_logging(LOG, debug=True)
