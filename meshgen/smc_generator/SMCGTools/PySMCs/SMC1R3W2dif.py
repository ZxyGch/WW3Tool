"""
## Program to draw the W2 rotation zonal flow diagarm.
## Draw initial Hw & 5 day diff in 2 panels.  
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

    from datetime import datetime, timedelta

    from readtext import readtext
    from readcell import readcell
    from rgbcolor import rgbcolor
    from whtliner import whtliner 
    from whtdfsqr import whtdfsqr 
    from smcfield import smcfield 
    from addtexts import addtexts 

## Find the $DATADIR directory on the system.
    datadir = os.popen('echo $DATADIR').read()[0:-1]
    homedir = os.popen('echo $HOME').read()[0:-1]

## Model name
    Model='SMC1R3'
    gname='SMC$\mathregular{1^o}$MR3'

## Path of the cell projection files
    DatSWE=datadir+'/SMCGTools/DatSWE/'
    OutSWE=datadir+'/SMCGTools/OutSWE/'
    Wrkdir=datadir+'/SMCGTools/tmpfls/'

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
    whtdifs=[-25, -16, -9, -4, -1, 0, 1, 4, 9, 16, 25]

## Font sizes
    fntsz=10.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz

## Use own color map and defined depth colors 
    colrfile = './rgbspectrum.dat'
    colrs = rgbcolor( colrfile )
    nclrm = colrs.N

## Choose global or local verts from different files.
    vrfile = DatSWE+Model+'VrtsSing.npz'
    vrtcls = np.load( vrfile, allow_pickle=True )

    nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel'] 
    config = vrtcls['cnfg']
    papror='portrait'
    print (' nvrts, ncels and config read ' )

## Two bottom side text messages positions.
    sztpxy=config[1]
    tpx=sztpxy[2]; tpy=sztpxy[3]
    xydxdylft=[ tpx, tpy, 0.0, 0.6]
    xydxdyrgt=[-tpx, tpy, 0.0, 0.6]

## Specify number of steps per hour, DT=90
    nhr=40

## Floor bottom height needs to be removed as
## output is Hw + Btm
    Btm= -3000.0 

## Read in cell concentration data files from a list file
    hdr, cnfiles = readtext(OutSWE+'cnfiles05d.txt')
    cfiles = cnfiles.astype(str).reshape(len(cnfiles))

## Column and row in multi-panel plot
    colm=1; rows=2
    panels=['(a)','(b)','(c)','(d)','(e)','(f)']

## Select colm*rows for a single figure.
    psize = (sztpxy[0]*colm*0.9, sztpxy[1]*rows*0.9)
    fig=plt.figure(figsize=psize)

## loop over all panels.
    for nn in range(0,colm*rows):
        dfile=OutSWE+cfiles[nn] 
        ax=fig.add_subplot(rows,colm,nn+1)

        hdlist, swh2d = readtext(dfile)
        mt = int(hdlist[0])
        mc = int(hdlist[1])
        whts = swh2d.flatten()[0:mc] - Btm

## Convert time step for output file
        ntsp='NTS = %5d' % (mt)
        thrs='T = %5.2d hr' % (float(mt)/nhr) 
        if( float(mt)/nhr % 24 == 0 ): 
            thrs='T = %3d day' % (float(mt)/nhr/24)

        if( nn == 0 ):
## Draw initial water height field.
            wht0 = whts

## Convert water height into linear color indexes.
            nwhts, whtmnx, whtscl = whtliner( wht0, heights )

            txtary=[ [whtmnx[0], 'b', fntsz],
                     [whtmnx[1], 'r', fntsz],
                     [thrs,      'k', fntsa] ] 

## Draw the water height field on given axis panel.
            smcfield(ax, nwhts, nvrts, ncels, colrs, config,
                     vscle=whtscl, fntsz=11.0, vunit='WHt m')

## Add texts on two sides for each panel.
            ax.text(tpx, 9.0, panels[nn], fontsize=fntsb, 
                horizontalalignment='left', color='k')

            addtexts(ax, xydxdylft, txtary, hrzlgn='left')
            txtrgt=[ [gname,   'r', fntsa], 
                     ['WHt m', 'b', fntsz] ]
            addtexts(ax, xydxdyrgt, txtrgt, hrzlgn='right')

        else:
## Draw water height difference from initial one.
            whdf = whts - wht0

## Convert whdf into square root difference colour scales.
            nwhts, whdmnx, whdscl = whtdfsqr(whdf, whtdifs, 
                   nclrm=255, nczro=123) 

            txtary=[ ['WHDfmn='+whdmnx[0], 'b', fntsz],
                     ['WHDfmx='+whdmnx[1], 'r', fntsz],
                     [thrs,                'k', fntsa] ] 

## Draw the water height difference on given axis panel.
            smcfield(ax, nwhts, nvrts, ncels, colrs, config,
                vscle=whdscl[0:3], fntsz=11.0, vunit='WHtDif m')

## Add texts on two sides for each panel.
            ax.text(tpx, 9.0, panels[nn], fontsize=fntsb, 
                horizontalalignment='left', color='k')

            addtexts(ax, xydxdylft, txtary, hrzlgn='left')

            txtrgt=[ [gname,    'r', fntsa], 
                   ['WHtDif m', 'b', fntsz] ]
            addtexts(ax, xydxdyrgt, txtrgt, hrzlgn='right')

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

        print (" Finish plot No.", nn," at ", datetime.now())

## End of date loop

## Adjust panel gaps and save plot.
    plt.subplots_adjust(left=0.0, bottom=0.0, right=1.0, 
                         top=1.0, wspace=0.0, hspace=0.0)
    figfl = Wrkdir + 'SMC1R3W2df2.eps'
    print (" Save the plot "+figfl )
    plt.savefig(figfl, dpi=None, facecolor='w', edgecolor='w', \
                orientation=papror)

## End of main() function.

if __name__ == '__main__':
    main()

## End of program SMC1R3W2dif.py

