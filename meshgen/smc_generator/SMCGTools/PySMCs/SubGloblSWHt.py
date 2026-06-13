"""
## Program to draw Sub-grid global model SWH field.
##
## First created:    JGLi30Jun2011
## Converted into Python.    JGLi20Dec2018
## Adapted for 3 sub-grids SWH plots.    JGLi25Jan2021
## Last modified:    JGLi11Nov2025
##
"""

## Import relevant modules and functions
import gc
import os
import sys
import psutil
import numpy as np
import pandas as pd

## Only import Figure, no longer use pyplot.  JGLi05Nov2025
from matplotlib.figure import Figure

from datetime import datetime 
from readtext import readtext
from readcell import readcell
from rgbcolor import rgbcolor
from smcswhcv import smcswhcv 
from smcfield import smcfield 
from addtexts import addtexts 

def main():
    """ Draw SWH plot for Subi-grid global model. """

## Check input information file name if provided.
    print(sys.argv)
    if( len(sys.argv) > 1 ):
        if( len(sys.argv[1]) > 3 ):
            gridfile = sys.argv[1]
    else:
        gridfile = 'GridInfo61250Subs.txt'

## Read global grid information file. 
    with open( gridfile, 'r' ) as flhdl:
## First line contains merged global and sub-grid names. 
        nxlne = flhdl.readline().split()
        Subnms = list(nxlne) 
        Subdct = dict(enumerate(Subnms)) 
        print(" Global and sub-grid names = \n", Subnms)
## Second line contains zlon zlat dlon dlat of size-1 cell parameters.
        nxlne = flhdl.readline().split()
        zdlnlt = np.array(nxlne, dtype=float)
        print(" Input grid zlon zlat dlon dlat = \n", zdlnlt)
## Third line is the working directory and cell array subdirectory.
        nxlne = flhdl.readline().split()
        Wrkdir=nxlne[0]
        DatSub=nxlne[1]
        MCodes=nxlne[2]
        print(" Wrkdir, DatSub and MCodes = \n", nxlne)
## Fourth line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        nplc = int(nxlne[0])
        ngrd = int(nxlne[1])
        print(" Number of polar cells and sub-grids = ", nplc, ngrd)
## Final line is the SWH files and propagation test output directories.
        nxlne = flhdl.readline().split()
        SWHdir=nxlne[0]
        OutDat=nxlne[1]
        print(" SWH and Prop OutDat = \n", nxlne)

## Use own color map and defined depth colors 
    colrfile = MCodes+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Read start and end datetime from fdate
    datefl = open( MCodes+'strendat', 'r')
    strend = datefl.read().split()
    datefl.close()

## Convert into datetime variables
    start = datetime.strptime(strend[0], '%y%m%d%H')
    endat = datetime.strptime(strend[1], '%y%m%d%H')
    timdx = pd.date_range(start=start, end=endat, freq=strend[2])

## Prompt selection choices and ask for one input
    print (" \n ", Subdct)
    instr = input("\n *** Please enter your selected number here > ")
    m = int(instr)
    Gname=Subdct.get(m, 'Invalid_selection')
    if( Gname == 'Invalid_selection' ): 
        print ("Invalid selection, program terminated.")
        exit()

    print (" Draw SWH plots for "+Gname)

##  Choose global or local verts from different files.
    vrfile = DatSub+Gname+'Vrts.npz'
    vrtcls = np.load( vrfile )

    if( m == 0 ): 
        nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']
        svrts = vrtcls['svrt'] ; scels = vrtcls['scel']
        config = vrtcls['cnfg']
        print (' n/svrts/cels config read ') 

    else:
        nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel'] 
        config = vrtcls['cnfg']
        print (' nvrts, ncels and config read ') 

## Selected plot configuration parameters.
    sztpxy = config[1]
    rngsxy = config[2]
    papror='portrait'

## Alternative font sizes.
    fntsz=12.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz
    
    print (" SWH file loop started at ", datetime.now() )

## Use ijk to count how many times to draw.
    ijk=0

## Number of characters in sub-grid IDs for SubG61250 grid. 
    nid=4

#   for i in range( ndays*4 ):
    for dt in timdx:

##  Convert time step for output file and set plot filename.
        datms = dt.strftime('%Y%m%d%H')
        epsfl = Wrkdir+'swh'+Gname[0:nid]+datms[2:]+'.eps'

##  Read sub-grid SWH field and draw plot.
        if( m == 0 ):
            swhgrd=[]
            for j in range(ngrd):
                swhfl = SWHdir+Subnms[j+1][0:nid]+'/ww3.'+ dt.strftime('%y%m%d%H') + '.hs'
                hdlist, swh2d = readtext(swhfl)
                ms = int(hdlist[4])
                swhgrd.append(swh2d.flatten()[0:ms])
            print(" swhgrd length =",len(swhgrd))
            swhs = np.hstack( tuple(swhgrd) )

        else:
            swhfl = SWHdir+Gname[0:nid]+'/ww3.'+ dt.strftime('%y%m%d%H') + '.hs'
            hdlist, swh2d = readtext(swhfl)
            ms = int(hdlist[4])
            swhs = swh2d.flatten()[0:ms]

## Convert swh field into color indexes.
        nswh, swhmnx, swhscl = smcswhcv( swhs )
        txtary=[ [Gname,    'k', fntsb],
                 ['SWHmn='+swhmnx[0], 'b', fntsa],
                 ['SWHmx='+swhmnx[1]+' m', 'r', fntsa],
                 [datms,     'k', fntsb] ]

        if( m == 0 ):
## Open figure plt for 2 panels.
            fig=Figure(figsize=sztpxy[0:2])
            ax1=fig.add_subplot(1,2,1)

## Draw SWH field on northern heimisphere panel.
            smcfield(ax1, nswh, nvrts, ncels, colrs, config,
                     vscle=swhscl, vunit='SWH m')

## Draw field on southern hemisphere subplot panel.
            ax2=fig.add_subplot(1,2,2)
            smcfield(ax2, nswh, svrts, scels, colrs, config,
                     vscle=swhscl, vunit=' ')

## Put statistic information inside subplot ax2
            ax2.text(sztpxy[2], 9.0, Gname, color='r', 
                horizontalalignment='center', fontsize=fntsb)
            xydxdy=[sztpxy[2], sztpxy[3], 0.0, 0.6]
            addtexts(ax2, xydxdy, txtary[1:])

            fig.subplots_adjust(left=0.005, bottom=0.0, right=0.995, 
                                 top=1.0,  wspace=0.01, hspace=0.0)

        else:
## Open figure for a single plot. 
            fig=Figure(figsize=sztpxy[0:2])
            ax = fig.subplots()
            smcfield(ax, nswh, nvrts, ncels, colrs, config,
                     vscle=swhscl, vunit='SWH m')

## Put statistic information inside plot ax.
            xydxdy=[sztpxy[2], sztpxy[3], 0.0, -0.6]
            addtexts(ax, xydxdy, txtary)
            fig.subplots_adjust(left=0,bottom=0,right=1,top=1)

## Save grid plot as eps file.
        print (" ... saving the SWH grid plot as ", epsfl )
        fig.savefig(epsfl, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=papror)

## Clear figure contents and call memory cleaning function. 
        fig.clear()       # Clear figure contents.
        gc.collect()      # Gabbage collection call.

        # Print memory usage for diagnosis
        process = psutil.Process(os.getpid())
        memorys = f" Memory usage {process.memory_info().rss /(1024*1024):.2f} MB"

##  Increase ijk for next plot
        ijk += 1
        print (" Finish plot ", ijk," at ", datetime.now(), memorys)

##  End of date loop

## End of main() function. 

if __name__ == '__main__':
    main()

## End of SubGloblSWHts.py program.

