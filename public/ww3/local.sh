#!/bin/bash

set -o pipefail


# MPI process count for local run (keep consistent with previous)
MPI_NPROCS=10

# Treat current directory as script root (assumes running in case directory)
SCRIPT_ROOT="$(pwd)"

# Write run.log during execution; rename to success.log or fail.log at the end
LOG="$SCRIPT_ROOT/run.log"
SUCCESS_LOG="$SCRIPT_ROOT/success.log"
FAIL_LOG="$SCRIPT_ROOT/fail.log"
rm -f "$LOG" "$SUCCESS_LOG" "$FAIL_LOG"

# Run ww3_prnc for multiple forcing files
run_prnc_with_fields() {
    # Check for multiple forcing files
    if [ -f "ww3_prnc_current.nml" ] || [ -f "ww3_prnc_level.nml" ] || [ -f "ww3_prnc_ice.nml" ] || [ -f "ww3_prnc_ice1.nml" ]; then
        # Multiple forcing files found; process sequentially
        
        # 1) Run ww3_prnc once (default ww3_prnc.nml, usually wind)
        echo -e "
============================== Running ww3_prnc (wind) ==============================" | tee -a "$LOG"
        ww3_prnc 2>&1 | tee -a "$LOG"
        
        # 2) Rename ww3_prnc.nml -> ww3_prnc_wind.nml
        mv ww3_prnc.nml ww3_prnc_wind.nml
        
        # 3) Process other forcing files
        if [ -f "ww3_prnc_current.nml" ]; then
            echo -e "
============================== Running ww3_prnc (current) ==============================" | tee -a "$LOG"
            mv ww3_prnc_current.nml ww3_prnc.nml
            ww3_prnc 2>&1 | tee -a "$LOG"
            mv ww3_prnc.nml ww3_prnc_current.nml
        fi
        
        if [ -f "ww3_prnc_level.nml" ]; then
            echo -e "
============================== Running ww3_prnc (level) ==============================" | tee -a "$LOG"
            mv ww3_prnc_level.nml ww3_prnc.nml
            ww3_prnc 2>&1 | tee -a "$LOG"
            mv ww3_prnc.nml ww3_prnc_level.nml
        fi
        
        if [ -f "ww3_prnc_ice.nml" ]; then
            echo -e "
============================== Running ww3_prnc (ice) ==============================" | tee -a "$LOG"
            mv ww3_prnc_ice.nml ww3_prnc.nml
            ww3_prnc 2>&1 | tee -a "$LOG"
            mv ww3_prnc.nml ww3_prnc_ice.nml
        fi

        if [ -f "ww3_prnc_ice1.nml" ]; then
            echo -e "
============================== Running ww3_prnc (ice1) ==============================" | tee -a "$LOG"
            mv ww3_prnc_ice1.nml ww3_prnc.nml
            ww3_prnc 2>&1 | tee -a "$LOG"
            mv ww3_prnc.nml ww3_prnc_ice1.nml
        fi
        
        # 4) Restore ww3_prnc_wind.nml -> ww3_prnc.nml
        mv ww3_prnc_wind.nml ww3_prnc.nml
    else
        # Only one ww3_prnc.nml; run directly
        echo -e "
============================== Running ww3_prnc ==============================" | tee -a "$LOG"
        ww3_prnc 2>&1 | tee -a "$LOG"
    fi
}

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

# Detect nested grid mode
if [ -d "coarse" ] && [ -d "fine" ]; then
    ######################################
    # Nested grid mode
    ######################################
    echo -e "
============================== Running ww3_grid (coarse) ==============================" | tee -a "$LOG"
    cd coarse
    ww3_grid 2>&1 | tee -a "$LOG"
    run_prnc_with_fields
    echo -e "
============================== Running ww3_strt (coarse) ==============================" | tee -a "$LOG"
    ww3_strt 2>&1 | tee -a "$LOG"
    cd ..
    
    echo -e "
============================== Running ww3_grid (fine) ==============================" | tee -a "$LOG"
    cd fine
    ww3_grid 2>&1 | tee -a "$LOG"
    run_prnc_with_fields
    echo -e "
============================== Running ww3_strt (fine) ==============================" | tee -a "$LOG"
    ww3_strt 2>&1 | tee -a "$LOG"
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
        [ -f "$LOG" ] && mv "$LOG" "$FAIL_LOG"
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
============================== Running ww3_ounp (fine) ==============================" | tee -a "$LOG"
        ww3_ounp 2>&1 | tee -a "$LOG"
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ] && [ -f track_i.ww3 ]; then
        echo -e "
============================== Running ww3_trnc (fine) ==============================" | tee -a "$LOG"
        ww3_trnc 2>&1 | tee -a "$LOG"
        rc_export=$?
    fi
    
    if [ $rc_export -eq 0 ]; then
        echo -e "
============================== Running ww3_ounf (fine) ==============================" | tee -a "$LOG"
        ww3_ounf 2>&1 | tee -a "$LOG"
        rc_export=$?
    fi
    cd ..
    if [ $rc_export -ne 0 ]; then
        [ -f "$LOG" ] && mv "$LOG" "$FAIL_LOG"
        exit $rc_export
    fi
    [ -f "$LOG" ] && mv "$LOG" "$SUCCESS_LOG"
else
    ######################################
    # Regular grid mode
    ######################################
    echo -e "
============================== Running ww3_grid ==============================" | tee -a "$LOG"
    ww3_grid 2>&1 | tee -a "$LOG"
    run_prnc_with_fields
    echo -e "
============================== Running ww3_strt ==============================" | tee -a "$LOG"
    ww3_strt 2>&1 | tee -a "$LOG"
    
    ######################################
    # Run MPI program (regular grid mode)
    ######################################
    run_ww3_shel_with_fallback
    rc_shel=$?
    if [ $rc_shel -ne 0 ]; then
        [ -f "$LOG" ] && mv "$LOG" "$FAIL_LOG"
        exit $rc_shel
    fi
    
    ######################################
    # Export results (regular grid mode)
    ######################################
    rc_export=0
    if [ -f points.list ]; then
        echo -e "
============================== Running ww3_ounp ==============================" | tee -a "$LOG"
        ww3_ounp 2>&1 | tee -a "$LOG"
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ] && [ -f track_i.ww3 ]; then
        echo -e "
============================== Running ww3_trnc ==============================" | tee -a "$LOG"
        ww3_trnc 2>&1 | tee -a "$LOG"
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ]; then
        echo -e "
============================== Running ww3_ounf ==============================" | tee -a "$LOG"
        ww3_ounf 2>&1 | tee -a "$LOG"
        rc_export=$?
    fi
    if [ $rc_export -ne 0 ]; then
        [ -f "$LOG" ] && mv "$LOG" "$FAIL_LOG"
        exit $rc_export
    fi
    [ -f "$LOG" ] && mv "$LOG" "$SUCCESS_LOG"
fi
