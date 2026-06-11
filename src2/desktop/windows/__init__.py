"""Windows exposed by the desktop application."""

__all__ = [
    "DesktopSurfaceDependencyError",
    "ForcingPreparationWindow",
    "PreprocessingWindow",
    "WorkFolderDialog",
    "create_full_application_window",
    "create_preprocessing_window",
    "select_initial_work_directory",
]


def __getattr__(name):
    if name == "ForcingPreparationWindow":
        from .forcing_preparation_window import ForcingPreparationWindow

        return ForcingPreparationWindow
    if name in {"PreprocessingWindow", "create_preprocessing_window"}:
        from .preprocessing_window import PreprocessingWindow, create_preprocessing_window

        return {
            "PreprocessingWindow": PreprocessingWindow,
            "create_preprocessing_window": create_preprocessing_window,
        }[name]
    if name == "WorkFolderDialog":
        from .work_folder_dialog import WorkFolderDialog

        return WorkFolderDialog
    if name in {
        "DesktopSurfaceDependencyError",
        "create_full_application_window",
        "select_initial_work_directory",
    }:
        from .full_application_window import (
            DesktopSurfaceDependencyError,
            create_full_application_window,
            select_initial_work_directory,
        )

        return {
            "DesktopSurfaceDependencyError": DesktopSurfaceDependencyError,
            "create_full_application_window": create_full_application_window,
            "select_initial_work_directory": select_initial_work_directory,
        }[name]
    raise AttributeError(name)
