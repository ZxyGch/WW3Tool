"""
##  First created:    JGLi16Feb2012
##  Converted into Python.    JGLi20Dec2018
##  AMM153km PropOMP test.    JGLi11Jul2023
##  Modified for AMM153km.    JGLi26Jul2023
##  Last modified:    JGLi10Nov2025
##
"""

## Import relevant modules and functions
import sys
import numpy  as np
import pandas as pd

from matplotlib.figure import Figure
from datetime import datetime 
from readtext import readtext
from readcell import readcell
from rgbcolor import rgbcolor
from smcswhcv import smcswhcv 
from smcfield import smcfield 
from addtexts import addtexts 

def main( ):

## Check input information file name if provided.
    print(sys.argv)
    if( len(sys.argv) > 1 ):
        if( len(sys.argv[1]) > 3 ):
            gridfile = sys.argv[1]
    else:
        gridfile = 'GridInfoAMM153.txt'

## Read rotated grid information file. 
    with open( gridfile, 'r' ) as flhdl:
## First line contains grid name and number of resolution levels.
        nxlne = flhdl.readline().split()
        Gname = nxlne[0]
        Level = int(nxlne[1])
        print(" Input grid name and number of levl= ", Gname, Level)
## Second line contains zlon zlat dlon dlat of size-1 cell parameters.
        nxlne = flhdl.readline().split()
        zdlnlt = np.array(nxlne, dtype=float)
        print(" Input grid zlon zlat dlon dlat = \n", zdlnlt) 
## Third line is the working directory and cell array subdirectory.
        nxlne = flhdl.readline().split()
        Wrkdir=nxlne[0]
        DatGMC=nxlne[1]
        MCodes=nxlne[2]
        print(" Working directory and DatGMC = \n", nxlne) 
## Forth line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        npl = int(nxlne[0])
        print(" Number of polar cells = ", npl) 
## Fifth line stores the rotated polon and polat values.
        nxlne = flhdl.readline().split()
        Polon = float(nxlne[0])
        Polat = float(nxlne[1])
        print(" Rotated N Polon Polat = ", Polon, Polat) 
## Final line is the SWH files and propagation test output directories.
        nxlne = flhdl.readline().split()
        SWHdir=nxlne[0]
        OutDat=nxlne[1]
        nhrmdl=int(nxlne[2])
        print(" SWH and Prop OutDat = \n", nxlne)
## End of reading grid information file.

## Read grid cell array. 
    Cel_file = DatGMC+Gname+'Cels.dat'
    headrs, cel = readcell( [Cel_file] )
    numbrs = np.array( headrs[0].split() ).astype(int)
    print( numbrs )
    ng = numbrs[0]
    na = nb = 0
    nc = ng 
    print (' Merged total cel number = %d' % nc )

## Use own color map and defined depth colors 
    colrfile = MCodes+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

    print (" Draw Propagation test SWH plots for "+Gname)

## Read precalcuated polygon verts from saved file.
    vrfile = DatGMC+Gname+'Vrts.npz'
    vrtcls = np.load( vrfile )
    nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel'] 
    config = vrtcls['cnfg']
    print (' nvrts, ncels and config read ' )

## Selected plot configuration parameters.
    sztpxy = config[1]
    rngsxy = config[2]

## Alternative font sizes.
    fntsz=12.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz

## Define spectral direction
    ndir=24
    theta=np.arange(ndir)*np.pi*2.0/ndir

## Add a spectral array plots for the Northern stripe 
    x0= 3.0
    y0= 5.0
    t0=np.pi*0.25
    cs=np.cos(theta + t0)
    xn=theta*0.0+x0
    yn=theta*0.0+y0
    for i in range(ndir):
        if( cs[i] > 0.0 ): 
            spc=1.2*cs[i]*cs[i]
            xn[i]=x0+spc*np.cos(theta[i])
            yn[i]=y0+spc*np.sin(theta[i])

## Add another spectral array plots for the Southern stripe 
    x1=-2.0
    y1=-8.0
    cs=np.cos(theta - t0)
    xs=theta*0.0+x1
    ys=theta*0.0+y1
    for i in range(ndir):
        if( cs[i] > 0.0 ): 
            spc=1.2*cs[i]*cs[i]
            xs[i]=x1+spc*np.cos(theta[i])
            ys[i]=y1+spc*np.sin(theta[i])

## Polar disk spectral array uses the Southern one but new location
    xp= 3.0
    yp= 8.0

## Atlantic disk spectral array uses the Southern one but new location
    xt=-1.0
    yt=-2.0

## Use ijk to count how many times to draw.
    ijk=0

## Specify number of steps per hour (DTG = 360 s)
    nhr=10
    if( nhr != nhrmdl ):
        nhr = mhrmdl
        print(" *** Warning: nhr reset to input value:", nhr)

## Read in cell concentration data files from a list file
    hdr, cnfiles = readtext(OutDat+'cfiles.txt')
    cfiles = cnfiles.astype(str).reshape(len(cnfiles))

## loop over available files 
    for nn in range(0,len(cnfiles),2):
#   for nn in range(0,len(cnfiles),1):
        dfile=OutDat+cfiles[nn] 

        hdlist, swh2d = readtext(dfile)
        mt = int(hdlist[0])
        mc = int(hdlist[1])
        swhs = swh2d.flatten()[0:mc]

## Check input data number matches cell number. 
        if( mc != nc ):
            print ( ' Unmatching mc/nc = %d %d' % (mc, nc) ) 
            exit()
        else:
            print (' Plotting cell number mc = %d' % mc )

## Convert time step for output file
        ntsp='NTS = %5d' % (mt)
        thrs='T = %6.2f hr' % (float(mt)/nhr) 

## Convert swh field into color indexes.
        nswh, swhmnx, swhscl = smcswhcv( swhs )

        txtary=[ [Gname+' SWH',       'k', fntsb],
                 ['SWHmn='+swhmnx[0], 'b', fntsa],
                 ['SWHmx='+swhmnx[1]+' m', 'r', fntsa],
                 [thrs,  'k', fntsb] ] 

## Call function to draw the swh plot.
        epsfl = Wrkdir + 'Hs' + cfiles[nn][2:7] + '.eps'
        fig = Figure( figsize=sztpxy[0:2] )
        ax = fig.subplots()

        smcfield(ax, nswh, nvrts, ncels, colrs, config,
                 vscle=swhscl, vunit='SWH m')

## Put statistic information inside plot ax.
        xydxdy=[sztpxy[2], sztpxy[3], 0.0, -0.6]
        addtexts(ax, xydxdy, txtary)
        fig.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)

## Save plot and clear figure contents.
        print(" ... Saving plot as", epsfl )
        fig.savefig(epsfl, dpi=None,facecolor='w',edgecolor='w', 
            orientation='portrait')
        fig.clear()

## Increase ijk for next plot
        ijk += 1
        print (" Finish plot No.", ijk," at ", datetime.now())

## End of date loop

## End of AMM153kmProps.py main program. 

if __name__ == '__main__':
    main()

## End of program AMM153kmProps.py.

