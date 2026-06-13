"""
#;;  steromap procedure converts standard latitude longitude to rotated 
#;;  or equatorial latitude longitude with a given N'-pole position and
#;;  map the rotated lat/lon with a stereographic projection.
#;;  First Created:   14 May 2014  by Jian-Guo Li
#;;  Converted into a Python function on 5 Dec 2018 by Jian-Guo Li
#;;  Last Modified:    8 Nov 2024  by Jian-Guo Li
#
# name:     steromap
#
# purpose:  Converts standard lat/lon to rotated lat/lon and stereographic map
#
# usage:    ELat, ELon, SXxc, SYyc = steromap( SLat, SLon, Polat, Polon, Pangl=Pangl, Onecl=True, Pnrds=4.0 )
#           Assuming default radius = 10.0, otherwise, add the radius=your_value key word.
#           Minimum projection distance is 2 radius and default is 3.0, unless user defined Pnrds is present.
#
# input:    SLat, SLon --- Standard lat lon as ndarray in deg
#           Polat, Polon --- New North Pole position in standard lat/lon in deg, scalors.
#           Pangl --- scalor angle in deg from rotated Pole so its projected radius is 10 unit.
#           Onecl --- if True, keep all points in one hemisphere as one cell. 
# output:   ELat, ELon --- Corresponding lat lon in rotated grid in deg, as ndarray.
#           SXxc, SYyc --- Corresponding projected x/y coordinates in range [-10, 10], as ndarray.
#
"""

import numpy as np
from ll2eqdeg import ll2eqdeg

def steromap( SLat, SLon, Polat, Polon, Pangl=90.0, radius=10.0, Onecl=False, Pnrds=3.0 ):

##  Check Input SLat, Slon elements, should be equal
    nlat=len(SLat)
    nlon=len(SLon)

    if nlat != nlon: 
        print( ' SLat and SLon elements should have equal elements!' )
        print( ' SLat and SLon elements are', nlat, nlat )
        return 

    if( Pangl <= 0.0 or Pangl > 90.0): 
        print( ' Pangl must be 0 < Pangl <= 90.0!' )
        print( ' Input Pangl is equal to', Pangl )
        return 

##  Number of radius from projection point.
    if Pnrds <= 2.0:
        print( ' Use minimum projection distance of 2 radius!' )
        Pnrds = 2.0
#   elif Pnrds > 4.0:
#       print( ' Use defined projection distance in radius:', Pnrds )
#   else:
#       print( ' Use default projection distance of 3 radius!' )

##  No need to calculate if North Pole unchanged
    if (Polat == 90.0 and Polon == 0.0): 
        ELat = SLat
        ELon = SLon
    else:
##  Convert slat slon to elat elon with given new pole
        ELat, ELon = ll2eqdeg(SLat, SLon, Polat, Polon)

##  Radian-degree conversion constants.
    d2rad=np.pi/180.0
    r2deg=180.0/np.pi

##  Adjusted projected radius so that projected edge radius 
##  to be equal to the original radius. 
    PRadus=radius*(Pnrds - 1.0 + np.cos(Pangl*d2rad))/np.sin(Pangl*d2rad)

##  Generate projecting coordiantes. ndarray operations.
    pradmp=PRadus*np.cos(ELat*d2rad)/(Pnrds - 1.0 + np.sin(np.absolute(ELat)*d2rad))
    SYyc = pradmp*np.cos(ELon*d2rad)
    SXxc =-pradmp*np.sin(ELon*d2rad)

##  Check if any point is on the southern hemisphere
    indx = ELat < 0.0 
    if( indx.any() ):     ## Any element of this boolean array is true
        if( Onecl ):
##  If it is for one single cell projection, keep all in one hemisphere
            SXxc = -SXxc 
        else:
##  Reverse southern hemisphere x-coordinate for individual points.
            SXxc=np.where(indx, -SXxc, SXxc)

    return ( ELat, ELon, SXxc, SYyc )

##  print('... Finishing steromap.py ...')


