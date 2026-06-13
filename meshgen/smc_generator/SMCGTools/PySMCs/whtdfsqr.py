"""
## Function to convert WHt difference with square root scales. 
## 
## First created:    JGLi18Nov2019
## Last modified:    JGLi16Nov2025
## 
"""

def whtdfsqr(whts, whtdif, nclrm=256, nczro=111): 

##  Import relevant modules and functions
    import numpy as np
    from scale_dsqrt import scale_dsqrt

## Set up difference scale marks or use given whtdif marks.
    if( len(whtdif) < 2 ):
        print(" whtdif not enough whtdifs= ", whtdif)
        return

## Use different square root scale for negative and positive whtdif 
## with zero at nczro and full color range up to nclrm.
    bottom, ceilng, fctneg, fctpos, marks, ncstr, nczro, nclrm \
          = scale_dsqrt(whtdif, nczro=nczro, nclrm=nclrm)

#   print( ' bottom, ceilng, fctneg, fctpos, nclrm = %f, %f, %f, %f, %d' % \
#           (bottom, ceilng, fctneg, fctpos, nclrm) ) 

## Scale parameters to be passed back.
    whdscl=[whtdif, marks, nclrm, ncstr]

## Work out max and min values, excluding missing data fmdi
    fmdi = -1.0E4
    cmax = whts.max()
    cmin = whts[ whts > fmdi ].min()
    idxmax=list(whts).index(cmax)
    idxmin=list(whts).index(cmin)

    print ( ' whdif ranges %f, %f' % (cmin, cmax) )
#   print ( ' min/max cell %d, %d' % (idxmin, idxmax) )
#   whdmnx =[ f'{cmin:10.3E}', f'{cmax:.3f}', \
    whdmnx =[ f'{cmin:.4f}', f'{cmax:.4f}', \
              f'{idxmin:d}', f'{idxmax:d}' ]

## Convert array into sqrt of its original magnitude, keeping sign.
    whtsgn= np.sign(whts)
    whtnew= whtsgn*np.sqrt( whtsgn*whts )
    mwht = whts.shape[0]
    icnf = np.arange(mwht)
    
## Scale whts to determine color index
    fzero = 1.0E-38
    for k in range(mwht):
## Black or nczro colors for nearly zero values
        if( abs(whts[k]) <= fzero ):
            icnf[k]= nczro
## None zero values use other colors
        if( whts[k] >  fzero ):
            icnf[k]=min([ceilng, whtnew[k]])*fctpos + nczro + 1
        if( whts[k] < -fzero ):
            icnf[k]=max([whtnew[k]-bottom, 0.0])*fctneg + ncstr

## Convert icnf float array into integer one 
    nwhts = np.array( icnf, dtype=int )

## Return converted indexes, SWH min-max text, and SWH scale.
    return ( nwhts, whdmnx, whdscl )

## End of whtdfsqr function. 

