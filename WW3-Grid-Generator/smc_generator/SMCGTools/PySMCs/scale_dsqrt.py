"""
## Function to set up the color scale for difference plot, using 
## the full 256 colors with zero roughly centred around color 110. 
##
## First Created:    18 Nov 2019  Jian-Guo Li
## Last Modified:    06 Apr 2025  Jian-Guo Li
##
## Usage:    bottom, ceilng, factor, nmarks, ncstr, nclrm = \
##           scale_dsqrt(dfrng, ncstr=2, nczro=110, nclrm=Colrs.N)
##
## Difference field convertion see dfrng convertion below.
##
"""

def scale_dsqrt( dfrng, ncstr=2, nczro=110, nclrm=256 ):

    import numpy as np

    nlen=len(dfrng)
    if( nlen < 2 ):
        print( ' Inappropriate difference range: ', dfrng )
        print( ' Range list should have more than 2 elements!' )
        return

##  Convert array into sqrt of its original magnitude, keeping sign.
    difinp=np.array(dfrng, dtype=float)
    difsgn=np.sign(difinp)
    difrnge = difsgn*np.sqrt( difsgn*difinp )
    
    difextd= 0.4*(difrnge[nlen-1] - difrnge[0])/nlen
    bottom = difrnge[0] - difextd 
    ceilng = difrnge[nlen-1] + difextd 

    fctpos = (nclrm - nczro)/ceilng 
    fctneg = (ncstr - nczro)/bottom

    marks = np.arange(nlen)
    for k in range(nlen):
        if( difrnge[k] >= 0.0 ):
            marks[k]=difrnge[k]*fctpos + nczro
        if( difrnge[k] <  0.0 ):
            marks[k]=(difrnge[k]-bottom)*fctneg + ncstr
   
    nmarks = marks.astype(int)

    print( nclrm-ncstr, ' colors with marks at ', dfrng)

    return ( bottom, ceilng, fctneg, fctpos, nmarks, ncstr, nczro, nclrm )

## End of function scale_dsqrt.py.

