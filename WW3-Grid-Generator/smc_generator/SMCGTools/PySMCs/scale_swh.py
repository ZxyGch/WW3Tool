"""
#;;  scale_swh function to set up the color scale for SWH plot, using given
#;;  color table with 0 to 255 index. 
#;;  First Created on  22 Feb 2019  by Jian-Guo Li
#;;  Last Modified on  26 Feb 2019  by Jian-Guo Li
#
# usage:    waveht, factor, residu, marks, ckeys = scale_swh( nclrm=colrs.N )
#
# For consistency wave height should be converted by
#   nswh=np.rint( factor*np.log(waveht+residu) ).astype(np.int)
#
"""

def scale_swh( ncstr=0, nclrm=256 ):

    import numpy as np

    waveht=np.array([0,1,2,4,8,16,32], dtype=int)
    factor=(nclrm - 2)/np.log(35.0)
    residu=np.exp(5.0/factor)
    marks=ncstr + np.rint( factor*np.log(waveht+residu) ).astype(int)
    print( ncstr, nclrm, ' colors with waveheight marks at ', waveht[:] )

    return ( waveht, factor, residu, marks, ncstr, nclrm )


