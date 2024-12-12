import inspect
from enum import Enum
from typing import Callable, Any, Optional, get_origin, get_args, Type, Union

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ParamType(Enum):
    STRING = "string"
    INTEGER = "number"
    FLOAT = "number"
    BOOLEAN = "boolean"
    LIST = "array"
    ENUM = "enum"
    OBJECT = "object"


class PropertyDefinition(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    type: str
    description: str = "Description not given"
    items: Optional["PropertyDefinition"] = None
    enum: Optional[list[str]] = None


class ParameterPropertyDefinition(BaseModel):
    """
    This model is used for properties that are of type 'object'. It is similar to ParameterDefinition but with an
    added description and can be seen more than once in a function definition.
    """
    model_config = ConfigDict(alias_generator=to_camel)

    type: str = "object"
    description: str = "Description not given"
    properties: dict[str, Union[PropertyDefinition, "ParameterPropertyDefinition"]] = {}
    required: list[str] = Field(default_factory=list)
    additional_properties: bool = False


class ParameterDefinition(BaseModel):
    """
    This model is the root parameter model for a function specification, it should only be seen once per function
    definition.
    """
    model_config = ConfigDict(alias_generator=to_camel)

    type: str = "object"
    properties: dict[str, Union[PropertyDefinition, ParameterPropertyDefinition]] = {}
    required: list[str] = Field(default_factory=list)
    additional_properties: bool = False


class FunctionDefinition(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    name: str
    description: str
    strict: bool = True
    parameters: ParameterDefinition = ParameterDefinition()


class ToolDefinition(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    type: str = "function"
    function: FunctionDefinition


def build_tool_definition(func: Callable, override_name: str = None) -> ToolDefinition:
    signature = inspect.signature(func)

    func_definition = FunctionDefinition(
        name=override_name or func.__name__,
        description=func.__doc__ or "Description not given"
    )

    for param_name, param in signature.parameters.items():
        param_type = param.annotation if param.annotation != inspect.Parameter.empty else str
        mapped_param_type = __map_param_type(param_type)

        # Add the parameter name to the required list
        func_definition.parameters.required.append(param_name)

        # Build the property definition for current parameter
        match mapped_param_type:
            case ParamType.STRING:
                func_definition.parameters.properties[param_name] = build_string_property(param)
            case ParamType.INTEGER:
                func_definition.parameters.properties[param_name] = build_number_property(param)
            case ParamType.FLOAT:
                func_definition.parameters.properties[param_name] = build_number_property(param)
            case ParamType.BOOLEAN:
                func_definition.parameters.properties[param_name] = build_boolean_property(param)
            case ParamType.LIST:
                func_definition.parameters.properties[param_name] = build_array_property(param)
            case ParamType.OBJECT:
                func_definition.parameters.properties[param_name] = build_object_property(param)
            case ParamType.ENUM:
                func_definition.parameters.properties[param_name] = build_enum_property(param)
            case _:
                raise Exception(f"Unhandled parameter type: {param_type}")

    return ToolDefinition(function=func_definition)


def build_string_property(prop: inspect.Parameter) -> PropertyDefinition:
    return PropertyDefinition(type="string")


def build_number_property(prop: inspect.Parameter) -> PropertyDefinition:
    return PropertyDefinition(type="number")


def build_boolean_property(prop: inspect.Parameter) -> PropertyDefinition:
    return PropertyDefinition(type="boolean")


def build_object_property(prop: inspect.Parameter) -> ParameterPropertyDefinition:
    return ParameterPropertyDefinition(type="object")


def build_array_property(prop: inspect.Parameter) -> PropertyDefinition:
    args = get_args(prop.annotation)
    if len(args) == 1:
        items = build_property(args[0])
    else:
        items = {}

    return PropertyDefinition(type="array", items=items)


def build_enum_property(prop: inspect.Parameter) -> PropertyDefinition:
    return PropertyDefinition(type="string", enum=[e.value for e in prop.annotation])


def __map_param_type(param: Any) -> ParamType:
    if isinstance(param, type) and issubclass(param, Enum):
        return ParamType.ENUM
    elif param == str:
        return ParamType.STRING
    elif param == int:
        return ParamType.INTEGER
    elif param == float:
        return ParamType.FLOAT
    elif param == bool:
        return ParamType.BOOLEAN
    elif get_origin(param) == list:
        return ParamType.LIST
    else:
        return ParamType.OBJECT


def build_property(param: Any):
    mapped_param_type = __map_param_type(param)
    match mapped_param_type:
        case ParamType.STRING:
            return build_string_property(param)
        case ParamType.INTEGER:
            return build_number_property(param)
        case ParamType.FLOAT:
            return build_number_property(param)
        case ParamType.BOOLEAN:
            return build_boolean_property(param)
        case ParamType.LIST:
            return build_array_property(param)
        case ParamType.OBJECT:
            return build_object_property(param)
        case ParamType.ENUM:
            return build_enum_property(param)
        case _:
            raise Exception(f"Unhandled parameter type: {param}")
