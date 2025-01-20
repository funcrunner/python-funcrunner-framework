import requests

from funcrunner.app import FuncRunnerApp
from funcrunner.models import Message, OpenAIRunBody, ExecType


def test_health_check(application):
    app: FuncRunnerApp = application
    app.health_port = 7777
    app._start_health_server()

    r = requests.get("http://localhost:7777/up")
    assert r.status_code == 200

    app._stop_health_server()


def test_application(application):
    queue_items = [
        Message(
            id="1",
            object=ExecType.OPENAI_RUN,
            body={"run_id": "run1", "thread_id": "thread1"},
            integration_id="int1",
            correlation_id="corr1",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="2",
            object=ExecType.OPENAI_RUN,
            body={"run_id": "run2", "thread_id": "thread2"},
            integration_id="int2",
            correlation_id="corr2",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="3",
            object=ExecType.OPENAI_RUN,
            body={"run_id": "run3", "thread_id": "thread3"},
            integration_id="int3",
            correlation_id="corr3",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="4",
            object=ExecType.OPENAI_RUN,
            body={"run_id": "run4", "thread_id": "thread4"},
            integration_id="int4",
            correlation_id="corr4",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="5",
            object=ExecType.OPENAI_RUN,
            body={"run_id": "run5", "thread_id": "thread5"},
            integration_id="int5",
            correlation_id="corr5",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        ),
        Message(
            id="6",
            object=ExecType.OPENAI_RUN,
            body={"run_id": "run6", "thread_id": "thread6"},
            integration_id="int6",
            correlation_id="corr6",
            expires_at="2024-12-31T23:59:59Z",
            visible_at="2024-11-10T12:00:00Z",
            in_flight=False
        )
    ]

    # Mock run data for tool calls
    mock_run_data = [
        {"required_action": {"submit_tool_outputs": {
            "tool_calls": [{"function": {"name": "greet", "arguments": "{\"name\": \"Alice\"}"}, "id": "tc1"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [
            {"function": {"name": "add_numbers", "arguments": "{\"a\": 5, \"b\": 3.2}"}, "id": "tc2"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [
            {"function": {"name": "check_status", "arguments": "{\"is_active\": true}"}, "id": "tc3"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [
            {"function": {"name": "list_summary", "arguments": "{\"items\": [\"apple\", \"banana\", \"cherry\"]}"},
             "id": "tc4"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [
            {"function": {"name": "user_info", "arguments": "{\"user\": {\"username\": \"johndoe\", \"age\": 30}}"},
             "id": "tc5"}]}}},
        {"required_action": {"submit_tool_outputs": {"tool_calls": [
            {"function": {"name": "review_status", "arguments": "{\"status\": \"approved\"}"}, "id": "tc6"}]}}}
    ]

    # Step 4: Mock the _fetch_run_data method to return the mock run data
    application._fetch_run_data = lambda message: mock_run_data[int(message.id) - 1] if int(message.id) <= len(
        mock_run_data) else None

    # Step 5: Process each Message object and get the results
    for message in queue_items:
        result = application._process_queue_message(message)

        # Step 6: Verify the results are as expected
        assert result is not None, f"Result for Message ID {message.id} should not be None."
        print(f"Message ID '{message.id}' processed successfully with result: {result}")

    # Step 7: Test function spec generation for all registered functions
    functions_to_test = ["greet", "greet_in_spanish", "add_numbers", "check_status", "list_summary", "user_info",
                         "review_status"]
    for func in functions_to_test:
        kallable = application.function_registry[func]
        spec = application._generate_function_spec(func, kallable)
        assert spec is not None, f"Function spec for '{kallable.__name__}' should not be None."
        print(f"Function spec for '{kallable.__name__}' generated successfully: {spec}")
