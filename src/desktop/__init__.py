"""Desktop application and view-model adapters for the src architecture."""

__all__ = [
    "ForcingStepViewModel",
    "PipelineViewModel",
    "PreprocessingWindow",
    "create_window",
    "main",
]


def __getattr__(name):
    if name == "ForcingStepViewModel":
        from .view_models.forcing_step import ForcingStepViewModel

        return ForcingStepViewModel
    if name == "PipelineViewModel":
        from .view_models.pipeline import PipelineViewModel

        return PipelineViewModel
    if name == "PreprocessingWindow":
        from .windows.preprocessing_window import PreprocessingWindow

        return PreprocessingWindow
    if name in {"create_window", "main"}:
        from .application import create_window, main

        return {"create_window": create_window, "main": main}[name]
    raise AttributeError(name)
