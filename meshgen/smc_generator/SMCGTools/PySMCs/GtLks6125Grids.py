"""
## Program to draw the Great Lakes 6125 SMC grid.
##
## First created:    JGLi20Apr2021
## Last modified:    JGLi04Jun2025
##
"""

def main():

## Import relevant modules and functions
    import numpy as np
    import matplotlib.pyplot as plt

    from datetime import datetime
    from readcell import readcell   
    from rgbcolor import rgbcolor
    from smcgrids import smcgrids
    from addtexts import addtexts
    from smcelvrts import smcelvrts

    print( " Program started at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Gt Lakes grid information from file.
    with open( './GridInfoGtLks.txt', 'r' ) as flhdl:
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
        print(" Working directory and DatGMC = \n", nxlne) 
## Final line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        npl = int(nxlne[0])
        print(" Number of polar cells = ", npl) 

##  Read global and Arctic part cells. 
    Cel_file = DatGMC+Gname+'Cels.dat' 
    Model='GtLakes6125'

    headrs, cel = readcell( [Cel_file] ) 
    nc = int( headrs[0].split()[0] )
    ncs= np.array( headrs[0].split() ).astype(int) 
    print (Model+' total cel number = %d' % nc )
    print (' N1, N2, N4, N8 cel number = ', ncs[1:])

## Initial txtary list as [txt, colr, fontsize].
    fntsz = 12.0
    fntsa = 1.25*fntsz
    fntsb = 1.50*fntsz

    txtary = [ [Model+' Grid', 'k', fntsb],
               ['NC='+str(nc), 'r', fntsa] ] 

##  Use own color map and defined depth colors 
    colrfile = './rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

##  Maximum mapping radius.
    radius=10.0

    print (" Draw grid for "+Model )

## Gt Lakes regional plot.
    pangle= 4.50 
    plon= 276.0
    plat=  45.3
    clrbxy=[  2.0,  6.0,   9.0,  0.8]
    sztpxy=[ 15.0, 10.0, -11.0, -3.0]
    rngsxy=[-15.0, 15.0, -10.0, 10.0]
    papror='portrait'

## Projection pole lon-lat and angle
    rdpols=[radius, pangle, plon, plat]

    print( " Start loop over cells at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Create cell vertices
    nvrts, ncels, svrts, scels, nsmrk = smcelvrts( cel, zdlnlt, 
           rdpols, rngsxy ) 

## Set plot size and limits and message out anchor point.
    config=np.array([rdpols, sztpxy, rngsxy, clrbxy])
    pzfile=DatGMC+Gname+'Vrts.npz'

## Store selected north and south verts and cell numbers for swh plots.
## Use the np.savez to save 3/5 variables in one file.  JGLi22Feb2019 
    np.savez( pzfile, nvrt=nvrts, ncel=ncels, cnfg=config) 

## These variables could be loaded back by
#   vrtcls = np.load(DatGMC+Gname+'Vrts.npz')
#   nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']; config=vrtcls['cnfg']; 

## Draw your selected grid plot.
    epsfile=Wrkdir+Gname+'grds.eps' 

    fig, ax = plt.subplots(figsize=sztpxy[0:2])
    smcgrids(ax, cel, nvrts,ncels,colrs,config) 

    xydxdy=[sztpxy[2],sztpxy[3], 0.0, -0.6]
    addtexts(ax, xydxdy, txtary)

    plt.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)

    print(" ...... Saving file ", epsfile)
    plt.savefig(epsfile, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=papror)
    plt.close()

    print( " Program finished at %s " % datetime.now().strftime('%F %H:%M:%S') )

## End of main function. 

if __name__ == '__main__':
    main()

## End of GtLks6125Grids program ##

