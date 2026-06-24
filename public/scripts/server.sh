#!/bin/bash
#SBATCH -J 202501
#SBATCH -p CPU6240R
#SBATCH -n 48
#SBATCH -N 1
#SBATCH --mem=190G
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

# Save script root directory
SCRIPT_ROOT="$(pwd)"

# All output appends to run.log; on completion drop an empty 'success' or 'fail'
# marker file (run.log itself is never renamed or cleared).
LOG="$SCRIPT_ROOT/run.log"
SUCCESS_MARK="$SCRIPT_ROOT/success"
FAIL_MARK="$SCRIPT_ROOT/fail"

# Clean old markers only; keep earlier preparation/submission logs.
rm -f "$SUCCESS_MARK" "$FAIL_MARK"

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

if [ "$GRID_TYPE" = "nested" ]; then
    # Nested grid mode (N levels: level0=coarsest .. levelN=finest)
    # Discover nested grid dirs (level0=coarsest .. levelN=finest).
    LEVELS=$(ls -d level[0-9]* 2>/dev/null | sort -V)
    if [ -z "$LEVELS" ]; then
        echo "no nested grid dirs (level*) found" >> "$LOG" ; fail_exit 1
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
