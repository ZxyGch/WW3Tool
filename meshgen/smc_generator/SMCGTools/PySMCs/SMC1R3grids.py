"""
##
## Program to draw the SMC1dMR3 grid. 
##
## First created:    JGLi26Nov2008
## Updated to Python 3.    JGLi02Apr2019
## Last modified:    JGLi20Jun2025
##
"""

def main():

## Import relevant modules and functions
    import os
    import numpy as np
    import matplotlib.pyplot as plt

    from matplotlib.collections import PolyCollection

    from datetime import datetime
    from readcell import readcell   
    from steromap import steromap
    from rgbcolor import rgbcolor
    from smcgrids import smcgrids 
    from addtexts import addtexts 
    from smcelvrts import smcelvrts

    print( " Program started at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Find the $DATADIR directory on the system.
    datadir = os.popen('echo $DATADIR').read()[0:-1]
    homedir = os.popen('echo $HOME').read()[0:-1]

## Paths of the cell array and projection files.
    Wrkdir=datadir+'/SMCGTools/tmpfls/'
    DatSWE=datadir+'/SMCGTools/DatSWE/'

## Model and grid names.
    Model='SMC1R3'
    Gname='SMC$\mathregular{1^o}$MR3'

## Read cell array.
    Cel_file = DatSWE+Model+'Cels.dat'
    Arc_file = DatSWE+Model+'BArc.dat'

    headrs, cel = readcell( [Cel_file, Arc_file] ) 
    ng = int( headrs[0].split()[0] )
    NArB = headrs[1].split()
    na = int( NArB[0] )
    nb = int( NArB[1] )
    nbg= int( NArB[2] )
    npl= int( NArB[3] )
    nc = ng + na
    print (' Merged total cel number = %d' % nc )
    print (' Arctic header NArB =', NArB)

## Initial txtary list as [txt, colr, fontsize].
    fntsz = 10.0
    fntsa = 1.25*fntsz
    fntsb = 1.50*fntsz

    txtary = [ [Gname+' Grid',   'k', fntsb],
               ['NC='+str(nc),   'r', fntsa], 
               ['NPl='+str(npl), 'r', fntsa] ] 

## Size-1 cell parameters.
    dxlon=0.3515625
    dylat=0.250 
    zrlon=0.0
    zrlat=0.0

## Grid related parameters
    zdlnlt = [zrlon, zrlat, dxlon, dylat]

## Extra array in config for Arctic part
    Arctic = True 
    nabgpl = [na, nb, nbg, npl]

## Increase cell depth for dark color grid plot.
    cel[:,4]=4000

## Mark all cells on the Equator and 2 polar cells
    cel1=list(cel[:,1])
    ind0=[]
    for j in range(ng):
        if(cel1[j] == 0): ind0.append(j)
    excids= ind0 + [nc-2,nc-1]
## But remove the first cell at zero meridian.
    excids.remove(ind0[0])

## Use own color map and defined depth colors 
    colrfile = './rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Maximum mapping radius.
    radius=10.0

## Possible selection of your plot types. 
    gorloc={0:'Global', 1:'Single', 2:'Sglcky', \
            3:'Regulr', 4:'RegNth'}

## Prompt selection choices and ask for one input
    print (" \n ", gorloc)
    instr = input(' *** Please enter your selected number here > ')
    m = int(instr)
    pltype=gorloc.get(m, 'Invalid_selection')
    if( pltype == 'Invalid_selection' ): 
        print ("Invalid selection, program terminated.")
        exit()

    print (" Draw SMC grid "+Model+pltype)

    if( pltype == 'Global'):
## Whole global projection angle from N Pole to be 90.0
        Pnrds=10.0
        pangle=90.0
        plon=  0.0 
        plat= 40.0 
        clrbxy=[ -9.6,-12.0, 19.0,  1.0]
        sztpxy=[ 16.0, 9.0, -10.2, -9.8]
        rngsxy=[-10.0, 10.0,-12.1, 10.0]
        papror='portrait'

    if( pltype == 'Single'):
## Euro-Arctic regional plot
        Pnrds=4.0
        pangle=90.0
        plon=  0.0 
        plat= 40.0 
        clrbxy=[ 10.1, -9.6, 1.0, 19.0]
        sztpxy=[  9.0,  8.0, -9.6, -9.9]
        rngsxy=[-10.1, 12.1,-10.1, 10.1]
        papror='portrait'

    if( pltype == 'Sglcky'):
## Same as 'Single' hemisphere but color key at bottom.
        Pnrds=4.0
        pangle=90.0
        plon=  0.0 
        plat= 40.0 
        clrbxy=[ -9.6,-12.0, 19.0, 1.0]
        sztpxy=[  8.0,  9.0, -9.6, -9.9]
        rngsxy=[-10.1, 10.1,-12.1, 10.1]
        papror='portrait'

    if( pltype == 'Regulr'):
## Global rectangular regular lat-lon view.
        pangle=90.0 
        plon=-180.0
        plat=  90.0
        clrbxy=[366.0,-86.0, 10.0, 170.0]
        sztpxy=[ 16.0,  8.0, 60.0, 30.0]
        rngsxy=[ 0.0, 390.0,-90.0, 90.0]
        papror='portrait'

    if( pltype == 'RegNth'):
## Rectangular regular lat-lon view for North hemisphere.
        pangle=90.0
        plon=-180.0 
        plat=  90.0
        clrbxy=[366.0,  3.0, 10.0, 85.0]
        sztpxy=[ 16.0,  6.0, 60.0, 30.0]
        rngsxy=[ 0.0, 390.0,  0.0, 90.0]
        papror='portrait'

    print( " Start loop over cells at %s " % datetime.now().strftime('%F %H:%M:%S') )

## Projection pole lon-lat and angle
    rdpols=[radius, pangle, plon, plat]

## Create cell vertices
    if( pltype == 'Global' or pltype == 'Single' or pltype == 'Sglcky'):
## Create cell vertices
        from smcelvrts import smcelvrts
        nvrts, ncels, svrts, scels, nsmrk = smcelvrts( cel, zdlnlt, rdpols, 
               rngsxy, NArB=nabgpl, excids=excids, Pnrds=Pnrds )

        config=np.array([rdpols, sztpxy, rngsxy, clrbxy, nabgpl])

    if( pltype == 'Regulr' or pltype == 'RegNth'):
        from smcelvrglr import smcelvrglr
        nvrts, ncels, nmark = smcelvrglr( cel, zdlnlt, rngsxy, 
                  excids=excids, NArB=nabgpl )

## For regular plot there is no need to store the projection rdpols but zdlnlt.
        config=np.array([zdlnlt, sztpxy, rngsxy, clrbxy, nabgpl])

## Store selected north and south verts and cell numbers for swh plots.
## Use the np.savez to save 3/5 variables in one file.  JGLi22Feb2019 
    pzfile=DatSWE+Model+'Vrts'+pltype[0:4]+'.npz'
    if( pltype == 'Global' ):
        np.savez( pzfile, nvrt=nvrts, ncel=ncels, cnfg=config, 
                          svrt=svrts, scel=scels)
    else:
        np.savez( pzfile, nvrt=nvrts, ncel=ncels, cnfg=config) 

## These variables could be loaded back by
#   vrtcls = np.load(DatSWE+Model+'Vrts'+pltype[0:4]+'.npz')
#   nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']; config=vrtcls['cnfg']; 
#   svrts = vrtcls['svrt'] ; scels = vrtcls['scel']
##

## Draw your selected grid plot.
    epsfile=Wrkdir+Model+pltype[0:4]+'.eps' 

    if( pltype == 'Global'):
        fig=plt.figure(figsize=sztpxy[0:2])
        ax1=fig.add_subplot(1,2,1)

        smcgrids(ax1, cel, nvrts,ncels,colrs, config, Arctic=Arctic, 
                 fntsz=fntsz, nmark=nsmrk[0]) 

        ax2=fig.add_subplot(1,2,2)
        smcgrids(ax2, cel, svrts,scels,colrs, config, Arctic=Arctic, 
                 fntsz=fntsz, nmark=nsmrk[1]) 

        xydxdy=[sztpxy[2], sztpxy[3], 0.0, 0.6]
        addtexts(ax2, xydxdy, txtary)

        plt.subplots_adjust(left=0.01, bottom=0.01, right=0.99, 
                             top=0.99, wspace=0.01, hspace=0.01)
        plt.savefig(epsfile, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=papror)
        plt.close()

    elif( pltype == 'Single' or pltype == 'Sglcky'):
        fig, ax = plt.subplots(figsize=sztpxy[0:2])
        plt.subplots_adjust(left=0.0, bottom=0.0, right=1.0, top=1.0)

        smcgrids(ax, cel, nvrts,ncels,colrs,config, Arctic=Arctic, 
                 fntsz=fntsz, nmark=nsmrk[0], Pnrds=Pnrds)

        xydxdy=[-9.6, -9.6, 0.0, 0.6]
        addtexts(ax, xydxdy, txtary, hrzlgn='left')
        xydxdy=[ 9.6, -9.6, 0.0, 0.6]
        proary = [ ['Projection Pole',   'k', fntsb],
                   [f'PLon={plon:8.2f}', 'r', fntsa], 
                   [f'PLat={plat:7.2f}', 'r', fntsa] ] 
        addtexts(ax, xydxdy, proary, hrzlgn='right')

        print (" Save the grid plot ... " )
        plt.savefig(epsfile, dpi=None, facecolor='w', \
            edgecolor='w', orientation=papror)
        plt.close()

    else:
        fig, ax = plt.subplots(figsize=sztpxy[0:2])
        plt.subplots_adjust(left=0.03, bottom=0.04, \
                           right=0.99, top=0.98)
        from smcgrglr import smcgrglr

        smcgrglr(ax, cel, nvrts, ncels, colrs, config, 
                 fntsz=fntsz, nmark=nmark)

        tpx=(rngsxy[1] - rngsxy[0])*0.5
        tpy=rngsxy[2]+1.0
        ax.text(tpx, tpy, Gname+' NC ='+str(nc),  
            horizontalalignment='center', fontsize=fntsb, color='k')

        print (" Save the grid plot ... " )
        plt.savefig(epsfile, dpi=None, facecolor='w', \
            edgecolor='w', orientation=papror)

    print(" Program finished at %s " % \
           datetime.now().strftime('%F %H:%M:%S') )

## End of main:() function.

if __name__ == '__main__':
    main()

## End of SMC1R3grids program. 

