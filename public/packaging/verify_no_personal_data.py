"""发布前检查：产物里不得残留开发者的路径 / 主机 / 账号。

仓库根的 params.yml 既是开发者日常配置又是随包分发的模板，构建时由
run.py 的 _sanitize_params_template 清洗。这个脚本是兜底——清洗漏了就让
发布失败，而不是发出去之后才发现。

[EN] Release gate: fail if developer-specific values reached the artifacts.
"""

import json
import pathlib
import re
import sys
import tarfile
import zipfile

# 家目录形态的绝对路径，以及本项目用过的集群家目录前缀。
PATTERN = re.compile(rb"/Users/|/root/|/public/home/|[A-Za-z]:\\Users\\")

# 只检查随包分发的运行资源；第三方依赖里出现构建路径是正常的。
SUFFIXES = (".yml", ".yaml", ".json", ".nml", ".flag", "requirements.txt")

# 模板里必须保持中性的偏好项（与 run.py 的 _NEUTRAL_DEFAULTS 对应）。
# 打包那一刻开发者的界面语言曾经就这样成了所有用户的默认值。
# [EN] Preferences the template must keep neutral (mirrors run.py's _NEUTRAL_DEFAULTS).
NEUTRAL_DEFAULTS = {"language": "auto", "theme": "AUTO"}

_PREF_KV = re.compile(rb"^\s*(?P<key>[a-z_]+)\s*:\s*(?P<value>[^#\r\n]*?)\s*$")


def _offenders(name, data):
    for lineno, line in enumerate(data.splitlines(), 1):
        if PATTERN.search(line):
            yield f"{name}:{lineno}: {line.decode('utf-8', 'replace').strip()}"


def _preference_offenders(name, data):
    """模板里的个人偏好没被清洗回中性值时报错。

    [EN] Flag personal preferences the sanitizer failed to reset to a neutral value.
    """
    for lineno, line in enumerate(data.splitlines(), 1):
        m = _PREF_KV.match(line)
        if not m:
            continue
        key = m.group("key").decode("ascii", "replace")
        expected = NEUTRAL_DEFAULTS.get(key)
        if expected is None:
            continue
        value = m.group("value").decode("utf-8", "replace").strip().strip("'\"")
        if value != expected:
            yield (f"{name}:{lineno}: {key} 应为 {expected}，"
                   f"实际是 {value!r}（开发机偏好泄漏到了发行模板）")


def _broken_json(name, data):
    """清洗器改坏 JSON 的话在这里拦住。

    语言包解析失败不会报错，tr() 会静默退回源码里的中文默认值——
    发出去之后要靠用户报"怎么全是中文"才发现。

    [EN] Catch JSON the sanitizer corrupted: a broken language file does not
    raise, it silently falls back to the source-language defaults.
    """
    try:
        json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        return [f"{name}: 不是合法 UTF-8：{exc}"]
    except json.JSONDecodeError as exc:
        return [f"{name}: JSON 解析失败（清洗器很可能改坏了这一行）：{exc}"]
    return []


def _scan_member(name, data):
    found = list(_offenders(name, data))
    if name.endswith("params.yml"):
        found += list(_preference_offenders(name, data))
    if name.endswith(".json"):
        found += _broken_json(name, data)
    return found


def scan(dist="dist"):
    bad = []
    for path in sorted(pathlib.Path(dist).glob("*")):
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as zf:
                for member in zf.namelist():
                    if member.endswith(SUFFIXES):
                        bad += _scan_member(f"{path.name}:{member}", zf.read(member))
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path) as tf:
                for member in tf.getmembers():
                    if member.isfile() and member.name.endswith(SUFFIXES):
                        handle = tf.extractfile(member)
                        if handle is not None:
                            bad += _scan_member(f"{path.name}:{member.name}", handle.read())
    return bad


if __name__ == "__main__":
    offenders = scan(sys.argv[1] if len(sys.argv) > 1 else "dist")
    for line in offenders[:20]:
        print(f"  {line}")
    if offenders:
        print(f"\n共 {len(offenders)} 处")
    sys.exit(1 if offenders else 0)
