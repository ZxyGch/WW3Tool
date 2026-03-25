"""
#;;  rgbcolor function to set up the rainbow color with 0 to 255 index. 
#;;  First Created on  18 Dec 2018  by Jian-Guo Li
#;;  Last Modified on  26 Feb 2025  by Jian-Guo Li
#
# name:     rgbcolor
#
# purpose:  read rgbspectrum.dat color table file and setup as a colormap in Python.
#
# usage:    colrs = rgbcolor() 
#
# input:    rgbspectrum.dat  color table file in the current directiory.
#
# output:   colrs colormap object of 256 tuples, each may be used as colrs(i) 
#
"""

def rgbcolor( colrfile ):

    import numpy as np
    import matplotlib as mpl

    clsrgb = np.genfromtxt(colrfile, dtype=int, skip_header=1)
    clsnm = clsrgb/float( clsrgb.max() ) 
    colrs = mpl.colors.ListedColormap(clsnm, name='Spectra')

    nclrm = colrs.N  ## colrs.N returns the total number of colors 256.
    normd = mpl.colors.Normalize(vmin=0, vmax=nclrm-1)

    return colrs

##  print('... Finishing rgbcolor.py ...')


