"""
## Program to draw the wave spectral propagation test on SMC61250 grid.
##
## First created:    JGLi30Jun2011
## Converted into Python.    JGLi20Dec2018
## Last modified:    JGLi08Apr2025
##
"""

def main( ):

## Import relevant modules and functions
    import os
    import numpy as np
    import matplotlib.pyplot as plt

    from datetime import datetime, timedelta

    from readtext import readtext
    from rgbcolor import rgbcolor
    from smcswhcv import smcswhcv 
    from smcfield import smcfield 
    from addtexts import addtexts 

## Find the $DATADIR directory on the system.
    datadir = os.popen('echo $DATADIR').read()[0:-1]

## Path of the cell projection files
    SMCGTools=datadir+'/SMCGTools/'
    PySMCs=SMCGTools+'PySMCs/'
    DatGMC=SMCGTools+'DatGMC/'
    OutDat=SMCGTools+'OutDat/'
    WrkDir=SMCGTools+'tmpfls/'

## Grid name to be used for all plots.
    gname='SMC61250'

## Use own color map and defined depth colors 
    colrfile = PySMCs+'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Choose global or local verts from different files.
    vrfile = DatGMC+'S650VrtsGlob.npz'
    vrtcls = np.load( vrfile )

    nvrts = vrtcls['nvrt'] ; ncels = vrtcls['ncel']
    svrts = vrtcls['svrt'] ; scels = vrtcls['scel']
    config = vrtcls['cnfg']
    print (' n/svrts/cels config read ' )

    papror='portrait'

## Global plot configuration parameters.
    sztpxy=config[1]
    tpx = sztpxy[2]; tpy = sztpxy[3]
    
## Alternative font sizes.
    fntsz=10.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz

## Define spectral direction
    ndir=36
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
    yt=-1.0

## Specify number of steps per hour (DTG = 900 s)
    nhr=4

## Read in cell concentration data files from a list file
    hdr, cnfiles = readtext(OutDat+'cfile3.txt')
    cfiles = cnfiles.astype(str).reshape(len(cnfiles))

## Setup one figure for 3 panels.
    fig = plt.figure(figsize=(sztpxy[0]*0.75, sztpxy[1]*2.25)) 

## loop over 3 panels. 
    for nn in range(3):

## Read propagation result file.
        dfile=OutDat+cfiles[nn] 

        hdlist, swh2d = readtext(dfile)
        mt = int(hdlist[0])
        mc = int(hdlist[1])
        swhs = swh2d.flatten()[0:mc]

        print (' Plotting cell number mc = %d' % mc )

## Convert time step for output file
        ntsp='NTS = %5d' % (mt)
        thrs=f'T = {float(mt)/nhr:.2f} hr' 

## Convert swh field into color indexes.
        nswh, swhmnx, swhscl = smcswhcv( swhs )

## Draw SWH field on northern heimisphere panel.
        ax1=fig.add_subplot(3,2,nn*2+1)
        smcfield(ax1, nswh, nvrts, ncels, colrs, config,
                 vscle=swhscl, vunit='SWH m')

## Add spectral array plots for the northern region
        for i in range(ndir):
            ax1.plot([x0,xn[i]], [y0,yn[i]], 'r-', linewidth=1)
            ax1.plot([xp,xp-x1+xs[i]], [yp,yp-y1+ys[i]], 'r-', linewidth=1)
            ax1.plot([xt,xt-x1+xs[i]], [yt,yt-y1+ys[i]], 'r-', linewidth=1)

## Draw field on southern hemisphere subplot panel.
        ax2=fig.add_subplot(3,2,nn*2+2)
        smcfield(ax2, nswh, svrts, scels, colrs, config,
                 vscle=swhscl, vunit=' ')

## Add a spectral array plots for the southern region
        for i in range(ndir):
            ax2.plot([x1, xs[i]], [y1, ys[i]], 'r-', linewidth=1)

## Put statistic information inside subplot ax2
        ax2.text(sztpxy[2], -sztpxy[3]-0.9, gname+' SWH m', 
            horizontalalignment='center', fontsize=fntsb, color='r')

        txtary=[ ['SWHmn='+swhmnx[0], 'b', fntsa],
                 ['SWHmx='+swhmnx[1], 'r', fntsa],
                 [thrs,      'k', fntsb] ] 
        xydxdy=[sztpxy[2], sztpxy[3]+0.5, 0.0, 0.6]
        addtexts(ax2, xydxdy, txtary)

        print (" Finish plot No.", nn," at ", datetime.now())

## Because total height is 27 inches and width 16 inches the wide 
## gap of 0.005(*16) is close to the height gap 0.003(*27).
        plt.subplots_adjust(left=0.005, bottom=0.003, right=0.995, 
               top=0.997, wspace=0.005, hspace=0.003)

## End of date loop
    epsfl = WrkDir + gname + 'Pro3.eps'
    print(" ... saving file as "+epsfl)
    plt.savefig(epsfl, dpi=None,facecolor='w',edgecolor='w', 
                orientation='portrait')
    plt.close()

## End of main() function. 

if __name__ == '__main__':
    main()

## End of SMC61250Pro3S.py program.

