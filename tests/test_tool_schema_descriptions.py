"""Function-calling schema copy must stay complete for every static registered tool."""


def test_registered_tool_schemas_describe_the_tool_and_each_parameter():
    from core.tool_dispatcher import _TOOL_REGISTRY

    for name, spec in _TOOL_REGISTRY.items():
        assert spec.get("description", "").strip(), f"{name} 缺少工具说明"
        for parameter, schema in spec.get("parameters", {}).get("properties", {}).items():
            assert schema.get("description", "").strip(), f"{name}.{parameter} 缺少参数说明"
