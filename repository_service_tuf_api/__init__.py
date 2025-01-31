# SPDX-FileCopyrightText: 2022-2023 VMware Inc
#
# SPDX-License-Identifier: MIT

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from celery import Celery
from dynaconf import Dynaconf
from dynaconf.loaders import redis_loader

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


@dataclass
class BootstrapState:
    bootstrap: bool
    state: Optional[str] = None
    task_id: Optional[str] = None


settings = Dynaconf(envvar_prefix="RSTUF")

settings_repository = Dynaconf(
    redis_enabled=True,
    redis={
        "host": settings.REDIS_SERVER.split("redis://")[1],
        "port": settings.get("REDIS_SERVER_PORT", 6379),
        "db": settings.get("REDIS_SERVER_DB_REPO_SETTINGS", 1),
        "decode_responses": True,
    },
)
secrets_settings = Dynaconf(
    envvar_prefix="SECRETS_RSTUF",
    environments=True,
)

# Celery setup
celery = Celery(__name__)
celery.conf.broker_url = settings.BROKER_SERVER
celery.conf.result_backend = (
    f"{settings.REDIS_SERVER}"
    f":{settings.get('REDIS_SERVER_PORT', 6379)}"
    f"/{settings.get('REDIS_SERVER_DB_RESULT', 0)}"
)
celery.conf.accept_content = ["json", "application/json"]
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.task_track_started = True
celery.conf.broker_heartbeat = 0
celery.conf.result_persistent = True
celery.conf.task_acks_late = True
celery.conf.broker_pool_limit = None
# celery.conf.broker_use_ssl
# https://github.com/repository-service-tuf/repository-service-tuf-api/issues/91


def pre_lock_bootstrap(task_id):
    """
    Add a pre-lock to the bootstrap repository settings.

    Add to the repository settings in Redis the lock as `pre-<task_id>`.

    Args:
        task_id: Task id generated by bootstrap
    """
    settings_data = settings_repository.as_dict(
        env=settings_repository.current_env
    )
    settings_data["BOOTSTRAP"] = f"pre-{task_id}"
    redis_loader.write(settings_repository, settings_data)


def release_bootstrap_lock():
    """
    Remove the pre-lock from repository settings.

    Move the repository settings BOOTSTRAP to None if not finished.
    """
    settings_data = settings_repository.as_dict(
        env=settings_repository.current_env
    )
    settings_data["BOOTSTRAP"] = None
    redis_loader.write(settings_repository, settings_data)


def bootstrap_state() -> BootstrapState:
    """
    Bootstrap state

    The bootstrap state is registered in Redis.
    Detailed definitions are available in
    https://repository-service-tuf.readthedocs.io/en/stable/devel/design.html#tuf-repository-settings  # noqa
    """

    # Reload the settings
    # The reload is required because the settings object is created in the
    # `app.py`'s initialization. The `settings_repository.get_fresh() doesn't
    # correctly reload because of that the settings_repository.reload() do
    # the job.
    settings_repository.reload()
    bootstrap = settings_repository.get_fresh("BOOTSTRAP")

    bootstrap_state = BootstrapState(bootstrap=False, state=None, task_id=None)
    if bootstrap is None:
        return bootstrap_state

    if len(bootstrap.split("-")) == 1:
        # This is a finished bootstrap. It only contains the `<task-id>``
        bootstrap_state.bootstrap = True
        bootstrap_state.state = "finished"
        bootstrap_state.task_id = bootstrap

        return bootstrap_state

    elif len(bootstrap.split("-")) == 2:
        # This is considered an intermediated state. It is not finished because
        # there is a `<state>-` like 'pre-<task_id>' or 'signing-<task_id>'.
        bootstrap_state.bootstrap = False
        bootstrap_state.state = bootstrap.split("-")[0]
        bootstrap_state.task_id = bootstrap.split("-")[1]

        return bootstrap_state


def get_task_id():
    return uuid4().hex


@celery.task(name="app.repository_service_tuf_worker")
def repository_metadata(action, payload):
    logging.debug(f"New tasks action submitted {action}")
    return True
