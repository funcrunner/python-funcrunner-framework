import json
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExecType(str, Enum):
    OPENAI_RUN = "openai.run"
    OPENAI_CHAT_COMPLETION = "openai.chat_completion"
    ANTHROPIC_MESSAGE = "anthropic.message"

class Message(BaseModel):
    id: str
    integration_id: str
    correlation_id: str
    object: ExecType
    body: dict
    expires_at: str
    visible_at: str
    in_flight: bool

class OpenAIRunBody(BaseModel):
    run_id: str
    thread_id: str

class ExecutionResult(BaseModel):
    execution_type: ExecType
    run_id: Optional[str] = None
    thread_id: Optional[str] = None
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