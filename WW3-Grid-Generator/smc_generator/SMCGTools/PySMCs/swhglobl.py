"""
##  Draw global swh plot with given polycollections and cell
##  array. Output as A3 ps file.        JGLi28Feb2019
##
"""

def swhglobl(swhs,nvrts,ncels,svrts,scels,colrs,config,fsize=12.0,
             mdlname='SMC',datx='2018010106',psfile='output.ps'):

##  Import relevant modules and functions

    import numpy as np
    import matplotlib.pyplot as plt

    from matplotlib.collections import PolyCollection

    from colrboxy import colrboxy
    from scale_swh import scale_swh

##  Degree to radian conversion parameter.
    d2rad=np.pi/180.0

##  Global plot configuration parameters.
    rdpols=config[0]
    sztpxy=config[1]
    rngsxy=config[2]
    clrbxy=config[3]
    ncabgm=config[4]

##  Maximum mapping radius.
    radius=rdpols[0]
    pangle=rdpols[1]
    plon  =rdpols[2]
    plat  =rdpols[3]

##  Outline circle at equator
    ciran=np.arange(1081)*d2rad/3.0
    xcirc=radius*np.cos(ciran)
    ycirc=radius*np.sin(ciran)

##  Set up wave height scale and marks with colrs.N.
##  colrs.N returns colrs' total number of colors 256.
    waveht, factor, residu, marks, ncstr, nclrm = scale_swh(nclrm=colrs.N)

    resmn1=residu - 1.0
    nswh0=ncstr+ int( factor*np.log(-resmn1 + residu) )
#   print (' factor, residu, resmn1, nswh0 = {} {} {} {: d}' 
#    .format(factor, residu, resmn1, nswh0) ) 

##  Alternative font sizes.
    asize=1.25*fsize 
    bsize=1.50*fsize

##  Some constant variables for plots.
    xprop={'xlim':rngsxy[0:2], 'xlabel':''}
    yprop={'ylim':rngsxy[2:4], 'ylabel':''}
    
    if True:
##  Work out max and min values, excluding missing data (-999.0)
        cmax = swhs.max()
        cmin = swhs[ swhs > -999.0 ].min()
        print ( ' swh range %f, %f' % (cmin, cmax) )
        cmxs = 'SWHmx = %6.2f m' % cmax
        cmns = 'SWHmn = %10.3E' % cmin

##  Reset missing values (-999.0) to be -resmn1 
        swhs[ swhs < -resmn1] = -resmn1

##  Trim large values into plot range if any
        swhs[ swhs > 32.0 ] = 32.0 

##  Convert swhs with logarithm scale.
        icnf = np.rint( factor*np.log(swhs+residu) )
        nswh = np.array( icnf, dtype=int )

        print (" Drawing "+psfile)
##  Set up first subplot and axis for northern hemisphere
        fig=plt.figure(figsize=sztpxy[0:2])
        ax1=fig.add_subplot(1,2,1)
        ax1.set_aspect('equal')
        ax1.set_autoscale_on(False)
        ax1.set_axis_off()
        plt.subplots_adjust(left=0.01,bottom=0.01,right=0.99,top=0.99)
        plt.subplots_adjust(wspace=0.01, hspace=0.01)

        ax1.set(**xprop)
        ax1.set(**yprop)

        ax1.plot(xcirc, ycirc, 'b-', linewidth=0.5)

## Use loaded verts to setup PolyCollection.
        polynorth = PolyCollection(nvrts)

## Create color array for this plot
        pcface = []
        pcedge = []
        for i in ncels:
            if( nswh[i] == nswh0 ): 
                pcface.append(colrs(255)) 
                pcedge.append(colrs(0)) 
            else:
                pcface.append(colrs(nswh[i]))
                pcedge.append(colrs(nswh[i]))
               

#   smcpoly.set_color(pcolr)    ## This line defines both edge and face color.
        polynorth.set_facecolor(pcface)
        polynorth.set_edgecolor(pcedge)
        polynorth.set_linewidth( 0.2 )
        ax1.add_collection(polynorth)  

##  Draw colorbar for ax1.
        xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks)
        ax1.add_collection(clrply)
        for i in range(len(waveht)):
            m = marks[i]
            plt.text(xkeys[m], ykeys[0]+1.18*(ykeys[1]-ykeys[0]), str(waveht[i]),
            horizontalalignment='center', fontsize=fsize, color='b' )
#           rotation=-90,verticalalignment='center', fontsize=11, color='b' )

        plt.text(xkeys[marks[0]], ykeys[0]+2.0*(ykeys[1]-ykeys[0]), 'SWH m',
            horizontalalignment='left', fontsize=asize, color='k' )
#           rotation=-90,verticalalignment='center', fontsize=15, color='k' )


##  Southern hemisphere subplot.
        ax2=fig.add_subplot(1,2,2)
        ax2.set_aspect('equal')
        ax2.axis('off')
        plt.subplots_adjust(left=0.01,bottom=0.01,right=0.99,top=0.99)
        plt.subplots_adjust(wspace=0.01, hspace=0.01)
        ax2.set(**xprop)
        ax2.set(**yprop)

        ax2.plot(xcirc, ycirc, 'b-', linewidth=0.5)

## Use loaded verts to set up PolyCollection. 
        polysouth = PolyCollection(svrts)

## Create color array for this plot
        pcface = []
        pcedge = []
        for i in scels:
            if( nswh[i] == nswh0 ):
                pcface.append(colrs(255))
                pcedge.append(colrs(0))
            else:
                pcface.append(colrs(nswh[i]))
                pcedge.append(colrs(nswh[i]))
   
#   smcpoly.set_color(pcolr)    ## This line defines both edge and face color.
        polysouth.set_facecolor(pcface)
        polysouth.set_edgecolor(pcedge)
        polysouth.set_linewidth( 0.2 )
        ax2.add_collection(polysouth)


##  Put statistic information inside subplot ax2
        tpx=sztpxy[2] 
        tpy=sztpxy[3]
        dpy= 0.6 

        plt.text(tpx, 9.0, mdlname+' SWH',  
             horizontalalignment='center', fontsize=bsize, color='r' )
        plt.text(tpx, tpy+dpy*1.0, cmns,
             horizontalalignment='center', fontsize=asize, color='b' )
        plt.text(tpx, tpy+dpy*2.0, cmxs, 
             horizontalalignment='center', fontsize=asize, color='r' )
        plt.text(tpx, tpy+dpy*3.0, datx,
             horizontalalignment='center', fontsize=asize, color='k' )

##  Draw colorbar for ax2.
        xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks)
        ax2.add_collection(clrply)
        for i in range(len(waveht)):
            m = marks[i]
            plt.text(xkeys[m], ykeys[0]+1.18*(ykeys[1]-ykeys[0]), str(waveht[i]),
               horizontalalignment='center', fontsize=fsize, color='b' )
#              rotation=-90,verticalalignment='center', fontsize=11, color='b' )

        plt.text(xkeys[marks[-1]], ykeys[0]+2.0*(ykeys[1]-ykeys[0]), 'SWH m',
            horizontalalignment='right', fontsize=asize, color='k' )
#           rotation=-90,verticalalignment='center', fontsize=15, color='k' )

##  Refresh subplots and save them.
        plt.subplots_adjust(wspace=0.01, hspace=0.01)

        plt.savefig(psfile, dpi=None,facecolor='w',edgecolor='w', 
                    orientation='landscape',papertype='a3')


        plt.close()


##  End of swhglobal plot.

