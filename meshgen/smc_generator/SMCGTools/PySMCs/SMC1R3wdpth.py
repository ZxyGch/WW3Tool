"""
## Program to draw water depth plot for SMC1MR3 grid W2 tests.
## 
## First created:    JGLi30Jun2011
## Converted into Python.    JGLi20Dec2018
## Last modified:    JGLi20Jun2025
##
"""

def main():

## Import relevant modules and functions
    import os
    import numpy as np
    import matplotlib.pyplot as plt

    from matplotlib.collections import PolyCollection
    from datetime import datetime, timedelta

    from readtext import readtext
    from readcell import readcell
    from rgbcolor import rgbcolor
    from steromap import steromap
    from whtliner import whtliner 
    from whtdfsqr import whtdfsqr 
    from smcfield import smcfield 
    from addtexts import addtexts 

## Find the $DATADIR directory on the system.
    datadir = os.popen('echo $DATADIR').read()[0:-1]
    homedir = os.popen('echo $HOME').read()[0:-1]

## Path of the cell projection files.
    DatSWE=datadir+'/SMCGTools/DatSWE/'
    OutSWE=datadir+'/SMCGTools/OutSWE/'
    Wrkdir=datadir+'/SMCGTools/tmpfls/'

## Model and grid names.
    Model='SMC1R3'
    Gname='SMC$\mathregular{1^o}$MR3'

## Read global and Arctic part cells. 
    Cel_file = DatSWE+Model+'Cels.dat'
    Arc_file = DatSWE+Model+'BArc.dat'

    headrs, cel = readcell( [Cel_file, Arc_file] ) 
    ng = int( headrs[0].split()[0] )
    NArB = headrs[1].split()
    na = int( NArB[0] )
    nb = int( NArB[1] )
    nc = ng + na
    print (' Merged total cel number = %d' % nc )

## Height scale used for plot.
    heights=[1000,1500,2000,2500,3000,3500]

## Height difference scale used for WHtDiff plot.
    whtdiff=[-60, -40, -20, 0, 20, 40, 60]

## Font sizes
    fntsz=10.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz

## Use own color map and defined depth colors 
    colrfile = './rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Possible selection of your plot types. 
    gorloc={0:'Global',1:'Single',2:'Sglcky',3:'WHtDiff'}

## Prompt selection choices and ask for one input
    print (" \n ", gorloc)
    instr = input("\n *** Please enter your selected number here > ")
    m = int(instr)
    pltype=gorloc.get(m, 'Invalid_selection')
    if( pltype == 'Invalid_selection' ): 
        print ("Invalid selection, program terminated.")
        exit()

    print (" Draw SWH plots "+pltype)

## Choose global or local verts from different files.
    vrfile = DatSWE+Model+'Vrts'+pltype[0:4]+'.npz'
    vrtcls = np.load( vrfile, allow_pickle=True )

    if( pltype == 'Global' ):
        nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']
        svrts = vrtcls['svrt'] ; scels = vrtcls['scel']
        config = vrtcls['cnfg']
        print (' n/svrts/cels config read ' )

    else:
        nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel'] 
        config = vrtcls['cnfg']
        print (' nvrts, ncels and config read ' )

    papror='portrait'

## Two bottom side text messages positions.
    sztpxy=config[1]
    tpx=sztpxy[2]; tpy=sztpxy[3]+0.5
    xydxdylft=[ tpx, tpy, 0.0, 0.5]
    xydxdyrgt=[-tpx, tpy, 0.0, 0.5]

## Use ijk to count how many times to draw.
    ijk=0

## Specify number of steps per hour, DT=90
    nhr=40

## Floor bottom height needs to be removed as
## output is Hw + Btm
    Btm= -3000.0 

## Read in cell concentration data files from a list file
    hdr, cnfiles = readtext(OutSWE+'cnfilesall.txt')
    cfiles = cnfiles.astype(str).reshape(len(cnfiles))

## loop over available files 
    for nn in range(0,len(cnfiles),2):
        dfile=OutSWE+cfiles[nn] 

        hdlist, swh2d = readtext(dfile)
        mt = int(hdlist[0])
        mc = int(hdlist[1])
        swhs = swh2d.flatten()[0:mc] - Btm

## Skip Arctic polar cell if nc = nga
        if( mc != nc ):
            print(' Unmatching mc/nc = %d %d' % (mc, nc)) 
            exit()
        else:
            print(' Plotting cell number mc = %d' % mc )

## Convert time step for output file
        ntsp='NTS = %5d' % (mt)
        thrs='T = %5.2d hr' % (float(mt)/nhr) 
        if( float(mt)/nhr % 24 == 0 ): 
            thrs='T = %4.2d day' % (float(mt)/nhr/24)

## Convert water height into linear color indexes.
        nwhts, whtmnx, whtscl = whtliner( swhs, heights )

        txtary=[ ['WHmn='+whtmnx[0], 'b', fntsa],
                 ['WHmx='+whtmnx[1], 'r', fntsa],
                 [thrs,      'k', fntsb] ] 

        epsfl = Wrkdir+'Hw'+pltype[0:4]+cfiles[nn][2:10]+'.eps'

## Call function to draw the swh plot.
        if( pltype == 'Global' ):

## Draw WH field on northern heimisphere panel.
            fig = plt.figure( figsize=(sztpxy[0:2]) )
            ax1=fig.add_subplot(1,2,1)
            smcfield(ax1, nwhts, nvrts, ncels, colrs, config,
                     vscle=whtscl, vunit='WHt m')

## Draw field on southern hemisphere subplot panel.
            ax2=fig.add_subplot(1,2,2)
            smcfield(ax2, nwhts, svrts, scels, colrs, config,
                     vscle=whtscl, vunit=' ')

## Put statistic information inside subplot ax2
            ax2.text(sztpxy[2], -sztpxy[3]-0.9, Gname+' WHt m',
                horizontalalignment='center', fontsize=fntsb, color='r')
            xydxdy=[sztpxy[2], sztpxy[3], 0.0, 0.6]
            addtexts(ax2, xydxdy, txtary)
            plt.subplots_adjust(left=0.01, bottom=0.01, right=0.99, 
                                 top=0.99, wspace=0.01, hspace=0.01)

        elif( pltype == 'Single' or pltype == 'Sglcky' ):
            fig, ax = plt.subplots(figsize=sztpxy[0:2])

## Draw the water height field on given axis panel.
            smcfield(ax, nwhts, nvrts, ncels, colrs, config, 
                     vscle=whtscl, fntsz=fntsz, vunit='WHt m')

## Add texts on two sides for each panel.
            addtexts(ax, xydxdylft, txtary, hrzlgn='left')
            txtrgt=[ [gname,   'r', fntsa], 
                     ['WHt m', 'b', fntsa] ]
            addtexts(ax, xydxdyrgt, txtrgt, hrzlgn='right')
            plt.subplots_adjust(left=0, bottom=0, right=1, top=1)

        elif( pltype == 'WHtDiff' ):
            if( nn == 0 ):
                swhs0=swhs
            else:
                hwdif=swhs - swhs0

## Convert water height into linear color indexes.
                nwhts, whdmnx, whdscl = whtdfsqr(whdf, whtdifs, 
                       nclrm=255, nczro=123) 

                txtary=[ ['WHDfmn='+whdmnx[0], 'b', fntsz],
                         ['WHDfmx='+whdmnx[1], 'r', fntsz],
                         [thrs,                'k', fntsa] ] 

                epsfl = Wrkdir + 'Hdf' + cfiles[nn][2:10] + '.eps'
                fig, ax = plt.subplots(figsize=sztpxy[0:2])

## Draw the water height difference on given axis panel.
                smcfield(ax, nwhts, nvrts, ncels, colrs, config,  
                    vscle=whdscl[0:3], fntsz=fntsz, vunit='WHtDif m')

                addtexts(ax, xydxdylft, txtary, hrzlgn='left')

                txtrgt=[ [gname,    'r', fntsa], 
                       ['WHtDif m', 'b', fntsa] ]
                addtexts(ax, xydxdyrgt, txtrgt, hrzlgn='right')
                plt.subplots_adjust(left=0, bottom=0, right=1, top=1)

## Draw maximum and minimum cell location marks if within ncels list.
                maxidx=minidx=0
                if( len(whdmnx) > 3 ): 
                    minidx=int(whdmnx[2])
                    maxidx=int(whdmnx[3])
                    kfnd=0
                    for k in range( len(ncels) ):
                        if( ncels[k] == maxidx ): 
                            mxpoly=nvrts[k][0]
                            ax.text(mxpoly[0], mxpoly[1], 'M', color='b', 
                                horizontalalignment='left', fontsize=fntsz)
                            kfnd += 1
                        if( ncels[k] == minidx ): 
                            mnpoly=nvrts[k][0]
                            ax.text(mnpoly[0], mnpoly[1], 'n', color='r', 
                                horizontalalignment='left', fontsize=fntsz)
                            kfnd += 1
                        if( kfnd >=2 ): break

## Save plot and close the fig object.
        print (" Save the plot "+epsfl )
        plt.savefig(epsfl, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=papror)
        plt.close(fig)

## Increase ijk for next plot
        ijk += 1
        print (" Finish plot No.", ijk," at ", datetime.now())

## End of date loop

## End of main() function.
    
if __name__ == '__main__':
    main()

## End of program SMC1R3wdpth.py.

