import importlib.util


def test_demo_app_module_exists() -> None:
    assert importlib.util.find_spec("client.demo_app") is not None
