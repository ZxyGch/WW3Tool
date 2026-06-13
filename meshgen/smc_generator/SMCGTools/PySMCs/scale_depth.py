"""
## scale_depth function to set up the color scale for depth plot, using the
## first 136 colors from a given color table of 256 colors.
## First Created:    22 Feb 2019    Jian-Guo Li
## Last Modified:    03 Apr 2025    Jian-Guo Li
##
## Bathymetry depth (positive) will need to be converted by
#    ndeps=np.rint((cstar-np.log10(depth+ndry))*factr).astype(np.int)
# to be consistent with the color key. 
#
"""

def scale_depth( ncstr=0, nclrm=136, ndry=11 ):

    import numpy as np

    depth=np.array([10000,1000,100,10,0,-ndry+1], dtype=int)
    cstar=np.log10(depth[0]+1000.0)
    factr=(nclrm - 1)/cstar
    marks= ncstr + np.rint((cstar-np.log10(depth+ndry))*factr).astype(int)
    print( nclrm, ' colors with depth marks at ', depth[::-1])

    return ( depth, factr, cstar, marks, ncstr, nclrm )

## End of function scale_depth.py.

