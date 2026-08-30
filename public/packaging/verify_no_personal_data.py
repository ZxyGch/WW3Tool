"""发布前检查：产物里不得残留开发者的路径 / 主机 / 账号。

仓库根的 params.yml 既是开发者日常配置又是随包分发的模板，构建时由
run.py 的 _sanitize_params_template 清洗。这个脚本是兜底——清洗漏了就让
发布失败，而不是发出去之后才发现。

[EN] Release gate: fail if developer-specific values reached the artifacts.
"""

import pathlib
import re
import sys
import tarfile
import zipfile

# 家目录形态的绝对路径，以及本项目用过的集群家目录前缀。
PATTERN = re.compile(rb"/Users/|/root/|/public/home/|[A-Za-z]:\\Users\\")

# 只检查随包分发的运行资源；第三方依赖里出现构建路径是正常的。
SUFFIXES = (".yml", ".yaml", ".json", ".nml", ".flag", "requirements.txt")


def _offenders(name, data):
    for lineno, line in enumerate(data.splitlines(), 1):
        if PATTERN.search(line):
            yield f"{name}:{lineno}: {line.decode('utf-8', 'replace').strip()}"


def scan(dist="dist"):
    bad = []
    for path in sorted(pathlib.Path(dist).glob("*")):
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as zf:
                for member in zf.namelist():
                    if member.endswith(SUFFIXES):
                        bad += list(_offenders(f"{path.name}:{member}", zf.read(member)))
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path) as tf:
                for member in tf.getmembers():
                    if member.isfile() and member.name.endswith(SUFFIXES):
                        handle = tf.extractfile(member)
                        if handle is not None:
                            bad += list(_offenders(f"{path.name}:{member.name}", handle.read()))
    return bad


if __name__ == "__main__":
    offenders = scan(sys.argv[1] if len(sys.argv) > 1 else "dist")
    for line in offenders[:20]:
        print(f"  {line}")
    if offenders:
        print(f"\n共 {len(offenders)} 处")
    sys.exit(1 if offenders else 0)
