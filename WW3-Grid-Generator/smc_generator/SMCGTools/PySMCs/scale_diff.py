"""
#;;  scale_diff function to set up the color scale for difference plot, using 
#;;  the full 256 colors with zero roughly centred around color 128. 
#;;  First Created on  18 Nov 2019  by Jian-Guo Li
#;;  Last Modified on  18 Nov 2019  by Jian-Guo Li
#
# usage:    bottom, ceilng, factor, nmarks, ncstr, nclrm = 
#           scale_diff(dfrng, ncstr=2, nclrm=Colrs.N)
#
# Difference field will need to be converted by
#   ndiffs = ncstr + np.rint( factor*(difield - bottom) )
# to be consistent with the color key. 
#
"""

def scale_diff( dfrng, ncstr=2, nclrm=256 ):

    import numpy as np

    nlen=len(dfrng)
    if( nlen < 2 ):
        print( ' Inappropriate difference range: ', dfrng )
        print( ' Range list should have more than 2 elements!' )
        return

    difrnge=np.array(dfrng, dtype=float)
    difextd= (difrnge[nlen-1] - difrnge[0])*0.05
    bottom = difrnge[0] - difextd 
    ceilng = difrnge[nlen-1] + difextd 
    factor = (nclrm-2 - ncstr)/(ceilng - bottom)
    marks = ncstr + np.rint( factor*(difrnge - bottom) )
    nmarks = marks.astype(int)

    print( nclrm-ncstr, ' colors with marks at ', difrnge)

    return ( bottom, ceilng, factor, nmarks, ncstr, nclrm )


