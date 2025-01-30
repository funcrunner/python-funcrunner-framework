import inspect
import json
import os
import signal
import sys
import threading
import time
from functools import reduce
from http.server import HTTPServer
from typing import Callable, Dict, Optional

import requests
import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from funcrunner.exceptions import AssistantException
from funcrunner.health import HealthHandler
from funcrunner.models import Message, FunctionExecution, ExecutionResult, ExecType
from funcrunner.tool_definitions import build_tool_definition


class FuncRunnerApp:
    def __init__(self,
                 api_key: Optional[str] = None,
                 assistant_id: Optional[str] = None,
                 auto_update: bool = True,
                 health_port: int = 8000,
                 polling_interval: float = 5.0,
                 enable_local_services: bool = False):
        self.function_registry: Dict[str, Callable] = {}
        self.cron_registry: Dict[str, Callable] = {}
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.logger = structlog.get_logger()
        self.api_key = api_key if api_key else os.environ.get("FUNCRUNNER_API_KEY")
        self.polling_interval = polling_interval
        self.assistant_id = assistant_id
        self.auto_update = auto_update
        self.health_port = health_port
        self.http_server = None
        self.http_thread = None

        if enable_local_services:
            self.proxy_host = "http://localhost:8080"
            self.queue_host = "http://localhost:8081"
        else:
            self.proxy_host = "https://proxy.funcrunner.com"
            self.queue_host = "https://queue.funcrunner.com"

        if self.api_key is None:
            self.logger.critical(
                "Missing Func Runner API key. Set 'FUNCRUNNER_API_KEY' environment variable or use 'api_key='")
            raise ValueError(
                "Missing func runner API key. Set 'FUNCRUNNER_API_KEY' environment variable or use 'api_key='.")

    def _start_health_server(self):
        def serve():
            self.http_server = HTTPServer(("0.0.0.0", self.health_port), HealthHandler)
            self.logger.info(f"Health check endpoint listening on port {self.health_port}")
            try:
                self.http_server.serve_forever()
            except Exception as e:
                self.logger.error(f"Health server error: {e}")

        self.http_thread = threading.Thread(target=serve)
        self.http_thread.start()

    def _stop_health_server(self):
        if self.http_server:
            self.logger.info("Shutting down health server...")
            self.http_server.shutdown()
            self.http_server.server_close()
            self.http_thread.join()
            self.logger.info("Health server shut down.")

    def _signal_handler(self, sig, frame):
        self.logger.info("Signal received. Shutting down...")
        self.is_running = False
        self._stop_health_server()
        sys.exit(0)

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

    def schedule(self, cron_expression: str):
        """Decorator for scheduling functions."""

        def decorator(func: Callable):
            self.logger.info(f"Registering scheduled function '{func.__name__}' with cron '{cron_expression}'")
            trigger = CronTrigger.from_crontab(cron_expression)
            self.scheduler.add_job(func, trigger)
            self.cron_registry[func.__name__] = cron_expression
            return func

        return decorator

    def _fetch_run_data(self, message: Message):
        url = f"{self.proxy_host}/v1/threads/{message.body.get("thread_id")}/runs/{message.body.get("run_id")}"
        self.logger.debug(f"Fetching run data from URL: {url}", message_id=message.id, run_id=message.body.get("run_id"),
                          correlation_id=message.correlation_id)
        response = self._make_request('get', url, message)
        if response is not None and response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON response", url=url, error=str(e),
                                  correlation_id=message.correlation_id)
        return None

    def _generate_function_spec(self, registry_key: str, func: Callable) -> dict:
        """Generates OpenAI-compatible function spec for a registered function."""
        self.logger.info(f"Generating function spec for function: '{func.__name__}'")
        definition = build_tool_definition(func=func, override_name=registry_key)

        return definition.model_dump(by_alias=True, exclude_none=True)

    def _configure_auto_tools(self):
        """Registers all functions in function_registry with a Func Runner."""
        self.logger.info("Configuring auto tools...", assistant_id=self.assistant_id)

        function_specs = [self._generate_function_spec(key, func) for key, func in self.function_registry.items()]

        url = f"{self.proxy_host}/fr/tools"
        update_resp = self._make_request('post', url, data=json.dumps(function_specs))
        if update_resp.status_code != 200:
            self.logger.error(f"Failed to update auto tools", url=url, status_code=update_resp.status_code,
                              error=update_resp.text)
            raise AssistantException(f"Failed to update auto tools with function specifications: {update_resp.text}")

        self.logger.info("Finished updating auto tools...", assistant_id=self.assistant_id)


    def _configure_assistant(self):
        """Registers all functions in function_registry with an OpenAI assistant."""
        self.logger.info("Updating assistant functions...", assistant_id=self.assistant_id)

        url = f"{self.proxy_host}/v1/assistants/{self.assistant_id}"
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

        function_specs = [self._generate_function_spec(key, func) for key, func in self.function_registry.items()]
        assistant["tools"] = updated_tools + function_specs

        for ro_attr in ["id", "object", "created_at"]:
            if ro_attr in assistant:
                del assistant[ro_attr]

        # If some values are none on the original record OpenAI will raise an error.
        for none_attr in ["name", "instructions"]:
            if none_attr in assistant and assistant[none_attr] is None:
                del assistant[none_attr]

        if "description" in assistant and assistant["description"] is None:
            del assistant["description"]

        update_resp = self._make_request('post', url, data=json.dumps(assistant))
        if update_resp.status_code != 200:
            self.logger.error(f"Failed to update assistant", url=url, status_code=update_resp.status_code,
                              error=update_resp.text)
            raise AssistantException(f"Failed to update the assistant with function specifications: {update_resp.text}")

        self.logger.info("Finished updating assistant functions...", assistant_id=self.assistant_id)

    @staticmethod
    def _extract_run_tool_calls(run: dict):
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
                              message=message.model_dump(), correlation_id=message.correlation_id)
            return f"Argument error when calling '{fe.name}': {str(e)}"
        except Exception as e:
            self.logger.error(f"nhandled exception when calling function", function_name=fe.name, error=str(e),
                              message=message.model_dump(), correlation_id=message.correlation_id)
            return f"Unhandled exception when calling function '{fe.name}': {str(e)}"

    def _process_queue_message(self, message: Message) -> Optional[ExecutionResult]:
        self.logger.info(f"Processing queue message", message_id=message.id, correlation_id=message.correlation_id)

        function_executions: list[FunctionExecution] = []
        result = ExecutionResult(execution_type=message.object)

        match message.object:
            case ExecType.OPENAI_RUN:
                run = self._fetch_run_data(message)
                if not run:
                    return

                tool_calls = self._extract_run_tool_calls(run)
                if not tool_calls:
                    self.logger.info(f"No tool calls found for run", run_id=message.body.get("run_id"),
                                     correlation_id=message.correlation_id)

                [function_executions.append(x) for x in self._process_tool_calls(tool_calls)]

                result.run_id = message.body.get("run_id")
                result.thread_id = message.body.get("thread_id")

            case ExecType.OPENAI_CHAT_COMPLETION:
                if message.body["choices"][0]["message"]["tool_calls"]:
                    tool_calls = [x for x in message.body["choices"][0]["message"]["tool_calls"]]
                    [function_executions.append(x) for x in self._process_tool_calls(tool_calls)]
                else:
                    self.logger.info(f"No tool calls found for chat completion", id=message.body["id"],
                                     correlation_id=message.correlation_id)

        for fe in function_executions:
            r = self._execute_function(fe, message)
            match message.object:
                case ExecType.OPENAI_RUN:
                    if isinstance(r, str) or r is None:
                        result.tool_outputs.append({"tool_call_id": fe.tool_call_id, "output": r})
                    else:
                        self.logger.error(
                            f"{fe.name} returned non-string value. openai expects functions to return a string.")
                        continue
                case ExecType.OPENAI_CHAT_COMPLETION:
                    if isinstance(r, str) or r is None:
                            result.tool_outputs.append({"role": "tool", "tool_call_id": fe.tool_call_id, "content": r})
                    else:
                        self.logger.error(
                            f"{fe.name} returned non-string value. openai expects functions to return a string.")
                        continue
        return result

    def _submit_openai_run_results(self, result: ExecutionResult) -> bool:
        self.logger.info(f"Submitting function results", run_id=result.run_id, correlation_id=result.thread_id)
        url = f"{self.proxy_host}/v1/threads/{result.thread_id}/runs/{result.run_id}/submit_tool_outputs"
        resp = self._make_request('post', url, None, result.dump_submission_response())
        if resp is None or resp.status_code != 200:
            return False
        self.logger.info(f"Successfully submitted function results", run_id=result.run_id,
                         correlation_id=result.thread_id)
        return True

    def _submit_openai_chat_results(self, result: ExecutionResult, chat: dict) -> bool:
        self.logger.info(f"Submitting chat function results", correlation_id=result.thread_id)
        url = f"{self.proxy_host}/fr/chat/completions/{chat.get("id")}"
        body = {
            "messages": result.tool_outputs
        }
        resp = self._make_request('post', url, None, data=json.dumps(body))
        if resp is None or resp.status_code != 200:
            self.logger.error(f"Failed to send results with error {resp.text}", correlation_id=result.thread_id)
            return False
        self.logger.info(f"Successfully submitted function results", correlation_id=result.thread_id)
        return True

    def _dequeue_message(self) -> Optional[Message]:
        resp = self._make_request('get', f"{self.queue_host}/messages")
        if resp is None or resp.status_code != 200:
            return None
        messages = resp.json()
        if len(messages) == 0:
            return None
        self.logger.info(f"Message dequeued", message_id=messages[0].get("id"),
                         correlation_id=messages[0].get("correlation_id"))
        return Message(**messages[0])

    def _delete_message(self, message: Message) -> Optional[Message]:
        message_id = message.id
        correlation_id = message.correlation_id

        self.logger.info(f"Deleting message from the queue", message_id=message_id, correlation_id=correlation_id)
        resp = self._make_request('delete', f"{self.queue_host}/messages/{message_id}")
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
        if self.cron_registry:
            self.logger.info(f"Scheduled functions: {', '.join(self.cron_registry.keys())}")
        else:
            self.logger.info("No scheduled tasks registered.")

        self.is_running = True
        self.scheduler.start()

        if self.auto_update:
            self._configure_auto_tools()
        if self.auto_update and self.assistant_id:
            self._configure_assistant()

        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start health check server
        self._start_health_server()

        try:
            while self.is_running:
                message = self._dequeue_message()

                exec_result = None
                if message:
                    exec_result = self._process_queue_message(message)

                success = False
                if exec_result:
                    match message.object:
                        case ExecType.OPENAI_RUN:
                            success = self._submit_openai_run_results(exec_result)
                        case ExecType.OPENAI_CHAT_COMPLETION:
                            success = self._submit_openai_chat_results(exec_result, message.body)
                if success:
                    self._delete_message(message)

                time.sleep(self.polling_interval)
        except KeyboardInterrupt:
            self.logger.info("Shutting down gracefully...")
            self.is_running = False

    # Function to stop the app loop
    def stop(self):
        self._stop_health_server()
        self.scheduler.shutdown()
        self.is_running = False
        self.logger.info("Func Runner application stopped")
