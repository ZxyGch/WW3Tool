#!/bin/bash

set -o pipefail

# Treat the directory containing this script as the case directory, even when
# local.sh is launched through an absolute path from another working directory.
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_ROOT" || exit 1

# All output appends to run.log; on completion drop an empty 'success' or 'fail'
# marker file (run.log itself is never renamed or cleared).
LOG="$SCRIPT_ROOT/run.log"
SUCCESS_MARK="$SCRIPT_ROOT/success"
FAIL_MARK="$SCRIPT_ROOT/fail"
rm -f "$SUCCESS_MARK" "$FAIL_MARK"

exec > >(tee -a "$LOG") 2>&1

ulimit -Sv 24000000

# MPI process count for local run:
# 1. Prefer explicit override from environment variable WW3_MPI_NPROCS
# 2. Otherwise use the number of online logical CPUs
# 3. Fallback to 1 if detection fails
MPI_NPROCS="${WW3_MPI_NPROCS:-}"
if [ -z "$MPI_NPROCS" ]; then
    if command -v getconf >/dev/null 2>&1; then
        MPI_NPROCS="$(getconf _NPROCESSORS_ONLN 2>/dev/null)"
    fi
fi
if [ -z "$MPI_NPROCS" ] && command -v sysctl >/dev/null 2>&1; then
    MPI_NPROCS="$(sysctl -n hw.logicalcpu 2>/dev/null)"
fi
case "$MPI_NPROCS" in
    ''|*[!0-9]*|0)
        MPI_NPROCS=1
        ;;
esac

echo "Using MPI_NPROCS=$MPI_NPROCS"

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
============================== Running $label =============================="
    "$@"
    local rc=$?
    if [ "$rc" -ne 0 ]; then
        echo -e "
============================== $label failed (exit $rc); aborting =============================="
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

# ww3_shel: try MPI first, fall back to a direct (non-MPI) run before failing
run_ww3_shel_with_fallback() {
    echo -e "
============================== Running mpirun ww3_shel =============================="
    mpirun -n $MPI_NPROCS ww3_shel
    rc_mpi=$?
    if [ $rc_mpi -eq 0 ]; then
        return 0
    fi

    echo -e "
============================== mpirun ww3_shel failed with exit code $rc_mpi; retrying direct ww3_shel =============================="
    ww3_shel
    rc_direct=$?
    if [ $rc_direct -eq 0 ]; then
        echo -e "
============================== direct ww3_shel succeeded after mpirun failure =============================="
        return 0
    fi

    echo -e "
============================== direct ww3_shel also failed with exit code $rc_direct =============================="
    return $rc_direct
}

# Determine grid type from params.yml (fall back to the on-disk layout)
GRID_TYPE="$(grep -m1 -E '^[[:space:]]*grid_type:' "$SCRIPT_ROOT/params.yml" 2>/dev/null | sed -E 's/.*grid_type:[[:space:]]*//; s/[[:space:]]*$//')"
if [ -z "$GRID_TYPE" ]; then
    if [ -d "coarse" ] && [ -d "fine" ]; then GRID_TYPE="nested"; else GRID_TYPE="normal"; fi
fi
echo "Grid type (from params.yml): $GRID_TYPE"

if [ "$GRID_TYPE" = "nested" ]; then
    ######################################
    # Nested grid mode (N levels: level0=coarsest .. levelN=finest)
    ######################################
    # Discover nested grid dirs; fall back to old coarse/fine layout.
    LEVELS=$(ls -d level[0-9]* 2>/dev/null | sort -V)
    [ -z "$LEVELS" ] && LEVELS=$(ls -d coarse fine 2>/dev/null)
    if [ -z "$LEVELS" ]; then
        echo "no nested grid dirs (level*/coarse/fine) found" ; fail_exit 1
    fi
    FINEST=$(echo "$LEVELS" | tr ' ' '\n' | sed '/^$/d' | tail -1)

    # 1) Per-level: ww3_grid + forcing prep + ww3_strt
    for lv in $LEVELS; do
        cd "$lv"
        run_step "ww3_grid ($lv)" ww3_grid
        run_prnc_with_fields
        run_step "ww3_strt ($lv)" ww3_strt
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
============================== Running mpirun ww3_multi =============================="
    mpirun -n $MPI_NPROCS ww3_multi
    rc_mpi=$?
    if [ $rc_mpi -ne 0 ]; then
        fail_exit $rc_mpi
    fi

    # 3) Export results from the finest level
    [ -f "out_grd.$FINEST" ] && mv "out_grd.$FINEST" "$FINEST/out_grd.ww3"
    [ -f "mod_def.$FINEST" ] && mv "mod_def.$FINEST" "$FINEST/mod_def.ww3"
    [ -f "out_pnt.$FINEST" ] && mv "out_pnt.$FINEST" "$FINEST/out_pnt.ww3"
    cd "$FINEST"
    [ -f points.list ] && run_step "ww3_ounp ($FINEST)" ww3_ounp
    [ -f track_i.ww3 ] && run_step "ww3_trnc ($FINEST)" ww3_trnc
    run_step "ww3_ounf ($FINEST)" ww3_ounf
    cd ..
    touch "$SUCCESS_MARK"
else
    ######################################
    # Regular grid mode
    ######################################
    run_step "ww3_grid" ww3_grid
    run_prnc_with_fields
    run_step "ww3_strt" ww3_strt

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
    touch "$SUCCESS_MARK"
fi
