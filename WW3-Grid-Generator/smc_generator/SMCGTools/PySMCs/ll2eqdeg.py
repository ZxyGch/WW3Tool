"""  ll2eqdeg procedure converts standard latitude longitude to rotated 
#    or equatorial latitude longitude with a given new pole position.
#    First created on  4 Dec 2018  by Jian-Guo Li
#    Last modified on 10 Dec 2018  by Jian-Guo Li
#
# name:     ll2eqdeg
#
# purpose:  Converts standard lat/lon to rotated lat/lon as NumPy arrays.
#
# usage:    ELat, ELon = ll2eqdeg( SLat, SLon, PoLat, PoLon )
#
# input:    SLat,  SLon  --- Standard lat lon as NumPy array in deg
#           Polat, Polon --- New North Pole standard lat/lon in deg, scalors.
# output:   ELat,  ELon  --- Corresponding lat lon in rotated grid in deg, NumPy array
#
"""

import numpy as np

def ll2eqdeg( SLat, SLon, Polat, Polon ):

##  Check Input SLat, Slon elements, should be equal
    nlat=len(SLat)
    nlon=len(SLon)

    if nlat != nlon: 
        print( ' SLat and SLon elements should have equal elements!' )
        print( ' SLat and SLon elements are', nlat, nlat )
        return 

##  No need to calculate if North Pole unchanged
    if (Polat == 90.0 and Polon == 0.0): 
        return (SLat, SLon)

##  Constants 
    D2Rad=np.pi/180.0
    R2Deg=180.0/np.pi

##  Make Pole longitude within range -180 to 180
    PoLon_orig=Polon
    if Polon > 180.0:  Polon=Polon - 360.0

##  Sine and cosine of PoLat
    if Polat >= 0.0: 
        sinpolat= np.sin(Polat*D2Rad)
        cospolat= np.cos(Polat*D2Rad)
    else: 
        sinpolat=-np.sin(Polat*D2Rad)
        cospolat=-np.cos(Polat*D2Rad)

##  Shifting SLat to opposite rotated pole side. 
    ZeroLon = Polon + 180.0
    ALon = SLon - ZeroLon

##  Converting ALon range to be -180 to 180
    lonind= ALon >= 180.0 
    if( lonind.any() ): ALon[lonind]=ALon[lonind]-360.0
    lonind= ALon < -180.0 
    if( lonind.any() ): ALon[lonind]=ALon[lonind]+360.0

##  Conversion of SLat/SLon to ELat/ELon
    Apt_Ang = - cospolat*np.cos(SLat*D2Rad)*np.cos(ALon*D2Rad) \
              + sinpolat*np.sin(SLat*D2Rad)

    Apt_Ang[ Apt_Ang >  1.0 ]= 1.0 
    Apt_Ang[ Apt_Ang < -1.0 ]=-1.0 

    ELatRad = np.arcsin(Apt_Ang)
    cosELat = np.cos(ELatRad)
    cosELon = sinpolat*np.cos(SLat*D2Rad)*np.cos(ALon*D2Rad) \
             +cospolat*np.sin(SLat*D2Rad)

    ELat = ELatRad*R2Deg
    ELon = np.zeros(nlon)
    Tmpr = np.zeros(nlon)

##  Only set Elon where cosELat is non zero
    latind = cosELat > 0.0 
    if( latind.any() ): 
        Tmprat=cosELon[latind]/cosELat[latind]

        Tmprat[ Tmprat >  1.0 ] = 1.0
        Tmprat[ Tmprat < -1.0 ] =-1.0

        ELon[latind] = R2Deg*np.arccos(Tmprat)

##  Change ELon sign to negative if ALon is negative. 
    lonind= ALon < 0.0 
    if( lonind.any() ): ELon[lonind]= - ELon[lonind]

##  print( '... Finishing ll2eqdeg ...') 

    return (ELat, ELon)


