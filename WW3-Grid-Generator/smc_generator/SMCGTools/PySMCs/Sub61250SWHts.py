"""
## Program to draw Sub61250 grid SWH field.
##
## First created:    JGLi30Jun2011
## Converted into Python.    JGLi20Dec2018
## Adapted for 3 sub-grids SWH plots.    JGLi25Jan2021
## Last modified:    JGLi02May2025
##
"""

def main():

## Import relevant modules and functions
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt

    from datetime import datetime, timedelta

    from readtext import readtext
    from rgbcolor import rgbcolor
    from smcswhcv import smcswhcv 
    from smcfield import smcfield 
    from addtexts import addtexts 

## Path of the cell projection files
    DatSub='../DatSub/'
    WrkDir='../tmpfls/' 

## Use own color map and defined depth colors 
    colrfile = 'rgbspectrum.dat'
    colrs = rgbcolor( colrfile )

## Read start and end datetime from fdate
    datefl = open( 'strendat', 'r')
    strend = datefl.read().split()
    datefl.close()

## Convert into datetime variables
    start = datetime.strptime(strend[0], '%y%m%d%H')
    endat = datetime.strptime(strend[1], '%y%m%d%H')
    timdx = pd.date_range(start=start, end=endat, freq=strend[2])

## Possible selection of your plot types. 
    gorloc={0:'SubG',1:'Soth',2:'Pacf',3:'Atln'}

## Prompt selection choices and ask for one input
    print (" \n ", gorloc)
    instr = input("\n *** Please enter your selected number here > ")
    m = int(instr)
    pltype=gorloc.get(m, 'Invalid_selection')
    if( pltype == 'Invalid_selection' ): 
        print ("Invalid selection, program terminated.")
        exit()

##  Model name to be used for all plots.
    ModlName=pltype+'61250'

    print (" Draw SWH plots for "+ModlName)

##  Choose global or local verts from different files.
    vrfile = DatSub+ModlName+'Vrts.npz'
    vrtcls = np.load( vrfile )

    if( pltype == 'SubG' ): 
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
    mdlswh=pltype[0:4]+'61250'

## Alternative font sizes.
    fntsz=12.0
    fntsa=1.20*fntsz 
    fntsb=1.50*fntsz
    
##  Loop over datetime of swh files
    swhSoth = '../../Sub650Soth/ww3.'
    swhPacf = '../../Sub650Pacf/ww3.'
    swhAtln = '../../Sub650Atln/ww3.'

    print (" SWH file loop started at ", datetime.now() )

##  Use ijk to count how many times to draw.
    ijk=0

#   for i in range( ndays*4 ):
    for dt in timdx:
##  Read Soth61250 swh.
        swhfl = swhSoth + dt.strftime('%y%m%d%H') + '.hs'

        hdlist, swh2d = readtext(swhfl)
        ms = int(hdlist[4])
        swh1 = swh2d.flatten()[0:ms]

##  Read Pacf61250 swh.
        swhfl = swhPacf + dt.strftime('%y%m%d%H') + '.hs'

        hdlist, swh2d = readtext(swhfl)
        mc = int(hdlist[4])
        swh2 = swh2d.flatten()[0:mc]

##  Read or append Atln51250 swh.
        swhfl = swhAtln + dt.strftime('%y%m%d%H') + '.hs'

        hdlist, swh2d = readtext(swhfl)
        mt = int(hdlist[4])
        swh3 = swh2d.flatten()[0:mt]

##  Convert time step for output file
        datms = dt.strftime('%Y%m%d%H')

##  Call function to draw the swh plot.
        epsfl = WrkDir+'swh'+pltype[0:4]+dt.strftime('%y%m%d%H')+'.eps'

        if( pltype == 'SubG' ): 
##  Merge all sub-grid SWHs together for global plot.
            swhs = np.hstack( (swh1, swh2, swh3) )

## Convert swh field into color indexes.
            nswh, swhmnx, swhscl = smcswhcv( swhs )
            txtary=[ [mdlswh,    'k', fntsb],
                     ['SWHmn='+swhmnx[0], 'b', fntsa],
                     ['SWHmx='+swhmnx[1]+' m', 'r', fntsa],
                     [datms,     'k', fntsb] ]

## Open figure plt for 2 panels.
            fig=plt.figure(figsize=sztpxy[0:2])
            ax1=fig.add_subplot(1,2,1)

## Draw SWH field on northern heimisphere panel.
            smcfield(ax1, nswh, nvrts, ncels, colrs, config,
                     vscle=swhscl, vunit='SWH m')

## Draw field on southern hemisphere subplot panel.
            ax2=fig.add_subplot(1,2,2)
            smcfield(ax2, nswh, svrts, scels, colrs, config,
                     vscle=swhscl, vunit=' ')

## Put statistic information inside subplot ax2
            ax2.text(sztpxy[2], 9.0, mdlswh, color='r', 
                horizontalalignment='center', fontsize=fntsb)
            xydxdy=[sztpxy[2], sztpxy[3]+1.0, 0.0, 0.6]
            addtexts(ax2, xydxdy, txtary[1:])

            plt.subplots_adjust(left=0.01, bottom=0.0, right=0.99, 
                                 top=1.0, wspace=0.01, hspace=0.0)

        else:
## Draw individual sub-grid SWH field.
            if( m == 1 ): swhs = swh1
            if( m == 2 ): swhs = swh2
            if( m == 3 ): swhs = swh3

## Convert swh field into color indexes.
            nswh, swhmnx, swhscl = smcswhcv( swhs )
            txtary=[ [mdlswh,    'k', fntsb],
                     ['SWHmn='+swhmnx[0], 'b', fntsa],
                     ['SWHmx='+swhmnx[1]+' m', 'r', fntsa],
                     [datms,     'k', fntsb] ]

## Ople figure plt and draw SWH field.
            fig, ax = plt.subplots(figsize=sztpxy[0:2])
            smcfield(ax, nswh, nvrts, ncels, colrs, config,
                     vscle=swhscl, vunit='SWH m')

## Put statistic information inside plot ax.
            xydxdy=[sztpxy[2], sztpxy[3]-0.5, 0.0, -0.6]
            addtexts(ax, xydxdy, txtary)
            plt.subplots_adjust(left=0,bottom=0,right=1,top=1)

## Save grid plot as eps file.
        print (" ... saving the smc grid plot as ", epsfile )
        plt.savefig(epsfile, dpi=None,facecolor='w',edgecolor='w', \
                    orientation=paprorn)
        plt.close()

##  Increase ijk for next plot
        ijk += 1
        print (" Finish plot No.", ijk," at ", datetime.now())

##  End of date loop

## End of main() function. 

if __name__ == '__main__':
    main()

## End of Sub61250SWHts.py program.

