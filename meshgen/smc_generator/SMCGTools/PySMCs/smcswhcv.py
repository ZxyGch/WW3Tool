"""
## Convert SWH field into color indexes for plot. 
##
## First created:    JGLi28Feb2019
## Last modified:    JGLi16Jul2025
##
"""

def smcswhcv( swhs, waveht=[], ncstr=2, nclrm=254, fmdi=-999.0 ):

## Import relevant modules and functions
    import numpy as np
    from scale_logwh import scale_logwh

## Set up wave height scale and marks with default waveht marks.
    if( len(waveht) < 2 ): waveht=[0, 1, 2, 4, 8, 16, 32]
    whtmrks, factor, residu, marks, ncstr, nclrm = \
        scale_logwh(waveht=waveht, ncstr=ncstr, nclrm=nclrm)

## The last value nswh0 is the color index for missing data cells.
    nswh0 = max([0, ncstr-1])
    swhscl=[waveht, marks, nclrm, nswh0]

## Work out max and min values, excluding missing data (-999.0)
    cmax = swhs.max()
    cmin = swhs[ swhs > fmdi ].min()
    idxmax=list(swhs).index(cmax)
    idxmin=list(swhs).index(cmin)
    print ( ' SWH range %f, %f' % (cmin, cmax) )
    swhmnx = [ f'{cmin:10.3E}', f'{cmax:.3f}', \
               f'{idxmin:d}',   f'{idxmax:d}' ]

## Find missing data indexes before resetting them.
    mdidxes = swhs <= fmdi

## Reset swhs within waveht range.
    swhs[ swhs < waveht[ 0] ] = waveht[ 0]
    swhs[ swhs > waveht[-1] ] = waveht[-1]

## Convert swhs with logarithm scale.
    nswh = ncstr+ np.rint( factor*np.log(swhs+residu) ).astype(int)

## Assign nswh0 to missing data points.
    nswh[mdidxes] = nswh0
 
## Return converted indexes, SWH min-max text, and SWH scale.
    return ( nswh, swhmnx, swhscl )

## End of smcswhcv function. 

