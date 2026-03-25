"""
## Convert water height field into linear color indexes for plot. 
##
## First created:    JGLi28Feb2019
## Last modified:    JGLi16Apr2025
##
"""

def whtliner( whts, whtmrks, ncstr=3, nclrm=253, fmdi=-9999.0 ):

## Import relevant modules and functions
    import numpy as np
    from scale_liner import scale_liner

## Set up wave height linear scale and marks with nclrm colours.
    factor, marks, ncstr, nclrm = scale_liner(whtmrks, ncstr=ncstr, nclrm=nclrm)

## Work out plotting height range by given water height marks.
    whtcs = float(whtmrks[0])
    whtmn = -ncstr/factor + whtcs 
    whtmx = float(whtmrks[-1])
   
## Last integer is reserved for marking with blank cells if no-zero.
    whtscl=[whtmrks, marks, nclrm, ncstr ]

## Work out max and min values, excluding missing data (-999.0)
    cmax = whts.max()
    cmin = whts[ whts > fmdi ].min()
    idxmax=list(whts).index(cmax)
    idxmin=list(whts).index(cmin)

    print ( ' whdif ranges %f, %f' % (cmin, cmax) )
    print ( ' min/max cell %d, %d' % (idxmin, idxmax) )

    whtmnx =[ f'{cmin:10.3E}', f'{cmax:.3f}', \
              f'{idxmin:d}',   f'{idxmax:d}' ]

## Trim whts values within whtmrks range. 
    whts[ whts < whtmn] = whtmn 

## Trim large values into plot range if any
    whts[ whts > whtmx ] = whtmx

## Convert whts into linear color indexes.
    cnvdf = ncstr+ np.rint( factor*(whts - whtcs) )
    nwhts = np.array( cnvdf, dtype=int )

## Return converted indexes, WHt min-max text, and WHt scale.
    return ( nwhts, whtmnx, whtscl )

## End of whtliner function. 

