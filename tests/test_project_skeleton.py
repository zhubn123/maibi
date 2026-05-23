def test_project_packages_are_importable() -> None:
    import client
    import core
    import server

    assert client.__version__ == "0.1.0"
    assert core.__version__ == "0.1.0"
    assert server.__version__ == "0.1.0"

