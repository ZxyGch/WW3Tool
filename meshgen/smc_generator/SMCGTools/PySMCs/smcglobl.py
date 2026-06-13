"""
##  The smcglobl function plots a global view of a given smc grid.
##  cel is the full cell array in shape(nc, 5).
##                                JGLi04Mar2019
##  Last updated:  JGLi09Jul2021
"""

def smcglobl(cel,nvrts,ncels,svrts,scels,colrs,config,Arctic=True,fsize=12.0, 
             mdlname='SMC', buoys='', psfile='output.ps', nmark=0,smark=0):

    """ Draw SMC grid in global view or as 2 hemisheres.
    """

##  Import relevant modules and functions
    import numpy as np
    import matplotlib.pyplot as plt

    from matplotlib.collections import PolyCollection

    from readtext import readtext   
    from steromap import steromap
    from colrboxy import colrboxy
    from scale_depth import scale_depth

##  Degree to radian conversion parameter.
    d2rad=np.pi/180.0

##  Total cell number from cell array.
    nc = cel.shape[0]

##  Global plot configuration parameters.
    rdpols=config[0]
    sztpxy=config[1]
    rngsxy=config[2]
    clrbxy=config[3]
##  Extra parameters for Arctic part.
    ncgrd = nc 
    if( Arctic and len(config) > 4 ): 
        ncabgm=config[4]
        ng=int(ncabgm[0])
        na=int(ncabgm[1])
        nb=int(ncabgm[2])
        jm=int(ncabgm[3])
        j3=cel[ng-1, 3]*3
        ncgrd = ng + na 

##  Maximum mapping radius.
    radius=rdpols[0]
    pangle=rdpols[1]
    plon  =rdpols[2]
    plat  =rdpols[3]

##  Outline circle at equator
    ciran=np.arange(1081)*d2rad/3.0
    xcirc=radius*np.cos(ciran)
    ycirc=radius*np.sin(ciran)

##  Define depth to color index conversion parameters and marks.
##  Use only first 131 colors in colrs(0:255). 
    depth, factr, cstar, marks, ncstr, nclrm = scale_depth(nclrm=131)

##  Alternative font sizes.
    asize=1.25*fsize 
    bsize=1.50*fsize

##  Cell color is decided by its depth value, dry cells use default 0 color.
    ndeps = np.zeros( (nc), dtype=int )
    for j in range(nc):
        if( cel[j,4] > 0 ):
            ndeps[j] = ncstr + np.rint( (cstar-np.log10(cel[j,4]+11))*factr ).astype(int)
#   ndeps = ncstr + np.rint( (cstar-np.log10(cel[:,4]))*factr ).astype(int)

##  Set up first subplot and axis for northern hemisphere
    print (" Drawing north hemisphere cells ... ")
    fig=plt.figure(figsize=sztpxy[0:2])
    ax1=fig.add_subplot(1,2,1)
    ax1.set_aspect('equal')
    ax1.set_autoscale_on(False)
    ax1.set_axis_off()
    plt.subplots_adjust(left=0.01,bottom=0.01,right=0.99,top=0.99)
    plt.subplots_adjust(wspace=0.01, hspace=0.01)

    xprop={'xlim':rngsxy[0:2], 'xlabel':'Nothing'}
    yprop={'ylim':rngsxy[2:4], 'ylabel':'Nothing'}
    ax1.set(**xprop)
    ax1.set(**yprop)

    ax1.plot(xcirc, ycirc, 'b-', linewidth=0.5)

## Select cells for one subplot and create verts and pcolr. 
    pcface = []
    pcedge = []
#   for i in ncels:
    kend = len(ncels)
    for k in range(kend):
        i = ncels[k]
##  Mark the arctical map-east reference region by first ring of its boundary cells at jmxglb-3
##  Here level 4 is assumed so the 4 overlapping rows are separated by 3*8=24 increments.
        if( Arctic and cel[i,1] == jm-j3 ):
            pcface.append(colrs(246))
            pcedge.append(colrs(246))
        elif( Arctic and cel[i,1] == jm ):
            pcface.append(colrs(168))
            pcedge.append(colrs(168))
##  Fill last nmark cells to be red.  JGLi03Sep2020
        elif( k >= kend - nmark ):
            pcface.append(colrs(240))
            pcedge.append(colrs(250))
        else:
            pcface.append(colrs(255))
            pcedge.append(colrs(ndeps[i]))
                
##  Draw this hemisphere cells
    smcpoly = PolyCollection(nvrts)
    smcpoly.set_facecolor(pcface)
    smcpoly.set_edgecolor(pcedge)
    smcpoly.set_linewidth( 0.2 )
    ax1.add_collection(smcpoly)


##  Draw colorbar for ax1.
    xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks, nclrm=nclrm)
    ax1.add_collection(clrply)
    for i in range(len(depth)):
        m = marks[i]
        plt.text(xkeys[m], ykeys[0]+1.15*(ykeys[1]-ykeys[0]), str(depth[i]),
            horizontalalignment='center', fontsize=fsize, color='b' )
#           rotation=-90,verticalalignment='center', fontsize=11, color='b' )

    plt.text(xkeys[marks[0]], ykeys[0]+2.0*(ykeys[1]-ykeys[0]), 'Depth m',
            horizontalalignment='left', fontsize=asize, color='k' )
#        rotation=-90,verticalalignment='center', fontsize=15, color='k' )

#;  Overlay buoy sits on grid map if buoy file is provided.
    if( len(buoys) > 3 ):
        hdr, buoyll = readtext(buoys)
        nmbu=int(hdr[0])
        buoyids=buoyll[:,0].astype(str)
        buoylat=buoyll[:,1].astype(float)
        buoylon=buoyll[:,2].astype(float)

#; Convert slat slon to elat elon with given new pole
        elat,elon,sxc,syc = steromap(buoylat,buoylon,plat,plon,Pangl=pangle)

#; Mark buoy position on map
        print (' Selected buoys on north hemisphere ...')
        for i in range(nmbu):
            if( (elat[i] >= 0.0) and (rngsxy[0] < sxc[i] < rngsxy[1])
                                 and (rngsxy[2] < syc[i] < rngsxy[3]) ):
                print (' {:6} {:8.3f} {:8.3f}'.format( buoyids[i], buoylat[i], buoylon[i] ) )
#               txtsz= 5+ int( np.sqrt( abs(np.sin(elat[i]*d2rad)) )*8.0 )
                txtsz= (1.0 + np.sqrt( abs(np.sin(elat[i]*d2rad)) ))*fsize*0.5 
                plt.text(sxc[i], syc[i], 'r',  fontsize=txtsz,
                     horizontalalignment='center', color='r' )
                plt.text(sxc[i], syc[i], '.',  fontsize=txtsz*2,
                     horizontalalignment='center', color='r' )


##  Southern hemisphere
    print (" Drawing south hemisphere cells ... ")
    ax2=fig.add_subplot(1,2,2)
    ax2.set_aspect('equal')
    ax2.axis('off') 
    plt.subplots_adjust(left=0.01,bottom=0.01,right=0.99,top=0.99)
    plt.subplots_adjust(wspace=0.01, hspace=0.01)
    ax2.set(**xprop)
    ax2.set(**yprop)

    ax2.plot(xcirc, ycirc, 'b-', linewidth=0.5)

## Select cells for one subplot and create verts and pcolr. 
    pcface = []
    pcedge = []
    if( Arctic ): jn=-jm-int(j3/3)

#   for i in scels:
    kend = len(scels)
    for k in range(kend):
        i = scels[k]
##  Mark the Antarctic map-east reference region, if any, within jn and jn+j3
##  where jn = -jm - j3/3  is symmetrical to the Arctic map-east region jm row. 
        if( Arctic and cel[i,1] == jn+j3 ):
            pcface.append(colrs(246))
            pcedge.append(colrs(246))
        elif( Arctic and cel[i,1] == jn ):
            pcface.append(colrs(168))
            pcedge.append(colrs(168))
##  Fill last nmark cells to be red.  JGLi03Sep2020
        elif( k >= kend - smark ):
            pcface.append(colrs(250))
            pcedge.append(colrs(250))
        else:
            pcface.append(colrs(255))
            pcedge.append(colrs(ndeps[i]))

## Generate polygon collections for southern hemisphere
    smcpoly = PolyCollection(svrts)
    smcpoly.set_facecolor(pcface)
    smcpoly.set_edgecolor(pcedge)
    smcpoly.set_linewidth( 0.2 )

    ax2.add_collection(smcpoly)
  
##  Put cell information inside plot
    tpx=sztpxy[2] 
    tpy=sztpxy[3]
    dpy= 0.6 

    plt.text(tpx, tpy+dpy*0.5, mdlname+' Grid',  
             horizontalalignment='center', fontsize=asize, color='k' )
    plt.text(tpx, tpy+dpy*2.0, 'NC='+str(ncgrd), 
             horizontalalignment='center', fontsize=fsize, color='r' )

    if( nmark + smark > 0 ):
        plt.text(tpx, tpy+dpy*3.0, 'NM='+str(nmark+smark), 
             horizontalalignment='center', fontsize=fsize, color='r' )
        tpy = tpy + dpy

    if( Arctic ):
        plt.text(tpx, tpy+dpy*3.0, 'NA='+str(na), 
             horizontalalignment='center', fontsize=fsize, color='r' )
        plt.text(tpx, tpy+dpy*4.0, 'NB='+str(nb), 
             horizontalalignment='center', fontsize=fsize, color='r' )

##  Draw colorbar for ax2.
    xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks, nclrm=nclrm)
    ax2.add_collection(clrply)
    for i in range(len(depth)):
        m = marks[i]
        plt.text(xkeys[m], ykeys[0]+1.18*(ykeys[1]-ykeys[0]), str(depth[i]),
            horizontalalignment='center', fontsize=fsize, color='b' )
#           verticalalignment='center', fontsize=11, color='b' )
#           rotation=-90,verticalalignment='center', fontsize=11, color='b' )

    plt.text(xkeys[marks[-1]], ykeys[0]+2.0*(ykeys[1]-ykeys[0]), 'Depth m',
            horizontalalignment='right', fontsize=asize, color='k' )
#        rotation=-90,verticalalignment='center', fontsize=15, color='k' )

#;  Overlay buoy sits on grid map if buoy file is provided.
    if( len(buoys) > 3 ):

#; Mark buoy position on map
        print (' Selected buoys on south hemisphere ...')
        for i in range(nmbu):
            if( (elat[i] < 0.0) and (rngsxy[0] < sxc[i] < rngsxy[1])
                                and (rngsxy[2] < syc[i] < rngsxy[3]) ):
                print (' {:6} {:8.3f} {:8.3f}'.format( buoyids[i], buoylat[i], buoylon[i] ) )
#               txtsz=int( abs(np.sin(elat[i]*d2rad)*12.0) )
                txtsz= (1.0 + np.sqrt( abs(np.sin(elat[i]*d2rad)) ))*fsize*0.5 
                plt.text( sxc[i], syc[i], 'r',  fontsize=txtsz,
                     horizontalalignment='center', color='r' )
                plt.text( sxc[i], syc[i], '.',  fontsize=txtsz*2,
                     horizontalalignment='center', color='r' )

##  Refresh subplots and save them.
    plt.subplots_adjust(wspace=0.02, hspace=0.01)

    plt.savefig(psfile, dpi=None,facecolor='w',edgecolor='w', \
                orientation='landscape',papertype='a3')

## End of smcglobl plot function. ##

