"""
## Merged program to draw global SMC grid with specified 
## input files for cell array and grid information.
## It reads cell files and uses own projection to draw 
## the SMC grid. Projected polygons are collected into 
## vert variables for grid and subsequent field plots. 
## Regional grid could be drawn with this program as well if
## drawing options are limited to suitable ones.
##
## First created:    JGLi26Nov2008
## Converted into a Python function.    JGLi05Dec2018
## Last modified:    JGLi18Jun2025
#
"""

def main():

## Import relevant modules and functions
    import os
    import sys
    import numpy as np
    import matplotlib.pyplot as plt

    from datetime import datetime
    from readcell import readcell   
    from rgbcolor import rgbcolor
    from smcgrids import smcgrids
    from addtexts import addtexts

    print( " Program started at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Check input information file name if provided.
    print(sys.argv)
    if( len(sys.argv) > 1 ):
        if( len(sys.argv[1]) > 3 ):
            gridfile = sys.argv[1]
    else:
        gridfile = 'GridInfo61250.txt'

## Read global grid information file. 
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
        print(" Working directory and DatGMC = \n", nxlne) 
## Final line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        npl = int(nxlne[0])
        print(" Number of polar cells = ", npl) 

## Read the cell array and Arctic part if any.
    Cel_file = [ DatGMC+Gname+'Cels.dat' ]
    if( npl > 0 ):
        Arc_file = DatGMC+Gname+'BArc.dat'
        Cel_file.append( Arc_file )

    headrs, cel = readcell( Cel_file ) 
    ng = int( headrs[0].split()[0] )
    nc = ng
    NArB = []
    if( npl > 0 ):
        NArB = headrs[1].split()
        na = int( NArB[0] )
        nb = int( NArB[1] )
        nbg= int( NArB[2] )
        nc = ng + na 
    print (' Merged total cel number = %d' % nc )

## Default Python library path of MyCodes.
    MyCodes='./'

## Initial txtary list as [txt, colr, fontsize].
    fntsz = 12.0
    fntsa = 1.25*fntsz
    fntsb = 1.50*fntsz

    txtary = [ [Gname+' Grid', 'k', fntsb],
               ['NC='+str(nc), 'r', fntsa] ] 
    
## Extra array in config for Arctic part
    Arctic = False
    nabgpl = []
    if( npl > 0 ):
        Arctic = True
        nabgpl = [na, nb, nbg, npl]
        txtary.append(['NA='+str(na), 'r', fntsz])
        txtary.append(['NB='+str(nb), 'r', fntsz])
  
## No excluded cell ids at present.
    excids=[]

## Use own color map and defined depth colors 
    colrfile = MyCodes+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Maximum mapping radius.
    radius=10.0

## Possible selection of your plot types. 
    gorloc={0:'Global', 1:'EuroArc',2:'Atlntic',3:'Pacific',4:'Regular', \
            5:'AtlHemi',6:'PacHemi',7:'IndianO',8:'Meditrn',9:'JapanPc', \
            11:'GtLkes',12:'RtdArc'}

## Prompt selection choices and ask for one input
    print (" \n ", gorloc)
    instr = input(' *** Please enter your selected number here > ')
    m = int(instr)
    pltype=gorloc.get(m, 'Invalid_selection')
    if( pltype == 'Invalid_selection' ): 
        print ("Invalid selection, program terminated.")
        exit()

    print (" Draw SMC grid "+pltype)

    if( pltype == 'Global'):
## Whole global projection angle from N Pole to be 90.0
        pangle=90.0
        plon= 0.0 
        plat= 23.5 
        clrbxy=[ -9.6,-12.0, 19.0,  1.0]
        sztpxy=[ 16.0,  9.0,-10.2, -9.8]
        rngsxy=[-10.0, 10.0,-12.1, 10.0]

    if( pltype == 'EuroArc'):
## Euro-Arctic regional plot
        pangle=28.0 
        plon=  0.0
        plat= 69.0
        clrbxy=[  8.0, -4.5,   0.8,  7.0]
        sztpxy=[ 11.0, 15.0,   4.0, -6.0]
        rngsxy=[-11.0, 11.0, -15.0, 15.0]

    if( pltype == 'Meditrn'):
        pangle= 11.50 
        plon= 15.0
        plat= 38.0
        clrbxy=[  3.5,  5.0,   8.0,  0.8]
        sztpxy=[ 15.0,  7.5,  -9.0, -3.0]
        rngsxy=[-14.5, 15.0,  -7.5,  7.5]

    if( pltype == 'Atlntic'):
## Atlantic regional plot
        pangle=40.0 
        plon=-24.0
        plat= 38.0
        clrbxy=[ 10.0, -9.0,   0.8,  9.0]
        sztpxy=[ 12.5, 10.0,   6.0, -2.0]
        rngsxy=[-12.5, 12.5, -10.0, 10.0]

    if( pltype == 'AtlHemi'):
## Hemispheric Atlantic ocean plot
        pangle=90.0
        plon= 0.0 
        plat= 23.5 
        clrbxy=[ -9.6,-12.0, 19.0,  1.0]
        sztpxy=[ 8.2,  9.0,   5.4,  6.0]
        rngsxy=[-10.0, 10.0,-12.1, 10.1]

    if( pltype == 'GtLkes'):
## Great Lakes regional plot
        pangle= 4.50 
        plon= 276.0
        plat=  45.3
        clrbxy=[  2.0,  6.0,   9.0,  0.8]
        sztpxy=[ 15.0, 10.0, -11.0, -3.0]
        rngsxy=[-15.0, 15.0, -10.0, 10.0]

    if( pltype == 'RtdArc'):
## Great Lakes regional plot
        pangle= 28.00 
        plon= 315.0
        plat=  80.1
        clrbxy=[ 10.0, 1.0,  0.8,  9.0]
        sztpxy=[ 10.0, 10.0, 5.0, 10.0]
        rngsxy=[ -9.0, 12.0,-10.3,10.6]

    if( pltype == 'Pacific'):
## West Pacific regional plot
        pangle=33.0 
        plon= 138.0
        plat=  18.0
        clrbxy=[-13.6,  7.5,   7.5,  0.8]
        sztpxy=[ 15.0, 10.0, -10.0,  6.4]
        rngsxy=[-15.0, 15.0, -10.0, 10.0]

    if( pltype == 'JapanPc'):
## Indian Ocean regional plot
        pangle= 36.0
        plon=146.0
        plat= 28.0
        clrbxy=[-11.6,  0.0,   0.8,  9.0]
        sztpxy=[ 12.0, 10.0,  -6.0,  9.0]
        rngsxy=[-12.0, 12.0, -10.0, 10.0]

    if( pltype == 'PacHemi'):
## Pacific hemispher plot
        pangle=90.0
        plon= 12.0 
        plat= 23.5 
        clrbxy=[ -9.6,-12.0, 19.0,  1.0]
        sztpxy=[ 12.0, 13.0,  7.0,  9.5]
        rngsxy=[-10.1, 10.1,-12.1, 10.1]

    if( pltype == 'IndianO'):
## Indian Ocean regional plot
        pangle= 54.0
        plon=-92.0
        plat= 20.0
        clrbxy=[-11.6, -2.0,   0.8,  9.0]
        sztpxy=[ 12.0, 10.0,   2.8,  9.5]
        rngsxy=[-12.0, 12.0, -10.0, 10.0]

    if( pltype == 'Regular'):
## Global rectangular regular lat-lon view.
        pangle=90.0 
        plon=-180.0
        plat=  90.0
        clrbxy=[366.0,-86.0, 10.0, 170.0]
        sztpxy=[ 16.0,  8.0, 60.0, 30.0]
        rngsxy=[ 0.0, 390.0,-90.0, 90.0]

    print( " Start loop over cells at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Projection pole lon-lat and angle
    rdpols=[radius, pangle, plon, plat]
    papror='portrait'

## Create cell vertices
    if( pltype == 'Regular' ):
        from smcelvrglr import smcelvrglr
        nvrts, ncels, nmark = smcelvrglr( cel, zdlnlt, rngsxy, 
               excids=excids, NArB=nabgpl )
        config=np.array([zdlnlt, sztpxy, rngsxy, clrbxy, nabgpl])

    else: 
        from smcelvrts import smcelvrts
        nvrts, ncels, svrts, scels, nsmrk = smcelvrts( cel, zdlnlt, 
               rdpols, rngsxy, excids=excids, NArB=NArB )
        if( len(nabgpl) > 0 ):
            config=np.array([rdpols, sztpxy, rngsxy, clrbxy, nabgpl])
        else: 
            config=np.array([rdpols, sztpxy, rngsxy, clrbxy])

## Store selected north and south verts and cell numbers for swh plots.
## Use the np.savez to save 3/5 variables in one file.  JGLi22Feb2019 
    pzfile=DatGMC+Gname+'Vrts'+pltype[0:4]+'.npz'
    if( pltype == 'Global' ):
        np.savez( pzfile, nvrt=nvrts, ncel=ncels, cnfg=config, 
                          svrt=svrts, scel=scels)

    elif( pltype == 'IndianO' or pltype == 'PacHemi' ):
        np.savez( pzfile, nvrt=svrts, ncel=scels, cnfg=config) 
    else:
        np.savez( pzfile, nvrt=nvrts, ncel=ncels, cnfg=config) 

## These variables could be loaded back by
#   vrtcls = np.load(DatGMC+Gname+'Vrts'+pltype[0:4]+'.npz')
#   nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']; config=vrtcls['cnfg']; 
#   svrts = vrtcls['svrt'] ; scels = vrtcls['scel']

## Draw your selected grid plot.
    epsfile=Wrkdir+Gname+pltype[0:4]+'grd.eps' 
    buspct=MyCodes+'SPBuoys.dat'
    bufile=MyCodes+'ECBuoys.dat'

    if( pltype == 'Global'):
        fig=plt.figure(figsize=sztpxy[0:2])
        ax1=fig.add_subplot(1,2,1)

        smcgrids(ax1, cel, nvrts,ncels,colrs, config, Arctic=Arctic, 
                 buoys=buspct)

        ax2=fig.add_subplot(1,2,2)
        smcgrids(ax2, cel, svrts,scels,colrs, config, Arctic=False, 
                 buoys=buspct, hemis=-1.0)

        xydxdy=[sztpxy[2],sztpxy[3], 0.0, 0.6]
        addtexts(ax2, xydxdy, txtary)
        plt.subplots_adjust(left=0.005, bottom=0.0, right=0.995, 
                             top=1.0, wspace=0.01, hspace=0.0)

    elif( pltype == 'PacHemi' or pltype == 'IndianO'):
        fig, ax = plt.subplots(figsize=sztpxy[0:2])
        smcgrids(ax, cel, svrts,scels,colrs,config, hemis=-1.0)
        xydxdy=[sztpxy[2],sztpxy[3], 0.0, -0.5]
        addtexts(ax, xydxdy, txtary)
        plt.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)

    elif( pltype == 'Regular'):
        fig, ax = plt.subplots(figsize=sztpxy[0:2])
        from smcgrglr import smcgrglr

        smcgrglr(ax, cel, nvrts, ncels, colrs, config, 
                 fntsz=fntsz, nmark=nmark)

        tpx=(rngsxy[1] - rngsxy[0])*0.5
        tpy=rngsxy[2]+1.0
        ax.text(tpx, tpy, Gname+' Grid  NC ='+str(nc),  
            horizontalalignment='center', fontsize=fntsb, color='k')
        plt.subplots_adjust(left=0.03, bottom=0.04, \
                           right=0.99, top=0.98)

    else:
        fig, ax = plt.subplots(figsize=sztpxy[0:2])
        smcgrids(ax, cel, nvrts,ncels,colrs,config, Arctic=Arctic, 
                 buoys=bufile) 

        xydxdy=[sztpxy[2],sztpxy[3], 0.0, -0.6]
        addtexts(ax, xydxdy, txtary)

        plt.subplots_adjust(left=0.0,bottom=0.0,right=1.0,top=1.0)

## Save the selected plot.
    print(" ...... Saving file ", epsfile)
    plt.savefig(epsfile, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=papror)
    plt.close()

    print( " Program finished at %s " % datetime.now().strftime('%F %H:%M:%S') )

## End of main function. 

if __name__ == '__main__':
    main()

## End of SMCGloblGrid.py program ##

