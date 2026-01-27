#!/bin/bash
#SBATCH -J 202501
#SBATCH -p CPU6240R
#SBATCH -n 48
#SBATCH -N 1
#SBATCH --time=2880:00:00


set -o pipefail

ulimit -s unlimited

# 检查是否在 SLURM 环境中运行
# 如果不在，则使用 sbatch 提交自己
if [ -z "$SLURM_JOB_ID" ]; then
    # 获取脚本的绝对路径
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SCRIPT_PATH="$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")"
    
    sbatch "$SCRIPT_PATH"
    squeue -l
    exit $?
fi


# 注意：如果修改此值，请同时修改脚本开头的 #SBATCH -n 参数
MPI_NPROCS=48

# 案例名称（用于 ww3_shel 的 --casename 参数）
CASENAME=202501

# 保存脚本根目录
SCRIPT_ROOT="$(pwd)"

# 日志文件（使用绝对路径，确保在子目录中也能正确写入）
RUN_LOG="$SCRIPT_ROOT/mpirun.log"
ALL_LOG="$SCRIPT_ROOT/all.log"
FAIL_LOG="$SCRIPT_ROOT/fail.log"
SUCCESS_LOG="$SCRIPT_ROOT/success.log"

# 清理旧标志
rm -f "$FAIL_LOG" "$SUCCESS_LOG" "$ALL_LOG"

# 执行 ww3_prnc 的函数，处理多个强迫场文件
run_prnc_with_fields() {
    # 检查是否存在多个强迫场文件
    if [ -f "ww3_prnc_current.nml" ] || [ -f "ww3_prnc_level.nml" ] || [ -f "ww3_prnc_ice.nml" ] || [ -f "ww3_prnc_ice1.nml" ]; then
        # 存在多个强迫场文件，需要依次处理
        
        # 1. 先执行一次 ww3_prnc（使用默认的 ww3_prnc.nml，通常是风场）
        echo "=== Running ww3_prnc (wind) ===" >> "$ALL_LOG"
        ww3_prnc >> "$ALL_LOG" 2>&1
        
        # 2. 把 ww3_prnc.nml 改名为 ww3_prnc_wind.nml
        mv ww3_prnc.nml ww3_prnc_wind.nml
        
        # 3. 依次处理其他强迫场文件
        if [ -f "ww3_prnc_current.nml" ]; then
            echo "=== Running ww3_prnc (current) ===" >> "$ALL_LOG"
            mv ww3_prnc_current.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_current.nml
        fi
        
        if [ -f "ww3_prnc_level.nml" ]; then
            echo "=== Running ww3_prnc (level) ===" >> "$ALL_LOG"
            mv ww3_prnc_level.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_level.nml
        fi
        
        if [ -f "ww3_prnc_ice.nml" ]; then
            echo "=== Running ww3_prnc (ice) ===" >> "$ALL_LOG"
            mv ww3_prnc_ice.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_ice.nml
        fi

        if [ -f "ww3_prnc_ice1.nml" ]; then
            echo "=== Running ww3_prnc (ice1) ===" >> "$ALL_LOG"
            mv ww3_prnc_ice1.nml ww3_prnc.nml
            ww3_prnc >> "$ALL_LOG" 2>&1
            mv ww3_prnc.nml ww3_prnc_ice1.nml
        fi
        
        # 4. 最后把 ww3_prnc_wind.nml 改回 ww3_prnc.nml
        mv ww3_prnc_wind.nml ww3_prnc.nml
    else
        # 只有一个 ww3_prnc.nml，直接执行
        echo "=== Running ww3_prnc ===" >> "$ALL_LOG"
        ww3_prnc >> "$ALL_LOG" 2>&1
    fi
}

# 检测嵌套网格模式
if [ -d "coarse" ] && [ -d "fine" ]; then
    # 嵌套网格模式
    echo "=== Running ww3_grid (coarse) ===" >> "$ALL_LOG"
    cd coarse
    ww3_grid >> "$ALL_LOG" 2>&1
    run_prnc_with_fields
    ww3_strt >> "$ALL_LOG" 2>&1
    cd ..
    
    echo "=== Running ww3_grid (fine) ===" >> "$ALL_LOG"
    cd fine
    ww3_grid >> "$ALL_LOG" 2>&1
    run_prnc_with_fields
    ww3_strt >> "$ALL_LOG" 2>&1
    cd ..
    
    # Coarse 网格处理
    [ -f coarse/mod_def.ww3 ] && mv coarse/mod_def.ww3 mod_def.coarse
    [ -f coarse/restart.ww3 ] && mv coarse/restart.ww3 restart.coarse
    [ -f coarse/wind.ww3 ]    && mv coarse/wind.ww3    wind.coarse
    [ -f coarse/current.ww3 ] && mv coarse/current.ww3 current.coarse
    [ -f coarse/level.ww3 ]   && mv coarse/level.ww3   level.coarse
    [ -f coarse/ice.ww3 ]     && mv coarse/ice.ww3     ice.coarse
    [ -f coarse/ice1.ww3 ]    && mv coarse/ice1.ww3    ice.coarse

    # Fine 网格处理
    [ -f fine/mod_def.ww3 ]   && mv fine/mod_def.ww3   mod_def.fine
    [ -f fine/restart.ww3 ]   && mv fine/restart.ww3   restart.fine
    [ -f fine/wind.ww3 ]      && mv fine/wind.ww3      wind.fine
    [ -f fine/current.ww3 ]   && mv fine/current.ww3   current.fine
    [ -f fine/level.ww3 ]     && mv fine/level.ww3     level.fine
    [ -f fine/ice.ww3 ]       && mv fine/ice.ww3       ice.fine
    [ -f fine/ice1.ww3 ]      && mv fine/ice1.ww3      ice.fine
    
    ######################################
    # 运行 MPI 程序 (嵌套网格模式)
    ######################################
    echo "=== Running mpirun ww3_multi ===" >> "$ALL_LOG"
    mpirun -n $MPI_NPROCS ww3_multi --casename=$CASENAME > "$RUN_LOG" 2>&1
    rc_mpi=$?
    cat "$RUN_LOG" >> "$ALL_LOG"
    
    if [ $rc_mpi -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_mpi
    fi
    
    [ -f out_grd.fine ] && mv out_grd.fine fine/out_grd.ww3
    [ -f mod_def.fine ] && mv mod_def.fine fine/mod_def.ww3
    
    ######################################
    # 导出计算结果 (嵌套网格模式)
    ######################################
    cd fine
    rc_export=0
    if [ -f points.list ]; then
        echo "=== Running ww3_ounp ===" >> "$ALL_LOG"
        ww3_ounp >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ] && [ -f track_i.ww3 ]; then
        echo "=== Running ww3_trnc ===" >> "$ALL_LOG"
        ww3_trnc >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi
    
    if [ $rc_export -eq 0 ]; then
        echo "=== Running ww3_ounf ===" >> "$ALL_LOG"
        ww3_ounf >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi
    cd ..
    if [ $rc_export -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_export
    fi
    
    ######################################
    # 全部成功 (嵌套网格模式)
    ######################################
    cat "$ALL_LOG" > "$SUCCESS_LOG"
else
    # 普通网格模式
    echo "=== Running ww3_grid ===" >> "$ALL_LOG"
    ww3_grid >> "$ALL_LOG" 2>&1
    run_prnc_with_fields
    echo "=== Running ww3_strt ===" >> "$ALL_LOG"
    ww3_strt >> "$ALL_LOG" 2>&1
    
    ######################################
    # 运行 MPI 程序 (普通网格模式)
    ######################################
    echo "=== Running mpirun ww3_shel ===" >> "$ALL_LOG"
    mpirun -n $MPI_NPROCS ww3_shel --casename=$CASENAME > "$RUN_LOG" 2>&1
    rc_mpi=$?
    cat "$RUN_LOG" >> "$ALL_LOG"
    
    if [ $rc_mpi -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_mpi
    fi
    
    ######################################
    # 导出计算结果 (普通网格模式)
    ######################################
    rc_export=0
    if [ -f points.list ]; then
        echo "=== Running ww3_ounp ===" >> "$ALL_LOG"
        ww3_ounp >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ] && [ -f track_i.ww3 ]; then
        echo "=== Running ww3_trnc ===" >> "$ALL_LOG"
        ww3_trnc >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi

    if [ $rc_export -eq 0 ]; then
        echo "=== Running ww3_ounf ===" >> "$ALL_LOG"
        ww3_ounf >> "$ALL_LOG" 2>&1
        rc_export=$?
    fi
    if [ $rc_export -ne 0 ]; then
        cat "$ALL_LOG" > "$FAIL_LOG"
        exit $rc_export
    fi
    
    ######################################
    # 全部成功 (普通网格模式)
    ######################################
    cat "$ALL_LOG" > "$SUCCESS_LOG"
fi

