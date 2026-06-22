#!/bin/bash

set -o pipefail

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

# Treat current directory as script root (assumes running in case directory)
SCRIPT_ROOT="$(pwd)"

# All output goes to run.log; on completion drop an empty 'success' or 'fail'
# marker file (run.log itself is never renamed).
LOG="$SCRIPT_ROOT/run.log"
SUCCESS_MARK="$SCRIPT_ROOT/success"
FAIL_MARK="$SCRIPT_ROOT/fail"
rm -f "$LOG" "$SUCCESS_MARK" "$FAIL_MARK"

echo "Using MPI_NPROCS=$MPI_NPROCS" | tee -a "$LOG"

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
============================== Running $label ==============================" | tee -a "$LOG"
    "$@" 2>&1 | tee -a "$LOG"
    local rc=${PIPESTATUS[0]}
    if [ "$rc" -ne 0 ]; then
        echo -e "
============================== $label failed (exit $rc); aborting ==============================" | tee -a "$LOG"
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
============================== Running mpirun ww3_shel ==============================" | tee -a "$LOG"
    mpirun -n $MPI_NPROCS ww3_shel 2>&1 | tee -a "$LOG"
    rc_mpi=${PIPESTATUS[0]}
    if [ $rc_mpi -eq 0 ]; then
        return 0
    fi

    echo -e "
============================== mpirun ww3_shel failed with exit code $rc_mpi; retrying direct ww3_shel ==============================" | tee -a "$LOG"
    ww3_shel 2>&1 | tee -a "$LOG"
    rc_direct=${PIPESTATUS[0]}
    if [ $rc_direct -eq 0 ]; then
        echo -e "
============================== direct ww3_shel succeeded after mpirun failure ==============================" | tee -a "$LOG"
        return 0
    fi

    echo -e "
============================== direct ww3_shel also failed with exit code $rc_direct ==============================" | tee -a "$LOG"
    return $rc_direct
}

# Determine grid type from params.yml (fall back to the on-disk layout)
GRID_TYPE="$(grep -m1 -E '^[[:space:]]*grid_type:' "$SCRIPT_ROOT/params.yml" 2>/dev/null | sed -E 's/.*grid_type:[[:space:]]*//; s/[[:space:]]*$//')"
if [ -z "$GRID_TYPE" ]; then
    if [ -d "coarse" ] && [ -d "fine" ]; then GRID_TYPE="nested"; else GRID_TYPE="normal"; fi
fi
echo "Grid type (from params.yml): $GRID_TYPE" | tee -a "$LOG"

if [ "$GRID_TYPE" = "nested" ]; then
    ######################################
    # Nested grid mode
    ######################################
    cd coarse
    run_step "ww3_grid (coarse)" ww3_grid
    run_prnc_with_fields
    run_step "ww3_strt (coarse)" ww3_strt
    cd ..

    cd fine
    run_step "ww3_grid (fine)" ww3_grid
    run_prnc_with_fields
    run_step "ww3_strt (fine)" ww3_strt
    cd ..

    # Coarse grid file handling
    [ -f coarse/mod_def.ww3 ] && mv coarse/mod_def.ww3 mod_def.coarse
    [ -f coarse/restart.ww3 ] && mv coarse/restart.ww3 restart.coarse
    [ -f coarse/wind.ww3 ]    && mv coarse/wind.ww3    wind.coarse
    [ -f coarse/current.ww3 ] && mv coarse/current.ww3 current.coarse
    [ -f coarse/level.ww3 ]   && mv coarse/level.ww3   level.coarse
    [ -f coarse/ice.ww3 ]     && mv coarse/ice.ww3     ice.coarse
    [ -f coarse/ice1.ww3 ]    && mv coarse/ice1.ww3    ice1.coarse

    # Fine grid file handling
    [ -f fine/mod_def.ww3 ]   && mv fine/mod_def.ww3   mod_def.fine
    [ -f fine/restart.ww3 ]   && mv fine/restart.ww3   restart.fine
    [ -f fine/wind.ww3 ]      && mv fine/wind.ww3      wind.fine
    [ -f fine/current.ww3 ]   && mv fine/current.ww3   current.fine
    [ -f fine/level.ww3 ]     && mv fine/level.ww3     level.fine
    [ -f fine/ice.ww3 ]       && mv fine/ice.ww3       ice.fine
    [ -f fine/ice1.ww3 ]      && mv fine/ice1.ww3      ice1.fine

    ######################################
    # Run MPI program (nested grid mode)
    ######################################
    echo -e "
============================== Running mpirun ww3_multi ==============================" | tee -a "$LOG"
    mpirun -n $MPI_NPROCS ww3_multi 2>&1 | tee -a "$LOG"
    rc_mpi=${PIPESTATUS[0]}
    if [ $rc_mpi -ne 0 ]; then
        fail_exit $rc_mpi
    fi

    [ -f out_grd.fine ] && mv out_grd.fine fine/out_grd.ww3
    [ -f mod_def.fine ] && mv mod_def.fine fine/mod_def.ww3
    [ -f out_pnt.fine ] && mv out_pnt.fine fine/out_pnt.ww3

    ######################################
    # Export results (nested grid mode)
    ######################################
    cd fine
    [ -f points.list ] && run_step "ww3_ounp (fine)" ww3_ounp
    [ -f track_i.ww3 ] && run_step "ww3_trnc (fine)" ww3_trnc
    run_step "ww3_ounf (fine)" ww3_ounf
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
