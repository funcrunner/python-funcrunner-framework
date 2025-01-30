def test_auto_update(application, assistant):
    application.assistant_id = assistant.id
    application._configure_assistant()


def test_auto_tools(application):
    application._configure_auto_tools()
