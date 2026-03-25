"""
## scale_liner function to set up linear color scale, using given
## marks range for nclrm color indexes. 
##
## First Created:  Jian-Guo Li    22 Feb 2019
## Last Modified:  Jian-Guo Li    16 Apr 2025
#
# usage:    factor, marks, ncstr, nclrm = scale_liner(heights, ncstr=3, nclrm=253)
#
# For consistency height should be converted by
#   nheight = ncstr + np.rint( factor*(height-heights[0]) ).astype(int)
#
"""

def scale_liner( heights, ncstr=3, nclrm=253 ):

    import numpy as np

    fhigts = np.array(heights, dtype=float)
    rhigts = fhigts[-1] - fhigts[0]
    extens = rhigts*0.02
    factor = (nclrm - ncstr)/(rhigts + extens) 
    marks = ncstr + np.rint( factor*(fhigts-fhigts[0]) ).astype(int)
    print( ncstr, nclrm, ' colors with height marks at ', heights[:] )

    return ( factor, marks, ncstr, nclrm )

##  End of function scale_liner.py.

