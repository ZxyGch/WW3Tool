"""Windows exposed by the desktop application."""

__all__ = [
    "PreprocessingWindow",
    "WorkFolderDialog",
    "create_preprocessing_window",
]


def __getattr__(name):
    if name in {"PreprocessingWindow", "create_preprocessing_window"}:
        from .preprocessing_window import PreprocessingWindow, create_preprocessing_window

        return {
            "PreprocessingWindow": PreprocessingWindow,
            "create_preprocessing_window": create_preprocessing_window,
        }[name]
    if name == "WorkFolderDialog":
        from .work_folder_dialog import WorkFolderDialog

        return WorkFolderDialog
    raise AttributeError(name)
