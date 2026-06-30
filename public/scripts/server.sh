#!/bin/bash
#SBATCH -J 202501
#SBATCH -p CPU6240R
#SBATCH -n 48
#SBATCH -N 1
#SBATCH --mem=190G
#SBATCH --time=2880:00:00

#wavewatch3--ST2
export PATH=/public/home/weiyl001/software/wavewatch3/model/exe:$PATH

set -o pipefail

ulimit -s unlimited

# Check whether running under SLURM
# If not, submit this script via sbatch
if [ -z "$SLURM_JOB_ID" ]; then
    # Get absolute path of this script
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"

    sbatch --chdir="$SCRIPT_DIR" "$SCRIPT_PATH"
    squeue -l
    exit $?
fi


# Note: if you change this, also update #SBATCH -n above
MPI_NPROCS=48

# Save script root directory
SCRIPT_ROOT="$(pwd)"

# All output appends to run.log; on completion drop an empty 'success' or 'fail'
# marker file (run.log itself is never renamed or cleared).
LOG="$SCRIPT_ROOT/run.log"
SUCCESS_MARK="$SCRIPT_ROOT/success"
FAIL_MARK="$SCRIPT_ROOT/fail"

# Clean old markers only; keep earlier preparation/submission logs.
rm -f "$SUCCESS_MARK" "$FAIL_MARK"

# If login-shell MPICH libraries shadow Intel MPI, prepend Intel runtime libs after probe.
# Edit _WW3_INTEL_LD when moving to another host; hosts without this issue skip the export.
_WW3_INTEL_LD="/public/home/weiyl001/intel/compilers_and_libraries_2019.0.117/linux/mpi/intel64/lib/release:/public/home/weiyl001/intel/compilers_and_libraries_2019.0.117/linux/mpi/intel64/lib:/public/home/weiyl001/intel/compilers_and_libraries_2019.0.117/linux/mpi/intel64/libfabric/lib:/public/home/weiyl001/intel/compilers_and_libraries_2019.0.117/linux/compiler/lib/intel64_lin:/public/home/weiyl001/software/netcdf/lib"
ensure_ww3_mpi_runtime() {
    if [ -n "${WW3_MPI_RUNTIME_FIXED:-}" ]; then
        return 0
    fi
    local probe
    probe=$(ww3_grid 2>&1 | head -8 || true)
    if echo "$probe" | grep -q "mpi_f08_compile_constants_mp_mpi_comm_world_\|symbol lookup error"; then
        echo "WW3 MPI probe failed (MPICH/LD_LIBRARY_PATH conflict); prepending Intel runtime libs" >> "$LOG"
        export LD_LIBRARY_PATH="${_WW3_INTEL_LD}:${LD_LIBRARY_PATH:-}"
        probe=$(ww3_grid 2>&1 | head -8 || true)
        if echo "$probe" | grep -q "mpi_f08_compile_constants_mp_mpi_comm_world_\|symbol lookup error"; then
            echo "WW3 MPI probe still failed after LD_LIBRARY_PATH fix" >> "$LOG"
            fail_exit 1
        fi
    fi
    WW3_MPI_RUNTIME_FIXED=1
}

# Abort the run: drop a 'fail' marker (keep run.log) and exit with the given code
fail_exit() {
    touch "$FAIL_MARK"
    exit "$1"
}

# Run one step; abort immediately if it fails (no point continuing).
#   run_step <label> <command> [args...]
run_step() {
    local label="$1"; shift
    echo -e "
============================== Running $label ==============================" >> "$LOG"
    "$@" >> "$LOG" 2>&1
    local rc=$?
    if [ "$rc" -ne 0 ]; then
        echo -e "
============================== $label failed (exit $rc); aborting ==============================" >> "$LOG"
        fail_exit "$rc"
    fi
}

# Run ww3_prnc for one or many forcing files (each step aborts on failure)
run_prnc_with_fields() {
    if [ -f "ww3_prnc_current.nml" ] || [ -f "ww3_prnc_level.nml" ] || [ -f "ww3_prnc_ice.nml" ] || [ -f "ww3_prnc_ice1.nml" ]; then
        # Multiple forcing files found; process sequentially
        run_step "ww3_prnc (wind)" ww3_prnc
        mv ww3_prnc.nml ww3_prnc_wind.nml

        if [ -f "ww3_prnc_current.nml" ]; then
            mv ww3_prnc_current.nml ww3_prnc.nml
            run_step "ww3_prnc (current)" ww3_prnc
            mv ww3_prnc.nml ww3_prnc_current.nml
        fi

        if [ -f "ww3_prnc_level.nml" ]; then
            mv ww3_prnc_level.nml ww3_prnc.nml
            run_step "ww3_prnc (level)" ww3_prnc
            mv ww3_prnc.nml ww3_prnc_level.nml
        fi

        if [ -f "ww3_prnc_ice.nml" ]; then
            mv ww3_prnc_ice.nml ww3_prnc.nml
            run_step "ww3_prnc (ice)" ww3_prnc
            mv ww3_prnc.nml ww3_prnc_ice.nml
        fi

        if [ -f "ww3_prnc_ice1.nml" ]; then
            mv ww3_prnc_ice1.nml ww3_prnc.nml
            run_step "ww3_prnc (ice1)" ww3_prnc
            mv ww3_prnc.nml ww3_prnc_ice1.nml
        fi

        mv ww3_prnc_wind.nml ww3_prnc.nml
    else
        run_step "ww3_prnc" ww3_prnc
    fi
}

log_msg() {
    echo "$@" >> "$LOG"
}

clean_yaml_scalar() {
    sed -E "s/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//; s/^['\"]//; s/['\"]$//"
}

params_restart_value() {
    local key="$1"
    local default_value="$2"
    local value
    value=$(awk -v target="$key" '
        /^ww3:[[:space:]]*$/ { in_ww3=1; in_restart=0; next }
        /^[^[:space:]]/ { if ($0 !~ /^ww3:[[:space:]]*$/) { in_ww3=0; in_restart=0 } }
        in_ww3 && /^[[:space:]]{2}restart:[[:space:]]*$/ { in_restart=1; next }
        in_restart && /^[[:space:]]{2}[^[:space:]]/ && $0 !~ /^[[:space:]]{4}/ { in_restart=0 }
        in_restart {
            pattern = "^[[:space:]]{4}" target ":[[:space:]]*"
            if ($0 ~ pattern) {
                sub(pattern, "", $0)
                print $0
                exit
            }
        }
    ' "$SCRIPT_ROOT/params.yml" 2>/dev/null | clean_yaml_scalar)
    if [ -n "$value" ] && [ "$value" != "null" ]; then
        echo "$value"
    else
        echo "$default_value"
    fi
}

restart_truthy() {
    case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
        true|yes|1|on) return 0 ;;
        *) return 1 ;;
    esac
}

find_checkpoint_by_time() {
    local dir="$1"
    local suffix="$2"
    local restart_time="$3"
    local stamp
    stamp="$(printf '%s' "$restart_time" | sed -E 's/^([0-9]{8})[[:space:]]+([0-9]{6})$/\1.\2/')"
    [ -n "$stamp" ] || return 0
    ls -1 "$dir/${stamp}.restart.${suffix}" 2>/dev/null | head -n 1
}

latest_checkpoint() {
    local dir="$1"
    local suffix="$2"
    local latest=""
    while IFS= read -r candidate; do
        [ -n "$candidate" ] || continue
        latest="$candidate"
    done <<EOF
$(ls -1 "$dir"/*.restart."$suffix" 2>/dev/null | sort)
EOF
    echo "$latest"
}

latest_numbered_restart() {
    local dir="$1"
    local best_index=-1
    local best_path=""
    local path index
    for path in "$dir"/restart[0-9]*.ww3; do
        [ -f "$path" ] || continue
        index="$(basename "$path" | sed -E 's/^restart([0-9]+)\.ww3$/\1/i')"
        [ -n "$index" ] || continue
        if [ "$index" -gt "$best_index" ]; then
            best_index="$index"
            best_path="$path"
        fi
    done
    echo "$best_path"
}

nml_restart_schedule() {
    local file="$1"
    [ -f "$file" ] || return 1
    python3 - "$file" <<'PY'
import re
import sys
from pathlib import Path

pattern = re.compile(
    r"(?:DATE|ALLDATE)%RESTART\s*=\s*'(\d{8}\s+\d{6})'\s*'(\d+)'",
    re.IGNORECASE,
)
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.strip().startswith("!"):
        continue
    match = pattern.search(line)
    if not match:
        continue
    stride = int(match.group(2))
    if stride <= 0:
        continue
    print(match.group(1))
    print(match.group(2))
    raise SystemExit(0)
raise SystemExit(1)
PY
}

restart_time_for_numbered_index() {
    local start_time="$1"
    local stride="$2"
    local index="$3"
  python3 - "$start_time" "$stride" "$index" <<'PY'
import sys
from datetime import datetime, timedelta
start = datetime.strptime(sys.argv[1], "%Y%m%d %H%M%S")
moment = start + timedelta(seconds=int(sys.argv[2]) * int(sys.argv[3]))
print(moment.strftime("%Y%m%d %H%M%S"))
PY
}

numbered_restart_for_time() {
    local dir="$1"
    local restart_time="$2"
    local nml_file="$3"
    local start_time stride delta index candidate
    read -r start_time stride <<EOF
$(nml_restart_schedule "$nml_file")
EOF
    [ -n "$start_time" ] && [ -n "$stride" ] && [ "$stride" -gt 0 ] || return 1
    delta="$(python3 - "$start_time" "$stride" "$restart_time" <<'PY'
import sys
from datetime import datetime
start = datetime.strptime(sys.argv[1], "%Y%m%d %H%M%S")
target = datetime.strptime(sys.argv[3], "%Y%m%d %H%M%S")
delta = int((target - start).total_seconds())
stride = int(sys.argv[2])
if delta < 0 or delta % stride != 0:
    raise SystemExit(1)
print(delta // stride)
PY
)" || return 1
    index="$delta"
    [ "$index" -gt 0 ] || return 1
  candidate="$dir/restart$(printf '%03d' "$index").ww3"
    [ -f "$candidate" ] && echo "$candidate" && return 0
    candidate="$dir/restart${index}.ww3"
    [ -f "$candidate" ] && echo "$candidate"
}

resolve_restart_file_name() {
    local value="$1"
    value="$(printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -n "$value" ] || return 0
    case "$value" in
        */*|*\\*) return 1 ;;
    esac
    echo "$value"
}

normalize_restart_time_value() {
    python3 - "$1" <<'PY'
import re
import sys

text = sys.argv[1].strip()
match = re.match(r"^(\d{8})(?:\s+(\d{6}))?$", text)
if not match:
    raise SystemExit(1)
print(f"{match.group(1)} {match.group(2) or '000000'}")
PY
}

RESTART_FILE="$(params_restart_value restart_file "")"

update_nml_start_time() {
    local file="$1"
    local restart_time="$2"
    local tmp
    [ -f "$file" ] || return 0
    tmp="${file}.tmp.$$"
    sed -E \
        -e "s/((DOMAIN%START|OUTPUT%FIELD%TIMESTART)[[:space:]]*=[[:space:]]*)'[^']+'/\1'${restart_time}'/g" \
        -e "s/((DATE|ALLDATE)%(FIELD|POINT|TRACK|RESTART2)[[:space:]]*=[[:space:]]*)'[^']+'/\1'${restart_time}'/g" \
        -e "s/((DATE|ALLDATE)%(FIELD|POINT|TRACK|RESTART2)%START[[:space:]]*=[[:space:]]*)'[^']+'/\1'${restart_time}'/g" \
        "$file" > "$tmp" && mv "$tmp" "$file"
}

RESTART_MODE="$(params_restart_value mode cold | tr '[:upper:]' '[:lower:]')"
RESTART_PICK_LATEST="$(params_restart_value pick_latest_checkpoint true)"
RESTART_TIME="$(params_restart_value restart_time "")"
RESTART_RUNTIME_TIME=""

prepare_regular_restart() {
    [ "$RESTART_MODE" = "restart" ] || return 1
    local checkpoint nml_file="$SCRIPT_ROOT/ww3_shel.nml"
    local start_time stride index resolved_file
    if restart_truthy "$RESTART_PICK_LATEST"; then
        checkpoint="$(latest_checkpoint "$SCRIPT_ROOT" "ww3")"
        if [ -n "$checkpoint" ] && [ -f "$checkpoint" ]; then
            RESTART_RUNTIME_TIME="$(basename "$checkpoint" | sed -E 's/^([0-9]{8})\.([0-9]{6})\.restart\..*$/\1 \2/')"
            cp -f "$checkpoint" "$SCRIPT_ROOT/restart.ww3" || fail_exit 1
            log_msg "✅ Auto Latest restart: $(basename "$checkpoint") -> restart.ww3 ($RESTART_RUNTIME_TIME)"
        else
            checkpoint="$(latest_numbered_restart "$SCRIPT_ROOT")"
            if [ -z "$checkpoint" ] || [ ! -f "$checkpoint" ]; then
                log_msg "❌ Auto Latest failed: no timestamped or numbered restart checkpoint found"
                fail_exit 1
            fi
            read -r start_time stride <<EOF
$(nml_restart_schedule "$nml_file")
EOF
            index="$(basename "$checkpoint" | sed -E 's/^restart([0-9]+)\.ww3$/\1/i')"
            if [ -z "$start_time" ] || [ -z "$stride" ] || [ -z "$index" ]; then
                log_msg "❌ Auto Latest failed: cannot infer restart time from nml for $(basename "$checkpoint")"
                fail_exit 1
            fi
            RESTART_RUNTIME_TIME="$(restart_time_for_numbered_index "$start_time" "$stride" "$index")"
            cp -f "$checkpoint" "$SCRIPT_ROOT/restart.ww3" || fail_exit 1
            log_msg "✅ Auto Latest restart: $(basename "$checkpoint") -> restart.ww3 ($RESTART_RUNTIME_TIME)"
        fi
    else
        RESTART_RUNTIME_TIME="$(normalize_restart_time_value "$RESTART_TIME")" || {
            log_msg "❌ restart_time must be YYYYMMDD or YYYYMMDD HHMMSS"
            fail_exit 1
        }
        resolved_file="$(resolve_restart_file_name "$RESTART_FILE")" || {
            log_msg "❌ restart_file must be a filename inside the workdir"
            fail_exit 1
        }
        if [ -n "$resolved_file" ]; then
            checkpoint="$SCRIPT_ROOT/$resolved_file"
            if [ ! -f "$checkpoint" ]; then
                log_msg "❌ Restart file not found: $resolved_file"
                fail_exit 1
            fi
            cp -f "$checkpoint" "$SCRIPT_ROOT/restart.ww3" || fail_exit 1
            log_msg "✅ Restart file: $resolved_file -> restart.ww3 ($RESTART_RUNTIME_TIME)"
        else
            checkpoint="$(find_checkpoint_by_time "$SCRIPT_ROOT" "ww3" "$RESTART_RUNTIME_TIME")"
            if [ -n "$checkpoint" ] && [ -f "$checkpoint" ]; then
                cp -f "$checkpoint" "$SCRIPT_ROOT/restart.ww3" || fail_exit 1
                log_msg "✅ Restart checkpoint: $(basename "$checkpoint") -> restart.ww3 ($RESTART_RUNTIME_TIME)"
            else
                checkpoint="$(numbered_restart_for_time "$SCRIPT_ROOT" "$RESTART_RUNTIME_TIME" "$nml_file")"
                if [ -n "$checkpoint" ] && [ -f "$checkpoint" ]; then
                    cp -f "$checkpoint" "$SCRIPT_ROOT/restart.ww3" || fail_exit 1
                    log_msg "✅ Restart checkpoint: $(basename "$checkpoint") -> restart.ww3 ($RESTART_RUNTIME_TIME)"
                fi
            fi
        fi
    fi
    if [ ! -f "$SCRIPT_ROOT/restart.ww3" ]; then
        log_msg "❌ Restart mode requires restart.ww3 (specify restart_file or matching checkpoint)"
        fail_exit 1
    fi
    update_nml_start_time "$SCRIPT_ROOT/ww3_shel.nml" "$RESTART_RUNTIME_TIME"
    return 0
}

prepare_nested_restart() {
    [ "$RESTART_MODE" = "restart" ] || return 1
    local selected_time=""
    local lv checkpoint current_time
    for lv in "$@"; do
        if restart_truthy "$RESTART_PICK_LATEST"; then
            checkpoint="$(latest_checkpoint "$SCRIPT_ROOT" "$lv")"
            if [ -z "$checkpoint" ]; then
                checkpoint="$(latest_checkpoint "$SCRIPT_ROOT/$lv" "ww3")"
            fi
            if [ -z "$checkpoint" ]; then
                log_msg "❌ Auto Latest failed: no timestamped restart checkpoint found for $lv"
                fail_exit 1
            fi
            current_time="$(basename "$checkpoint" | sed -E 's/^([0-9]{8})\.([0-9]{6})\.restart\..*$/\1 \2/')"
            if [ -n "$selected_time" ] && [ "$selected_time" != "$current_time" ]; then
                log_msg "❌ Nested restart checkpoint times differ: $selected_time vs $current_time"
                fail_exit 1
            fi
            selected_time="$current_time"
            cp -f "$checkpoint" "$SCRIPT_ROOT/$lv/restart.ww3" || fail_exit 1
            log_msg "✅ Auto Latest restart ($lv): $(basename "$checkpoint") -> $lv/restart.ww3 ($current_time)"
        else
            if [ -z "$RESTART_TIME" ]; then
                log_msg "❌ Restart mode requires restart_time when Auto Latest is disabled"
                fail_exit 1
            fi
            checkpoint="$(find_checkpoint_by_time "$SCRIPT_ROOT" "$lv" "$RESTART_TIME")"
            if [ -z "$checkpoint" ]; then
                checkpoint="$(find_checkpoint_by_time "$SCRIPT_ROOT/$lv" "ww3" "$RESTART_TIME")"
            fi
            if [ -n "$checkpoint" ] && [ -f "$checkpoint" ]; then
                cp -f "$checkpoint" "$SCRIPT_ROOT/$lv/restart.ww3" || fail_exit 1
                log_msg "✅ Restart checkpoint ($lv): $(basename "$checkpoint") -> $lv/restart.ww3 ($RESTART_TIME)"
            elif [ ! -f "$SCRIPT_ROOT/$lv/restart.ww3" ] && [ -f "$SCRIPT_ROOT/restart.$lv" ]; then
                cp -f "$SCRIPT_ROOT/restart.$lv" "$SCRIPT_ROOT/$lv/restart.ww3" || fail_exit 1
            fi
        fi
        if [ ! -f "$SCRIPT_ROOT/$lv/restart.ww3" ]; then
            log_msg "❌ Restart mode requires $lv/restart.ww3"
            fail_exit 1
        fi
    done
    if restart_truthy "$RESTART_PICK_LATEST"; then
        RESTART_RUNTIME_TIME="$selected_time"
    else
        RESTART_RUNTIME_TIME="$RESTART_TIME"
    fi
    if [ -z "$RESTART_RUNTIME_TIME" ]; then
        log_msg "❌ Restart mode requires restart_time when Auto Latest is disabled"
        fail_exit 1
    fi
    update_nml_start_time "$SCRIPT_ROOT/ww3_multi.nml" "$RESTART_RUNTIME_TIME"
    return 0
}

# ww3_shel: try MPI first, fall back to a direct (non-MPI) run before failing
run_ww3_shel_with_fallback() {
    echo -e "
============================== Running mpirun ww3_shel ==============================" >> "$LOG"
    mpirun -n $MPI_NPROCS ww3_shel >> "$LOG" 2>&1
    rc_mpi=$?
    if [ $rc_mpi -eq 0 ]; then
        return 0
    fi

    echo -e "
============================== mpirun ww3_shel failed with exit code $rc_mpi; retrying direct ww3_shel ==============================" >> "$LOG"
    ww3_shel >> "$LOG" 2>&1
    rc_direct=$?
    if [ $rc_direct -eq 0 ]; then
        echo -e "
============================== direct ww3_shel succeeded after mpirun failure ==============================" >> "$LOG"
        return 0
    fi

    echo -e "
============================== direct ww3_shel also failed with exit code $rc_direct ==============================" >> "$LOG"
    return $rc_direct
}

# Determine grid type from params.yml (fall back to the on-disk layout)
GRID_TYPE="$(grep -m1 -E '^[[:space:]]*grid_type:' "$SCRIPT_ROOT/params.yml" 2>/dev/null | sed -E 's/.*grid_type:[[:space:]]*//; s/[[:space:]]*$//')"
if [ -z "$GRID_TYPE" ]; then
    if ls -d level[0-9]* >/dev/null 2>&1; then GRID_TYPE="nested"; else GRID_TYPE="normal"; fi
fi
echo "Grid type (from params.yml): $GRID_TYPE" >> "$LOG"
ensure_ww3_mpi_runtime

if [ "$GRID_TYPE" = "nested" ]; then
    # Nested grid mode (N levels: level0=coarsest .. levelN=finest)
    # Discover nested grid dirs (level0=coarsest .. levelN=finest).
    LEVELS=$(ls -d level[0-9]* 2>/dev/null | sort -V)
    if [ -z "$LEVELS" ]; then
        echo "no nested grid dirs (level*) found" >> "$LOG" ; fail_exit 1
    fi
    FINEST=$(echo "$LEVELS" | tr ' ' '\n' | sed '/^$/d' | tail -1)
    RESTART_SKIP_STRT=0
    if prepare_nested_restart $LEVELS; then
        RESTART_SKIP_STRT=1
    fi

    # 1) Per-level: ww3_grid + forcing prep + ww3_strt
    for lv in $LEVELS; do
        cd "$lv"
        run_step "ww3_grid ($lv)" ww3_grid
        run_prnc_with_fields
        if [ "$RESTART_SKIP_STRT" -eq 1 ]; then
            echo "⏭️ Restart mode: skip ww3_strt ($lv), start from $RESTART_RUNTIME_TIME" >> "$LOG"
        else
            run_step "ww3_strt ($lv)" ww3_strt
        fi
        cd ..
    done

    # 2) Stage each level's files as <type>.<level> for ww3_multi
    for lv in $LEVELS; do
        [ -f "$lv/mod_def.ww3" ] && mv "$lv/mod_def.ww3" "mod_def.$lv"
        [ -f "$lv/restart.ww3" ] && mv "$lv/restart.ww3" "restart.$lv"
        [ -f "$lv/wind.ww3" ]    && mv "$lv/wind.ww3"    "wind.$lv"
        [ -f "$lv/current.ww3" ] && mv "$lv/current.ww3" "current.$lv"
        [ -f "$lv/level.ww3" ]   && mv "$lv/level.ww3"   "level.$lv"
        [ -f "$lv/ice.ww3" ]     && mv "$lv/ice.ww3"     "ice.$lv"
        [ -f "$lv/ice1.ww3" ]    && mv "$lv/ice1.ww3"    "ice1.$lv"
    done

    ######################################
    # Run MPI program (nested grid mode)
    ######################################
    echo -e "
============================== Running mpirun ww3_multi ==============================" >> "$LOG"
    mpirun -n $MPI_NPROCS ww3_multi >> "$LOG" 2>&1
    rc_mpi=$?

    if [ $rc_mpi -ne 0 ]; then
        fail_exit $rc_mpi
    fi

    # 3) Export results from the finest level
    [ -f "out_grd.$FINEST" ] && mv "out_grd.$FINEST" "$FINEST/out_grd.ww3"
    [ -f "mod_def.$FINEST" ] && mv "mod_def.$FINEST" "$FINEST/mod_def.ww3"
    [ -f "out_pnt.$FINEST" ] && mv "out_pnt.$FINEST" "$FINEST/out_pnt.ww3"
    [ -f "track_o.$FINEST" ] && mv "track_o.$FINEST" "$FINEST/track_o.ww3"
    cd "$FINEST"
    [ -f ../points.list ] && run_step "ww3_ounp" ww3_ounp
    [ -f track_i.ww3 ] && run_step "ww3_trnc" ww3_trnc
    run_step "ww3_ounf" ww3_ounf
    cd ..

    ######################################
    # All done (nested grid mode)
    ######################################
    touch "$SUCCESS_MARK"
else
    # Regular grid mode
    RESTART_SKIP_STRT=0
    if prepare_regular_restart; then
        RESTART_SKIP_STRT=1
    fi
    run_step "ww3_grid" ww3_grid
    run_prnc_with_fields
    if [ "$RESTART_SKIP_STRT" -eq 1 ]; then
        echo "⏭️ Restart mode: skip ww3_strt, start from $RESTART_RUNTIME_TIME" >> "$LOG"
    else
        run_step "ww3_strt" ww3_strt
    fi

    ######################################
    # Run MPI program (regular grid mode)
    ######################################
    run_ww3_shel_with_fallback
    rc_shel=$?

    if [ $rc_shel -ne 0 ]; then
        fail_exit $rc_shel
    fi

    ######################################
    # Export results (regular grid mode)
    ######################################
    [ -f points.list ] && run_step "ww3_ounp" ww3_ounp
    [ -f track_i.ww3 ] && run_step "ww3_trnc" ww3_trnc
    run_step "ww3_ounf" ww3_ounf

    ######################################
    # All done (regular grid mode)
    ######################################
    touch "$SUCCESS_MARK"
fi
