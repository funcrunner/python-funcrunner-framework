import os


def test_auto_update(application, assistant):
    application.assistant_id = assistant.id
    application._configure_assistant()


def test_function_specs(application):
    def test_list_method(some_list: list[str]):
        pass

    spec = application._generate_function_spec("test_list_method", test_list_method)
    assert spec == {
        "function": {
            "description": "Function test_list_method with no description.",
            "name": "test_list_method",
            "parameters": {
                "additionalProperties": False,
                "properties": {
                    "some_list": {
                        "description": "The some_list parameter.",
                        "items": {
                            "type": "string"
                        },
                        "type": "array"
                    }
                },
                "required": ["some_list"],
                "type": "object"
            },
            "strict": True
        },
        "type": "function"
    }

    def test_list_of_objects(some_list: list[dict]):
        pass

    spec = application._generate_function_spec("test_list_of_objects", test_list_of_objects)
    assert spec == {
        "function": {
            "description": "Function test_list_of_objects with no description.",
            "name": "test_list_of_objects",
            "parameters": {
                "additionalProperties": False,
                "properties": {
                    "some_list": {
                        "description": "The some_list parameter.",
                        "items": {
                            "type": "object"
                        },
                        "type": "array"
                    }
                },
                "required": ["some_list"],
                "type": "object"
            },
            "strict": True
        },
        "type": "function"
    }

    def test_dict_method(some_dict: dict):
        pass

    spec = application._generate_function_spec("test_dict_method", test_dict_method)
    assert spec == {
        "function": {
            "description": "Function test_dict_method with no description.",
            "name": "test_dict_method",
            "parameters": {
                "additionalProperties": False,
                "properties": {
                    "some_dict": {
                        "description": "The some_dict parameter.",
                        "type": "object"
                    }
                },
                "required": ["some_dict"],
                "type": "object"
            },
            "strict": True
        },
        "type": "function"
    }
