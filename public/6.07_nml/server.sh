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
    
    sbatch "$SCRIPT_PATH"
    squeue -l
    exit $?
fi


# Note: if you change this, also update #SBATCH -n above
MPI_NPROCS=48

# Case name (used by ww3_shel --casename)
CASENAME=202501

# Save script root directory
SCRIPT_ROOT="$(pwd)"

# Log files (absolute paths so subdirectories work correctly)
RUN_LOG="$SCRIPT_ROOT/mpirun.log"
ALL_LOG="$SCRIPT_ROOT/all.log"
FAIL_LOG="$SCRIPT_ROOT/fail.log"
SUCCESS_LOG="$SCRIPT_ROOT/success.log"

# Clean old markers
rm -f "$FAIL_LOG" "$SUCCESS_LOG" "$ALL_LOG"

# Run ww3_prnc for multiple forcing files
run_prnc_with_fields() {
    # Check for multiple forcing files
    if [ -f "ww3_prnc_current.nml" ] || [ -f "ww3_prnc_level.nml" ] || [ -f "ww3_prnc_ice.nml" ] || [ -f "ww3_prnc_ice1.nml" ]; then
        # Multiple forcing files found; process sequentially
        
        # 1) Run ww3_prnc once (default ww3_prnc.nml, usually wind)
        echo -e "
============================== Running ww3_prnc (wind) ==============================" >> "$ALL_LOG"
        ww3_prnc >> "$ALL_LOG" 2>&1
        
        # 2) Rename ww3_prnc.nml -> ww3_prnc_wind.nml
        mv ww3_prnc.nml ww3_prnc_wind.nml
        
        # 3) Process other forcing files
        if [ -f "ww3_prnc_current.nml" ]; then
            echo -e "
============================== Running ww3_prnc (current) ==============================" >> "$ALL_LOG"
            mv ww3_prnc_current.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_current.nml
        fi
        
        if [ -f "ww3_prnc_level.nml" ]; then
            echo -e "
============================== Running ww3_prnc (level) ==============================" >> "$ALL_LOG"
            mv ww3_prnc_level.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_level.nml
        fi
        
        if [ -f "ww3_prnc_ice.nml" ]; then
            echo -e "
============================== Running ww3_prnc (ice) ==============================" >> "$ALL_LOG"
            mv ww3_prnc_ice.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_ice.nml
        fi

        if [ -f "ww3_prnc_ice1.nml" ]; then
            echo -e "
============================== Running ww3_prnc (ice1) ==============================" >> "$ALL_LOG"
            mv ww3_prnc_ice1.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_ice1.nml
        fi
        
        # 4) Restore ww3_prnc_wind.nml -> ww3_prnc.nml
        mv ww3_prnc_wind.nml ww3_prnc.nml
    else
        # Only one ww3_prnc.nml; run directly
        echo -e "
============================== Running ww3_prnc ==============================" >> "$ALL_LOG"
        ww3_prnc >> "$ALL_LOG" 2>&1
    fi
}

run_ww3_shel_with_fallback() {
    echo -e "
============================== Running mpirun ww3_shel ==============================" >> "$ALL_LOG"
    mpirun -n $MPI_NPROCS ww3_shel --casename=$CASENAME > "$RUN_LOG" 2>&1
    rc_mpi=$?
    cat "$RUN_LOG" >> "$ALL_LOG"
    if [ $rc_mpi -eq 0 ]; then
        return 0
    fi

    echo -e "
============================== mpirun ww3_shel failed with exit code $rc_mpi; retrying direct ww3_shel ==============================" >> "$ALL_LOG"
    ww3_shel --casename=$CASENAME > "$RUN_LOG" 2>&1
    rc_direct=$?
    cat "$RUN_LOG" >> "$ALL_LOG"
    if [ $rc_direct -eq 0 ]; then
        echo -e "
============================== direct ww3_shel succeeded after mpirun failure ==============================" >> "$ALL_LOG"
        return 0
    fi

    echo -e "
============================== direct ww3_shel also failed with exit code $rc_direct ==============================" >> "$ALL_LOG"
    return $rc_direct
}

# Detect nested grid mode
if [ -d "coarse" ] && [ -d "fine" ]; then
    # Nested grid mode
    echo -e "
============================== Running ww3_grid (coarse) ==============================" >> "$ALL_LOG"
    cd coarse
    ww3_grid >> "$ALL_LOG" 2>&1
    run_prnc_with_fields
    ww3_strt >> "$ALL_LOG" 2>&1
    cd ..
    
    echo -e "
============================== Running ww3_grid (fine) ==============================" >> "$ALL_LOG"
    cd fine
    ww3_grid >> "$ALL_LOG" 2>&1
    run_prnc_with_fields
    ww3_strt >> "$ALL_LOG" 2>&1
    cd ..
    
    # Coarse grid file handling
    [ -f coarse/mod_def.ww3 ] && mv coarse/mod_def.ww3 mod_def.coarse
    [ -f coarse/restart.ww3 ] && mv coarse/restart.ww3 restart.coarse
    [ -f coarse/wind.ww3 ]    && mv coarse/wind.ww3    wind.coarse
    [ -f coarse/current.ww3 ] && mv coarse/current.ww3 current.coarse
    [ -f coarse/level.ww3 ]   && mv coarse/level.ww3   level.coarse
    [ -f coarse/ice.ww3 ]     && mv coarse/ice.ww3     ice.coarse
    [ -f coarse/ice1.ww3 ]    && mv coarse/ice1.ww3    ice.coarse

    # Fine grid file handling
    [ -f fine/mod_def.ww3 ]   && mv fine/mod_def.ww3   mod_def.fine
    [ -f fine/restart.ww3 ]   && mv fine/restart.ww3   restart.fine
    [ -f fine/wind.ww3 ]      && mv fine/wind.ww3      wind.fine
    [ -f fine/current.ww3 ]   && mv fine/current.ww3   current.fine
    [ -f fine/level.ww3 ]     && mv fine/level.ww3     level.fine
    [ -f fine/ice.ww3 ]       && mv fine/ice.ww3       ice.fine
    [ -f fine/ice1.ww3 ]      && mv fine/ice1.ww3      ice.fine
    
    ######################################
    # Run MPI program (nested grid mode)
    ######################################
    echo -e "
============================== Running mpirun ww3_multi ==============================" >> "$ALL_LOG"
    mpirun -n $MPI_NPROCS ww3_multi --casename=$CASENAME > "$RUN_LOG" 2>&1
    rc_mpi=$?
    cat "$RUN_LOG" >> "$ALL_LOG"
    
    if [ $rc_mpi -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_mpi
    fi
    
    [ -f out_grd.fine ] && mv out_grd.fine fine/out_grd.ww3
    [ -f mod_def.fine ] && mv mod_def.fine fine/mod_def.ww3
    [ -f out_pnt.fine ] && mv out_pnt.fine fine/out_pnt.ww3
    
    ######################################
    # Export results (nested grid mode)
    ######################################
    cd fine
    rc_export=0
    if [ -f points.list ]; then
        echo -e "
============================== Running ww3_ounp ==============================" >> "$ALL_LOG"
        ww3_ounp >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ] && [ -f track_i.ww3 ]; then
        echo -e "
============================== Running ww3_trnc ==============================" >> "$ALL_LOG"
        ww3_trnc >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi
    
    if [ $rc_export -eq 0 ]; then
        echo -e "
============================== Running ww3_ounf ==============================" >> "$ALL_LOG"
        ww3_ounf >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi
    cd ..
    if [ $rc_export -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_export
    fi
    
    ######################################
    # All done (nested grid mode)
    ######################################
    cat "$ALL_LOG" > "$SUCCESS_LOG"
else
    # Regular grid mode
    echo -e "
============================== Running ww3_grid ==============================" >> "$ALL_LOG"
    ww3_grid >> "$ALL_LOG" 2>&1
    run_prnc_with_fields
    echo -e "
============================== Running ww3_strt ==============================" >> "$ALL_LOG"
    ww3_strt >> "$ALL_LOG" 2>&1
    
    ######################################
    # Run MPI program (regular grid mode)
    ######################################
    run_ww3_shel_with_fallback
    rc_shel=$?

    if [ $rc_shel -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_shel
    fi
    
    ######################################
    # Export results (regular grid mode)
    ######################################
    rc_export=0
    if [ -f points.list ]; then
        echo -e "
============================== Running ww3_ounp ==============================" >> "$ALL_LOG"
        ww3_ounp >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ] && [ -f track_i.ww3 ]; then
        echo -e "
============================== Running ww3_trnc ==============================" >> "$ALL_LOG"
        ww3_trnc >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ]; then
        echo -e "
============================== Running ww3_ounf ==============================" >> "$ALL_LOG"
        ww3_ounf >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi
    if [ $rc_export -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_export
    fi
    
    ######################################
    # All done (regular grid mode)
    ######################################
    cat "$ALL_LOG" > "$SUCCESS_LOG"
fi

