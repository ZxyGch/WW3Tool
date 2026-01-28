#!/bin/bash
set -e  # 遇到错误立即退出

# 执行 ww3_prnc 的函数，处理多个强迫场文件
run_prnc_with_fields() {
    # 检查是否存在多个强迫场文件
    if [ -f "ww3_prnc_current.nml" ] || [ -f "ww3_prnc_level.nml" ] || [ -f "ww3_prnc_ice.nml" ] || [ -f "ww3_prnc_ice1.nml" ]; then
        # 存在多个强迫场文件，需要依次处理
        
        # 1. 先执行一次 ww3_prnc（使用默认的 ww3_prnc.nml，通常是风场）
        ww3_prnc
        
        # 2. 把 ww3_prnc.nml 改名为 ww3_prnc_wind.nml
        mv ww3_prnc.nml ww3_prnc_wind.nml
        
        # 3. 依次处理其他强迫场文件
        if [ -f "ww3_prnc_current.nml" ]; then
            mv ww3_prnc_current.nml ww3_prnc.nml
            ww3_prnc
            mv ww3_prnc.nml ww3_prnc_current.nml
        fi
        
        if [ -f "ww3_prnc_level.nml" ]; then
            mv ww3_prnc_level.nml ww3_prnc.nml
            ww3_prnc
            mv ww3_prnc.nml ww3_prnc_level.nml
        fi
        
        if [ -f "ww3_prnc_ice.nml" ]; then
            mv ww3_prnc_ice.nml ww3_prnc.nml
            ww3_prnc
            mv ww3_prnc.nml ww3_prnc_ice.nml
        fi

        if [ -f "ww3_prnc_ice1.nml" ]; then
            mv ww3_prnc_ice1.nml ww3_prnc.nml
            ww3_prnc
            mv ww3_prnc.nml ww3_prnc_ice1.nml
        fi
        
        # 4. 最后把 ww3_prnc_wind.nml 改回 ww3_prnc.nml
        mv ww3_prnc_wind.nml ww3_prnc.nml
    else
        # 只有一个 ww3_prnc.nml，直接执行
        ww3_prnc
    fi
}

# 检测嵌套网格模式
if [ -d "coarse" ] && [ -d "fine" ]; then
    # 嵌套网格模式
    cd coarse
    ww3_grid
    run_prnc_with_fields
    ww3_strt
    cd ..
    
    cd fine
    ww3_grid
    run_prnc_with_fields
    ww3_strt
    cd ..
    
    # Coarse 网格处理
    [ -f coarse/mod_def.ww3 ] && mv coarse/mod_def.ww3 mod_def.coarse
    [ -f coarse/restart.ww3 ] && mv coarse/restart.ww3 restart.coarse
    [ -f coarse/wind.ww3 ]    && mv coarse/wind.ww3    wind.coarse
    [ -f coarse/current.ww3 ] && mv coarse/current.ww3 current.coarse
    [ -f coarse/level.ww3 ]   && mv coarse/level.ww3   level.coarse
    [ -f coarse/ice.ww3 ]     && mv coarse/ice.ww3     ice.coarse
    [ -f coarse/ice1.ww3 ]    && mv coarse/ice1.ww3    ice1.coarse

    # Fine 网格处理
    [ -f fine/mod_def.ww3 ]   && mv fine/mod_def.ww3   mod_def.fine
    [ -f fine/restart.ww3 ]   && mv fine/restart.ww3   restart.fine
    [ -f fine/wind.ww3 ]      && mv fine/wind.ww3      wind.fine
    [ -f fine/current.ww3 ]   && mv fine/current.ww3   current.fine
    [ -f fine/level.ww3 ]     && mv fine/level.ww3     level.fine
    [ -f fine/ice.ww3 ]       && mv fine/ice.ww3       ice.fine
    [ -f fine/ice1.ww3 ]      && mv fine/ice1.ww3      ice1.fine
    
    mpirun -n 10 ww3_multi
    
    [ -f out_grd.fine ] && mv out_grd.fine fine/out_grd.ww3
    [ -f mod_def.fine ] && mv mod_def.fine fine/mod_def.ww3
    [ -f out_pnt.fine ] && mv out_pnt.fine fine/out_pnt.ww3
    
    cd fine
    if [ -f points.list ]; then
        ww3_ounp
    fi

    if [ -f track_i.ww3 ]; then
        ww3_trnc
    fi
    
    ww3_ounf
    cd ..
else
    # 普通网格模式
    ww3_grid
    run_prnc_with_fields
    ww3_strt
    mpirun -n 10 ww3_shel
    
    if [ -f points.list ]; then
        ww3_ounp
    fi

    if [ -f track_i.ww3 ]; then
        ww3_trnc
    fi

    ww3_ounf
fi
