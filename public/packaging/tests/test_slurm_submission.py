"""使用本地替身命令验证提交脚本，禁止调用真实 Slurm。"""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from workflows.infrastructure.ww3.server_sh import ServerSh, _update_submission_block
from workflows.infrastructure.ww3.widget_stubs import _TextValue


@pytest.fixture
def submission(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    workdir = tmp_path / "job with spaces"
    workdir.mkdir()
    script = workdir / "server.sh"
    script.write_text((ROOT / "public/scripts/server.sh").read_text())
    # 替身仅输出预设作业 ID 和退出码，记录队列查询是否执行。
    (bin_dir / "sbatch").write_text('#!/bin/sh\nprintf "%s\\n" "$TASK_JOB_ID"\nexit "$TASK_SUBMIT_RC"\n')
    (bin_dir / "squeue").write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$TASK_QUEUE_TRACE"\nexit "$TASK_QUEUE_RC"\n')
    for path in bin_dir.iterdir():
        path.chmod(0o700)
    env = dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin", I_MPI_ROOT="/synthetic/mpi",
               TASK_JOB_ID="12345", TASK_SUBMIT_RC="0", TASK_QUEUE_RC="0",
               TASK_QUEUE_TRACE=str(tmp_path / "queue.trace"))
    env.pop("SLURM_JOB_ID", None)
    return script, env


@pytest.mark.parametrize("submit_rc,queue_rc,job_id,expected", [
    (23, 0, "", 23), (0, 0, "12345", 0), (0, 17, "12345", 0),
    (0, 0, "12345;cluster", 0), (0, 0, "unexpected output", 1),
])
def test_submission_exit_code_and_job_id(submission, submit_rc, queue_rc, job_id, expected):
    script, env = submission
    env.update(TASK_SUBMIT_RC=str(submit_rc), TASK_QUEUE_RC=str(queue_rc), TASK_JOB_ID=job_id)
    result = subprocess.run(["/bin/bash", str(script)], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == expected, result.stderr
    saved_id = script.parent / "slurm_job_id"
    if expected == 0:
        assert saved_id.read_text().strip() == "12345"
        assert Path(env["TASK_QUEUE_TRACE"]).read_text().strip() == "-j 12345 -l"
    else:
        assert not saved_id.exists()
        assert not Path(env["TASK_QUEUE_TRACE"]).exists()


def test_standard_submission_block_updates_without_changing_model_body(submission):
    script, env = submission
    content = '#!/bin/bash\nif [ -z "$SLURM_JOB_ID" ]; then\n    sbatch server.sh\n    squeue -l\n    exit $?\nfi\n# MODEL BODY\n'
    updated = _update_submission_block(content, script.read_text())
    assert updated.endswith("# MODEL BODY\n")
    assert _update_submission_block(updated, script.read_text()) == updated
    script.write_text(updated)
    env["TASK_SUBMIT_RC"] = "23"
    result = subprocess.run(["/bin/bash", str(script)], env=env, capture_output=True, timeout=10)
    assert result.returncode == 23


def test_accepted_job_is_not_reported_failed_when_id_file_cannot_be_saved(submission):
    script, env = submission
    fake_mktemp = Path(env["PATH"].split(":")[0]) / "mktemp"
    fake_mktemp.write_text("#!/bin/sh\nexit 7\n")
    fake_mktemp.chmod(0o700)
    result = subprocess.run(["/bin/bash", str(script)], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "Submitted batch job 12345" in result.stdout
    assert "could not save job ID" in result.stderr


def test_generated_script_keeps_selected_executable_and_runtime(submission):
    script, _ = submission
    modifier = ServerSh()
    modifier.selected_folder = str(script.parent)
    modifier.shel_start_edit = _TextValue("20200101")
    modifier.num_n_edit, modifier.num_N_edit = _TextValue("4"), _TextValue("1")
    modifier.partition_var, modifier.st_var = "synthetic", "7.14 ST4_RECT"
    modifier._loaded_config = SimpleNamespace(slurm=SimpleNamespace(
        server_st_versions={"7.14 ST4_RECT": "/synthetic/ww3/bin"},
    ))
    logs = []
    modifier.log = logs.append
    modifier.modify_server_sh_file()
    modifier.modify_server_sh_file()
    text = script.read_text()
    assert text.count("export PATH=/synthetic/ww3/bin:$PATH") == 1, logs
    assert "mpi/2021.18/bin" in text
    assert "#SBATCH --time" not in text
    assert "sbatch --parsable" in text
    assert "MPI_NPROCS=4" in text
    subprocess.run(["/bin/bash", "-n", str(script)], check=True)
