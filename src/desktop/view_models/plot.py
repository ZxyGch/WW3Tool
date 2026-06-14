"""绘图页视图模型：桥接桌面到 application 绘图用例。

各方法接受已构建的 ``PipelineConfig``，转调对应用例并把日志转发给 ``on_log``，
返回用例的 Result（含 ``image_files`` / ``messages`` / ``success``）。后台执行与忙碌态
由窗口的 BackgroundRunner 负责。

[EN] Plot page view model: bridges desktop to application plotting use cases.

Each method accepts a built ``PipelineConfig``, delegates to the corresponding use case
and forwards logs to ``on_log``, returning the use case's Result (with ``image_files`` /
``messages`` / ``success``). Background execution and busy state are managed by the
window's BackgroundRunner.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from workflows.domain.config_models import PipelineConfig

LogCallback = Callable[[str], None]


class PlotViewModel:
    # [EN] Drive wave height maps / spectrum / Jason-3 / NDBC plotting use cases.
    """驱动波高场图 / 谱图 / Jason-3 / NDBC 绘图用例。"""

    def __init__(self, *, on_log: Optional[LogCallback] = None) -> None:
        self._on_log = on_log

    def _log(self, message: str) -> None:
        if self._on_log is not None:
            self._on_log(str(message))

    def wave_maps(
        self,
        config: PipelineConfig,
        *,
        time_step_hours: Optional[float] = None,
        wave_file: str = "",
    ):
        from workflows.application.plot_wave_maps import run_wave_maps

        return run_wave_maps(
            config,
            log=self._log,
            time_step_hours=time_step_hours,
            wave_file=wave_file or None,
        )

    def contour_maps(
        self,
        config: PipelineConfig,
        *,
        time_step_hours: Optional[float] = None,
        wave_file: str = "",
    ):
        from workflows.application.plot_wave_maps import run_contour_maps

        return run_contour_maps(
            config,
            log=self._log,
            time_step_hours=time_step_hours,
            wave_file=wave_file or None,
        )

    def wind_swell_maps(
        self,
        config: PipelineConfig,
        *,
        time_step_hours: Optional[float] = None,
        wave_file: str = "",
    ):
        from workflows.application.plot_wave_maps import run_wind_swell_maps

        return run_wind_swell_maps(
            config,
            log=self._log,
            time_step_hours=time_step_hours,
            wave_file=wave_file or None,
        )

    def wave_video(
        self,
        config: PipelineConfig,
        *,
        time_step_hours: Optional[float] = None,
        wave_file: str = "",
    ):
        from workflows.application.plot_wave_maps import run_wave_video

        return run_wave_video(
            config,
            log=self._log,
            time_step_hours=time_step_hours,
            wave_file=wave_file or None,
        )

    def wind_field(
        self,
        config: PipelineConfig,
        *,
        wind_file: str = "",
        time_step_hours: Optional[float] = None,
        flag_type: Optional[str] = None,
        density_step: Optional[int] = None,
    ):
        from workflows.application.plot_wind_field import run_wind_field

        return run_wind_field(
            config,
            log=self._log,
            wind_file=wind_file,
            time_step_hours=time_step_hours,
            flag_type=flag_type,
            density_step=density_step,
        )

    def spectrum(self, config: PipelineConfig, *, mode: str = "all", station_index: int = 0):
        from workflows.application.plot_spectrum import run_spectrum

        return run_spectrum(config, log=self._log, mode=mode, station_index=station_index)

    def match_jason3(self, config: PipelineConfig, *, data_folder: str = ""):
        from workflows.application.match_jason3 import run_match_jason3

        return run_match_jason3(
            config,
            log=self._log,
            data_folder=data_folder or None,
        )

    def match_ndbc(
        self,
        config: PipelineConfig,
        *,
        lon_lat: Optional[List[float]] = None,
        time_range: Optional[List[str]] = None,
    ):
        from workflows.application.match_ndbc import run_match_ndbc

        return run_match_ndbc(config, log=self._log, lon_lat=lon_lat, time_range=time_range)

    def download_ndbc(
        self,
        config: PipelineConfig,
        *,
        lon_lat: Optional[List[float]] = None,
        time_range: Optional[List[str]] = None,
    ):
        from workflows.application.match_ndbc import run_download_ndbc

        return run_download_ndbc(config, log=self._log, lon_lat=lon_lat, time_range=time_range)

    def download_jason3(
        self,
        config: PipelineConfig,
        *,
        time_range: Optional[List[str]] = None,
        local_folder: Optional[str] = None,
    ):
        from workflows.application.download_jason3 import run_download_jason3

        return run_download_jason3(config, log=self._log, time_range=time_range, local_folder=local_folder)

    def jason3_swh(
        self,
        config: PipelineConfig,
        *,
        lon_lat: Optional[List[float]] = None,
        time_range: Optional[List[str]] = None,
        data_folder: str = "",
    ):
        from workflows.application.match_jason3 import run_jason3_swh

        return run_jason3_swh(
            config,
            log=self._log,
            lon_lat=lon_lat,
            time_range=time_range,
            data_folder=data_folder or None,
        )
