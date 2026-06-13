"""
##  Convert SMC grid field into linear color indexes for plot. 
##
##  First created:    JGLi28Feb2019
##  Last modified:    JGLi03Apr2025
#;
"""

def smcliner( swhs, hgts, colrs ):

## Import relevant modules and functions
    import numpy as np
    from scale_liner import scale_liner

## Set up wave height linear scale and marks with colrs.N.
## colrs.N returns colrs' total number of colors 256.
#   hgts = [0,1,2,3,4,5,6]
    factor, marks, ncstr, nclrm = scale_liner(hgts, nclrm=colrs.N)

## Work out plotting height range.
    nswh0= ncstr
    hgts0= float(hgts[0])
    swhmn= -ncstr/factor + hgts0
    swhmx= float(hgts[-1])

    swhscl=[hgts, marks, nclrm, nswh0]

## Work out max and min values, excluding missing data (-999.0)
    cmax = swhs.max()
    cmin = swhs[ swhs > -999.0 ].min()
    print ( ' swh range %f, %f' % (cmin, cmax) )
    whmnx = [ f'WHmn = {cmin:10.3E}', \
              f'WHmx = {cmax:.3f}' ]

## Reset missing values (-999.0) to be -resmn1 
    swhs[ swhs < swhmn] = swhmn 

## Trim large values into plot range if any
    swhs[ swhs > swhmx ] = swhmx

## Convert swhs into linear color indexes.
    icnf = ncstr+ np.rint( factor*(swhs - hgts0) )
    nswh = np.array( icnf, dtype=int )

## Return converted indexes, SWH min-max text, and SWH scale.
    return ( nswh, whmnx, swhscl )

## End of smcliner function. 

