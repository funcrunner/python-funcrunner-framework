from funcrunner.app import FuncRunnerApp, Message
from typing import Any
from enum import Enum


# Define an Enum for testing
class StatusEnum(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def test_application():
    # Step 1: Create an instance of the app
    app = FuncRunnerApp(api_key="testkey")

    # Step 2: Register different types of functions using the app's decorator

    # Function with a string parameter
    @app.function()
    def greet(name: str):
        return f"Hello, {name}!"

    # Function with a number parameter
    @app.function()
    def add_numbers(a: int, b: float):
        return a + b

    # Function with a boolean parameter
    @app.function()
    def check_status(is_active: bool):
        return "Active" if is_active else "Inactive"

    # Function with an array parameter
    @app.function()
    def list_summary(items: list[str]):
        return f"You have {len(items)} items."

    # Function with an object parameter as a dict
    @app.function()
    def user_info(user: dict[str, Any]):
        return f"User {user['username']} is {user['age']} years old."

    # Function with an enum parameter
    @app.function()
    def review_status(status: StatusEnum):
        if isinstance(status, str):
            status = StatusEnum(status)
        return f"The review status is {status.value}."

    # Step 3: Create mock Message objects for each function to be processed by the app
    queue_items = [
        Message(
            id="1",
            run_id="run1",
            thread_id="thread1",
            integration_id="int1",
            correlation_id="corr1",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="2",
            run_id="run2",
            thread_id="thread2",
            integration_id="int2",
            correlation_id="corr2",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="3",
            run_id="run3",
            thread_id="thread3",
            integration_id="int3",
            correlation_id="corr3",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="4",
            run_id="run4",
            thread_id="thread4",
            integration_id="int4",
            correlation_id="corr4",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="5",
            run_id="run5",
            thread_id="thread5",
            integration_id="int5",
            correlation_id="corr5",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="6",
            run_id="run6",
            thread_id="thread6",
            integration_id="int6",
            correlation_id="corr6",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        )
    ]

    # Mock run data for tool calls
    mock_run_data = [
        {"required_action": {"submit_tool_outputs": {"tool_calls": [{"function": {"name": "greet", "arguments": "{\"name\": \"Alice\"}"}, "id": "tc1"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [{"function": {"name": "add_numbers", "arguments": "{\"a\": 5, \"b\": 3.2}"}, "id": "tc2"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [{"function": {"name": "check_status", "arguments": "{\"is_active\": true}"}, "id": "tc3"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [{"function": {"name": "list_summary", "arguments": "{\"items\": [\"apple\", \"banana\", \"cherry\"]}"}, "id": "tc4"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [{"function": {"name": "user_info", "arguments": "{\"user\": {\"username\": \"johndoe\", \"age\": 30}}"}, "id": "tc5"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [{"function": {"name": "review_status", "arguments": "{\"status\": \"approved\"}"}, "id": "tc6"}]}}}
    ]

    # Step 4: Mock the _fetch_run_data method to return the mock run data
    app._fetch_run_data = lambda message: mock_run_data[int(message.id) - 1] if int(message.id) <= len(mock_run_data) else None

    # Step 5: Process each Message object and get the results
    for message in queue_items:
        result = app._process_queue_message(message)

        # Step 6: Verify the results are as expected
        assert result is not None, f"Result for Message ID {message.id} should not be None."
        print(f"Message ID '{message.id}' processed successfully with result: {result}")

    # Step 7: Test function spec generation for all registered functions
    functions_to_test = [greet, add_numbers, check_status, list_summary, user_info, review_status]
    for func in functions_to_test:
        spec = app._generate_function_spec(func)
        assert spec is not None, f"Function spec for '{func.__name__}' should not be None."
        print(f"Function spec for '{func.__name__}' generated successfully: {spec}")