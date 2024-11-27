import json
from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str
    run_id: str
    thread_id: str
    integration_id: str
    correlation_id: str
    expires_at: str
    visible_at: str
    in_flight: bool


class RunResult(BaseModel):
    run_id: str
    thread_id: str
    tool_outputs: list[dict[str, str]] = Field(default_factory=list)

    def dump_submission_response(self):
        return json.dumps({"tool_outputs": self.tool_outputs})


class FunctionExecution(BaseModel):
    name: str
    arguments: dict[str, Any]
    tool_call_id: str


class FunctionExecutionPayload(BaseModel):
    thread_id: str
    run_id: str
    function_executions: list[FunctionExecution] = Field(default_factory=list)