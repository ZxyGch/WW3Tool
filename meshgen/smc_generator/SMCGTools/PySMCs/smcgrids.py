"""
##  The smcgrids function plots a SMC grid of cell array cel(nc, 5) 
##  with given projection verts and colors on a given axis.
##
##  First created:    JGLi04Mar2019
##  Last modified:    JGLi09Jun2025
##
"""

def smcgrids(ax, cel, verts, ncels, colrs, config, Arctic=False, 
            fntsz=10.0, nmark=0, ndry=11, hemis=1.0, 
            vunit='Depth m', buoys='', nmbuoy=0, Pnrds=3.0):

##  Import relevant modules and functions
    import numpy as np

    from matplotlib.collections import PolyCollection

    from readtext import readtext
    from steromap import steromap
    from colrboxy import colrboxy
    from scale_depth import scale_depth

##  Degree to radian conversion parameter.
    d2rad=np.pi/180.0

##  Total cell number by cell array
    nc = cel.shape[0]

##  Local plot configuration parameters
    rdpols=config[0]
    sztpxy=config[1]
    rngsxy=config[2]
    clrbxy=config[3]
##  Local or sub-grid cell number if defined.
    npl = 2
    if( Arctic and len(config) >4 ): 
        ncabgm=config[4]
        na=int(ncabgm[0])
        nb=int(ncabgm[1])
        nbg=int(ncabgm[2])
        npl=int(ncabgm[3])
        ng= nc - na
        jm=np.max(cel[0:ng, 1])
        j1=cel[ng-1, 3]
        j3=j1*3

##  Maximum mapping radius.
    radius=rdpols[0]
    pangle=rdpols[1]
    plon  =rdpols[2]
    plat  =rdpols[3]

##  Define depth to color index conversion parameters and marks.
##  Use only first 136 colors in colrs(0:255). 
    depth, factr, cstar, marks, ncstr, nclrm = \
           scale_depth(nclrm=136)

##  Cell color is decided by its depth value.
    ndeps = np.zeros( (nc), dtype=int )
    for j in range(nc):
        if( cel[j,4] > -ndry ): 
            ndeps[j] = ncstr + np.rint( (cstar- \
                np.log10(cel[j,4]+ndry))*factr ).astype(int)
##  Sea level index
    ndep0 = ncstr + np.rint( (cstar-np.log10(ndry))*factr ).astype(int)
#   print( " Sea level depth index is ", ndep0)

##  Use selected cells to draw the plot.
    ax.set_xlim(rngsxy[0:2])
    ax.set_ylim(rngsxy[2:4])
    ax.set_aspect('equal')
    ax.set_autoscale_on(False)
    ax.set_axis_off()

##  Add a outline circle if pangle >= 90.0
    if( pangle >= 90.0 ):
        ciran=np.arange(1081)*d2rad/3.0
        xcirc=radius*np.cos(ciran)
        ycirc=radius*np.sin(ciran)
        ax.plot(xcirc, ycirc, 'b-', linewidth=0.3)

##  Create color array for this plot
    pcface = []
    pcedge = []
    kend = len(ncels)
    for k in range(kend):
        i = ncels[k] 
## Mark the polar map-east reference region by first and last 
## rings of its boundary cells at jm-3 and jm.
        if( Arctic and (cel[i,1] == jm-j3  \
                     or cel[i,1] ==-jm+j3-j1) ):
            pcface.append(colrs(246))
            pcedge.append(colrs(246))
        elif( Arctic and (cel[i,1] == jm  \
                       or cel[i,1] ==-jm-j1) ):
            pcface.append(colrs(168))
            pcedge.append(colrs(168))
## Fill last nmark cells to be red.  JGLi03Sep2020
        elif( k >= kend - nmark ):
            pcface.append(colrs(250))
            pcedge.append(colrs(250))
        else:
            pcface.append(colrs(255))
            pcedge.append(colrs(ndeps[i]))

## Create PolyCollection from selected verts and define edge and face color.
    polynorth = PolyCollection(verts)
    polynorth.set_facecolor(pcface)
    polynorth.set_edgecolor(pcedge)
    polynorth.set_linewidth( 0.2 )

## Draw the selected cells as colored polygons.
    ax.add_collection(polynorth)

## Draw colorbar inside plot.
    xkeys, ykeys, clrply = colrboxy(clrbxy, colrs, marks, nclrm=nclrm)
    ax.add_collection(clrply)
    dkx=clrbxy[2]; dky=clrbxy[3]
    for i in range(len(depth)):
        m = marks[i]
        if( dkx < dky ):    
            ax.text(xkeys[0]+1.15*dkx, ykeys[m], str(depth[i]),
                rotation=-90,verticalalignment='center', fontsize=fntsz, color='b' )
        else:
            ax.text(xkeys[m], ykeys[0]+1.15*dky, str(depth[i]),
                horizontalalignment='center', fontsize=fntsz, color='b' )

    if( dkx < dky ):    
        ax.text(xkeys[0]+1.6*dkx, ykeys[marks[1]], vunit,
                 rotation=-90,verticalalignment='center', fontsize=fntsz, color='b' )
    else:
        ax.text(xkeys[marks[1]], ykeys[0]+1.6*dky, vunit, 
                 rotation=0,horizontalalignment='center', fontsize=fntsz, color='b' )

## Overlay buoy sits on grid map if buoy file is provided.
    if( len(buoys) > 3 ):
        hdr, buoyll = readtext(buoys)
        nmbu=int(hdr[0])
        buoyids=buoyll[:,0].astype(str)
        buoylat=buoyll[:,1].astype(float)
        buoylon=buoyll[:,2].astype(float)

## Convert slat slon to elat elon with given new pole
        elat, elon, sxc, syc = steromap(buoylat, buoylon, plat, plon,
            Pangl=pangle, Pnrds=Pnrds)

## Mark buoy position on map if it is on the right hemisphere.
        print (' Selected buoys in this plot:')
        for i in range(nmbu):
## Reverse sxc if it is for southern hemisphere.
            if( (hemis*elat[i] >= 0.0) and 
                (rngsxy[0] < sxc[i] < rngsxy[1]) and 
                (rngsxy[2] < syc[i] < rngsxy[3]) ):
                print (' {:6} {:8.3f} {:8.3f}'.format( 
                    buoyids[i], buoylat[i], buoylon[i] ))
                txtsz= (2.0+abs(np.sin(elat[i]*d2rad)))*0.4*fntsz  
                ax.text(sxc[i], syc[i], '.', fontsize=txtsz*2,
                    horizontalalignment='center', color='r')
## Optional buoy name, number or symbol r character.
                if( nmbuoy == 0 ):
                    ax.text(sxc[i], syc[i], 'r', fontsize=txtsz, 
                        horizontalalignment='center', color='r')
                elif( nmbuoy == 1 ):
                    ax.text(sxc[i], syc[i]+0.01*txtsz, str(i+1), fontsize=txtsz, 
                        horizontalalignment='center', color='r')
                else:
                    ax.text(sxc[i], syc[i]+0.01*txtsz, buoyids[i], fontsize=txtsz, 
                        horizontalalignment='center', color='r')

## End of smcgrids.py function. 

