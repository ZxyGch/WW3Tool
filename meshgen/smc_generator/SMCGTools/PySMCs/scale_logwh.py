"""
## scale_logwh function sets up a logarithmic color scale for SWH. 
## Shift negative marks to positive and extend end mark by a margin. 
##
## First Created:    JGLi22Feb2019 
## Last Modified:    JGLi26May2025 
##
## usage: whtmrks, factor, residu, marks, ncstr = \
##          scale_logwh(waveht=[], ncstr=2, nclrm=254)
##
## For consistency with whtmrks, wave height should be converted by
## nwht = ncstr + np.rint(factor*np.log(waveht+residu)).astype(int)
##
"""

def scale_logwh( waveht=[], ncstr=2, nclrm=254 ):

    import numpy as np

## Define whtmrks if not provided.
    if( len(waveht) < 2 ):
        waveht=[0,1,2,4,8,16,32]
    whtmrks=np.array(waveht, dtype=float)

## Shift negative marks to positive if any.
    residu = max( [1.0, 1.0-whtmrks[0]] )
    wexend = whtmrks[-1] + residu + 3.0
    factor = (nclrm - ncstr)/np.log(wexend)
    marks = ncstr + np.rint( factor*np.log(whtmrks+residu) ).astype(int)
    print( ncstr, nclrm, ' colors with waveheight marks at ', whtmrks[:] )

## Return waveht and conversion parameters.
    return ( waveht, factor, residu, marks, ncstr, nclrm )

## End of scale_logwh.py function.

