from fastapi import APIRouter, Depends, Security

from tuf_repository_service_api import SCOPES_NAMES, tasks
from tuf_repository_service_api.token import validate_token

router = APIRouter(
    prefix="/task",
    tags=["v1"],
    responses={404: {"description": "Not found"}},
)


@router.get(
    "/",
    summary=("Get task state. " f"Scope: {SCOPES_NAMES.read_tasks.value}"),
    description=(
        "Get Repository Metadata task state. "
        "The state is according with Celery tasks: "
        "`PENDING` the task still not processed or unknown/inexistent task. "
        "`RECEIVED` task is reveived by the broker server. "
        "`PRE_RUN` the task will start by tuf-repository-service-worker. "
        "`RUNNING` the task is in execution. "
        "`FAILURE` the task failed to executed. "
        "`SUCCESS` the task execution is finished. "
    ),
    response_model=tasks.Response,
    response_model_exclude_none=True,
)
def get(
    params: tasks.GetParameters = Depends(),
    _user=Security(validate_token, scopes=[SCOPES_NAMES.read_tasks.value]),
):
    return tasks.get(params.task_id)
