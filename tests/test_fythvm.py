"""Basic import tests for fythvm."""


def test_import() -> None:
    """Verify the fythvm package can be imported."""
    import fythvm  # noqa: F401


def test_promoted_modules_import() -> None:
    """Verify promoted package modules can be imported."""
    import fythvm.codegen  # noqa: F401
    import fythvm.dictionary  # noqa: F401
    import fythvm.dictionary.ir  # noqa: F401
    import fythvm.dictionary.layout  # noqa: F401
    import fythvm.rpn16  # noqa: F401
