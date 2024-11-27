import os


def test_auto_update(application, assistant):
    application.assistant_id = assistant.id
    application.api_key = os.getenv("FUNCRUNNER_API_KEY")
    application._configure_assistant()