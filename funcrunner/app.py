import inspect
import json
import os
import time
from enum import Enum
from functools import reduce
from typing import Any, Callable, Dict, Optional

import requests
import structlog
from pydantic import BaseModel


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
    tool_outputs: list[Dict[str, str]] = []

    def dump_submission_response(self):
        return json.dumps({"tool_outputs": self.tool_outputs})


class FunctionExecution(BaseModel):
    name: str
    arguments: dict[str, Any]
    tool_call_id: str


class FunctionExecutionPayload(BaseModel):
    thread_id: str
    run_id: str
    function_executions: list[FunctionExecution] = []


class FuncRunnerApp:
    def __init__(self,
                 api_key: Optional[str] = None,
                 assistant_id: Optional[str] = None,
                 auto_update: bool = True,
                 polling_interval: float = 5.0):
        self.function_registry: Dict[str, Callable] = {}
        self.is_running = False
        self.logger = structlog.get_logger()
        self.api_key = api_key if api_key else os.environ.get("FUNCRUNNER_API_KEY")
        self.polling_interval = polling_interval
        self.assistant_id = assistant_id
        self.auto_update = auto_update

        if self.api_key is None:
            self.logger.critical(
                "Missing Func Runner API key. Set 'FUNCRUNNER_API_KEY' environment variable or use 'api_key='")
            raise ValueError(
                "Missing func runner API key. Set 'FUNCRUNNER_API_KEY' environment variable or use 'api_key='.")

    # Function decorator for registering callable functions
    def function(self, name: Optional[str] = None):
        # Check if `name` is actually the function to be decorated (no parentheses case)
        if callable(name):
            func = name
            func_name = func.__name__
            self.function_registry[func_name] = func
            self.logger.info(f"Registering function: '{func_name}'")
            return func  # Return the function directly

        # Otherwise, return the decorator function for the parentheses case
        def decorator(func: Callable):
            func_name = name or func.__name__
            self.function_registry[func_name] = func
            self.logger.info(f"Registering function: '{func_name}'")
            return func

        return decorator

    def _fetch_run_data(self, message: Message):
        url = f"https://proxy.funcrunner.com/v1/threads/{message.thread_id}/runs/{message.run_id}"
        self.logger.debug(f"Fetching run data from URL: {url}", message_id=message.id, run_id=message.run_id,
                          correlation_id=message.correlation_id)
        response = self._make_request('get', url, message)
        if response is not None and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON response", url=url, error=str(e),
                                  correlation_id=message.correlation_id)
        return None

    def _generate_function_spec(self, func: Callable) -> dict:
        """Generates OpenAI-compatible function spec for a registered function."""
        self.logger.info(f"Generating function spec for function: '{func.__name__}'")

        func_name = func.__name__
        description = func.__doc__ or f"Function {func_name} with no description."

        # Generate JSON schema for parameters
        parameters_schema = {"type": "object", "properties": {}}
        required_params = []

        signature = inspect.signature(func)

        # Mapping Python types to OpenAI-compatible JSON types
        type_mapping = {
            str: "string",
            int: "number",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            Any: "object"
        }

        for param_name, param in signature.parameters.items():
            param_type = param.annotation if param.annotation != inspect.Parameter.empty else str

            # Check for Enum types
            if isinstance(param_type, type) and issubclass(param_type, Enum):
                json_type = "string"
                enum_values = [e.value for e in param_type]
                parameters_schema["properties"][param_name] = {
                    "type": json_type,
                    "enum": enum_values,
                    "description": f"The {param_name} parameter (enum)."
                }
            else:
                # Use type mapping for other types
                json_type = type_mapping.get(param_type, "string")

                if param_type == list:
                    json_type = {"type": "array", "items": {"type": "string"}}

                if param_type == dict:
                    json_type = "object"

                parameters_schema["properties"][param_name] = {
                    "type": json_type,
                    "description": f"The {param_name} parameter."
                }

            # If a parameter is required and doesn't have a default, add it to the required list
            if param.default == inspect.Parameter.empty:
                required_params.append(param_name)

        if required_params:
            parameters_schema["required"] = required_params

        parameters_schema["additionalProperties"] = False  # Enforces strict parameter validation

        # Create function specification compatible with OpenAI
        spec = {
            "type": "function",
            "function": {
                "name": func_name,
                "description": description,
                "parameters": parameters_schema,
                "strict": True
            }
        }
        self.logger.debug(f"Generated function spec for function: '{func_name}'", spec=spec)
        return spec

    def _configure_assistant(self):
        """Registers all functions in function_registry with an OpenAI assistant."""
        self.logger.info("Updating assistant functions...", assistant_id=self.assistant_id)

        url = f"https://proxy.funcrunner.com/v1/assistants/{self.assistant_id}"
        resp = self._make_request('get', url)

        if resp.status_code != 200:
            self.logger.error(f"Failed to fetch assistant", url=url, error=resp.text)
            return

        assistant = resp.json()

        updated_tools = []
        for tool in assistant.get("tools", []):
            for target_tool in ["code_interpreter", "file_search"]:
                if target_tool in tool:
                    updated_tools.append(tool)
                    break

        function_specs = [self._generate_function_spec(func) for func in self.function_registry.values()]
        assistant["tools"] = updated_tools + function_specs

        for ro_attr in ["id", "object", "created_at"]:
            if ro_attr in assistant:
                del assistant[ro_attr]

        if "description" in assistant and assistant["description"] is None:
            del assistant["description"]

        update_resp = self._make_request('post', url, data=json.dumps(assistant))
        if update_resp.status_code != 200:
            self.logger.error(f"Failed to update assistant", url=url, status_code=update_resp.status_code,
                              error=update_resp.text)

        self.logger.info("Finished updating assistant functions...", assistant_id=self.assistant_id)

    @staticmethod
    def _extract_tool_calls(run: dict):
        tool_calls = reduce(lambda d, k: d.get(k, {}), ["required_action", "submit_tool_outputs", "tool_calls"], run)
        if not isinstance(tool_calls, list):
            tool_calls = []
        return tool_calls

    def _process_tool_calls(self, tool_calls: list):
        function_executions = []
        for tool_call in tool_calls:
            try:
                name = tool_call["function"]["name"]
                self.logger.info(f"Processing function call request", function_name=name, tool_call_id=tool_call["id"])
                arguments = json.loads(tool_call["function"]["arguments"])
                fe = FunctionExecution(name=name, arguments=arguments, tool_call_id=tool_call["id"])
                function_executions.append(fe)
            except (KeyError, json.JSONDecodeError) as e:
                self.logger.error(f"Invalid tool call format", tool_call=tool_call, error=str(e))
        return function_executions

    def _execute_function(self, fe: FunctionExecution, message: Message):
        if fe.name not in self.function_registry:
            self.logger.error(f"Function not found in registry", function_name=fe.name,
                              available_functions=list(self.function_registry.keys()), message=message.dict(),
                              correlation_id=message.correlation_id)
            raise NotImplementedError(f"Function '{fe.name}' not found in registry.")

        function = self.function_registry[fe.name]
        signature = inspect.signature(function)

        try:
            bound_args = signature.bind(**fe.arguments)
            bound_args.apply_defaults()
            self.logger.info(f"Executing function", function_name=fe.name, arguments=fe.arguments,
                             correlation_id=message.correlation_id)
            return function(*bound_args.args, **bound_args.kwargs)
        except TypeError as e:
            self.logger.error(f"Argument error when calling function", function_name=fe.name, error=str(e),
                              message=message.dict(), correlation_id=message.correlation_id)
            raise ValueError(f"Argument error when calling '{fe.name}': {str(e)}")

    def _process_queue_message(self, message: Message) -> Optional[RunResult]:
        self.logger.info(f"Processing queue message", message_id=message.id, correlation_id=message.correlation_id)
        run = self._fetch_run_data(message)
        if not run:
            return

        tool_calls = self._extract_tool_calls(run)
        if not tool_calls:
            self.logger.info(f"No tool calls found for run", run_id=message.run_id,
                             correlation_id=message.correlation_id)

        function_executions = self._process_tool_calls(tool_calls)

        result = RunResult(run_id=message.run_id, thread_id=message.thread_id)

        for fe in function_executions:
            r = self._execute_function(fe, message)
            if isinstance(r, str) or r is None:
                result.tool_outputs.append({"tool_call_id": fe.tool_call_id, "output": r})
            else:
                self.logger.error(f"{fe.name} returned non-string value. openai expects functions to return a string.")
                continue

        return result

    def _submit_function_results(self, result: RunResult) -> bool:
        self.logger.info(f"Submitting function results", run_id=result.run_id, correlation_id=result.thread_id)
        url = f"https://proxy.funcrunner.com/v1/threads/{result.thread_id}/runs/{result.run_id}/submit_tool_outputs"
        resp = self._make_request('post', url, None, result.dump_submission_response())
        if resp is None or resp.status_code != 200:
            return False
        self.logger.info(f"Successfully submitted function results", run_id=result.run_id,
                         correlation_id=result.thread_id)
        return True

    def _dequeue_message(self) -> Optional[Message]:
        resp = self._make_request('get', "https://queue.funcrunner.com/messages")
        if resp is None or resp.status_code != 200:
            return None
        messages = resp.json()
        if len(messages) == 0:
            return None
        self.logger.info(f"Message dequeued", message_id=messages[0].get("id"),
                         correlation_id=messages[0].get("correlation_id"))
        return Message(**messages[0])

    def _delete_message(self, message_id, correlation_id) -> Optional[Message]:
        self.logger.info(f"Deleting message from the queue", message_id=message_id, correlation_id=correlation_id)
        resp = self._make_request('delete', f"https://queue.funcrunner.com/messages/{message_id}")
        if resp is None or resp.status_code != 200:
            return None
        self.logger.info(f"Successfully deleted queue message", message_id=message_id, correlation_id=correlation_id)

    def _make_request(self, method: str, url: str, message: Optional[Message] = None, data: Optional[str] = None):
        try:
            headers = {"Authorization": "Bearer " + self.api_key}
            if method.lower() == 'get':
                return requests.get(url, headers=headers)
            elif method.lower() == 'post':
                return requests.post(url, headers=headers, data=data)
            elif method.lower() == 'delete':
                return requests.delete(url, headers=headers)
            else:
                self.logger.error(f"Unsupported HTTP method", method=method)
                return None
        except requests.RequestException as e:
            self.logger.error(f"HTTP request failed", method=method, url=url, error=str(e),
                              correlation_id=message.correlation_id if message else "N/A")
            return None

    # The main loop to pull from a queue and process items
    def run(self):
        self.logger.info("Starting Func Runner application...")
        if self.function_registry:
            self.logger.info(f"Available functions: {', '.join(self.function_registry.keys())}")
        else:
            self.logger.info("No functions registered.")
        self.is_running = True

        if self.auto_update and self.assistant_id:
            self._configure_assistant()

        try:
            while self.is_running:
                message = self._dequeue_message()

                run_result = None
                if message:
                    run_result = self._process_queue_message(message)

                success = False
                if run_result:
                    success = self._submit_function_results(run_result)
                if success:
                    self._delete_message(message.id, message.correlation_id)

                time.sleep(self.polling_interval)
        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
            self.is_running = False

    # Function to stop the app loop
    def stop(self):
        self.is_running = False
        self.logger.info("Func Runner application stopped")
