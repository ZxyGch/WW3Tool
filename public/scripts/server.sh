#!/bin/bash
#SBATCH -J 202501
#SBATCH -p CPU6240R
#SBATCH -n 48
#SBATCH -N 1
#SBATCH --time=2880:00:00


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

# Case name (used by ww3_shel --casename)
CASENAME=202501

# Save script root directory
SCRIPT_ROOT="$(pwd)"

# All output goes to run.log; on completion drop an empty 'success' or 'fail'
# marker file (run.log itself is never renamed).
LOG="$SCRIPT_ROOT/run.log"
SUCCESS_MARK="$SCRIPT_ROOT/success"
FAIL_MARK="$SCRIPT_ROOT/fail"

# Clean old log and markers
rm -f "$LOG" "$SUCCESS_MARK" "$FAIL_MARK"

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

# ww3_shel: try MPI first, fall back to a direct (non-MPI) run before failing
run_ww3_shel_with_fallback() {
    echo -e "
============================== Running mpirun ww3_shel ==============================" >> "$LOG"
    mpirun -n $MPI_NPROCS ww3_shel --casename=$CASENAME >> "$LOG" 2>&1
    rc_mpi=$?
    if [ $rc_mpi -eq 0 ]; then
        return 0
    fi

    echo -e "
============================== mpirun ww3_shel failed with exit code $rc_mpi; retrying direct ww3_shel ==============================" >> "$LOG"
    ww3_shel --casename=$CASENAME >> "$LOG" 2>&1
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
    if [ -d "coarse" ] && [ -d "fine" ]; then GRID_TYPE="nested"; else GRID_TYPE="normal"; fi
fi
echo "Grid type (from params.yml): $GRID_TYPE" >> "$LOG"

if [ "$GRID_TYPE" = "nested" ]; then
    # Nested grid mode
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
============================== Running mpirun ww3_multi ==============================" >> "$LOG"
    mpirun -n $MPI_NPROCS ww3_multi --casename=$CASENAME >> "$LOG" 2>&1
    rc_mpi=$?

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
    [ -f points.list ] && run_step "ww3_ounp" ww3_ounp
    [ -f track_i.ww3 ] && run_step "ww3_trnc" ww3_trnc
    run_step "ww3_ounf" ww3_ounf
    cd ..

    ######################################
    # All done (nested grid mode)
    ######################################
    touch "$SUCCESS_MARK"
else
    # Regular grid mode
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

    ######################################
    # All done (regular grid mode)
    ######################################
    touch "$SUCCESS_MARK"
fi
