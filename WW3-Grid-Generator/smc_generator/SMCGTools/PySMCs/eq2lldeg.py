"""  eq2lldeg procedure converts rotated or equatorial latitude longitude 
#    back to standard latitude longitude with a given new pole position.
#    First created on  4 Dec 2018  by Jian-Guo Li
#    Last modified on  8 Feb 2019  by Jian-Guo Li
#
# name:     eq2lldeg
#
# purpose:  Converts standard lat/lon to rotated lat/lon as NumPy arrays.
#
# usage:    SLat, SLon = ll2eqdeg( ELat, ELon, PoLat, PoLon )
#
# input:    ELat,  ELon  --- Rotated or equitorial lat lon as NumPy array in deg
#           Polat, Polon --- New North Pole standard lat/lon in deg, scalors.
# output:   SLat,  SLon  --- Corresponding lat lon in standard grid in deg, NumPy array
#
"""

import numpy as np

def eq2lldeg( ELat, ELon, Polat, Polon ):

##  Check Input ELat, Elon elements, should be equal
    nlat=len(ELat)
    nlon=len(ELon)

    if nlat != nlon: 
        print( ' ELat and ELon elements should have equal elements!' )
        print( ' ELat and ELon elements are', nlat, nlat )
        return 

##  No need to calculate if North Pole unchanged
    if (Polat == 90.0 and Polon == 0.0): 
        return (ELat, ELon)

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
    ALon = ELon 

##  Converting ALon range to be -180 to 180
    lonind= ALon >= 180.0 
    if( lonind.any() ): ALon[lonind]=ALon[lonind]-360.0
    lonind= ALon < -180.0 
    if( lonind.any() ): ALon[lonind]=ALon[lonind]+360.0

##  Conversion of SLat/SLon to ELat/ELon
    Apt_Ang =   cospolat*np.cos(ELat*D2Rad)*np.cos(ALon*D2Rad) \
              + sinpolat*np.sin(ELat*D2Rad)

    Apt_Ang[ Apt_Ang >  1.0 ]= 1.0 
    Apt_Ang[ Apt_Ang < -1.0 ]=-1.0 

    ELatRad = np.arcsin(Apt_Ang)
    cosELat = np.cos(ELatRad)
    cosELon = sinpolat*np.cos(ELat*D2Rad)*np.cos(ALon*D2Rad) \
             -cospolat*np.sin(ELat*D2Rad)

    SLat = ELatRad*R2Deg
    SLon = np.zeros(nlon)
    Tmpr = np.zeros(nlon)

##  Only set Elon where cosELat is non zero
    latind = cosELat > 0.0 
    if( latind.any() ): 
        Tmprat=cosELon[latind]/cosELat[latind]

        Tmprat[ Tmprat >  1.0 ] = 1.0
        Tmprat[ Tmprat < -1.0 ] =-1.0

        SLon[latind] = R2Deg*np.arccos(Tmprat)

##  Change ELon sign to negative if ALon is negative. 
    lonind= ALon < 0.0 
    if( lonind.any() ): SLon[lonind]= - SLon[lonind]

##  Add zero-lon and stream back range
    SLon = SLon + ZeroLon
    lonind= SLon >= 360.0
    if( lonind.any() ): SLon[lonind]=SLon[lonind]-360.0
    lonind= SLon < 0.0
    if( lonind.any() ): SLon[lonind]=SLon[lonind]+360.0

##  print( '... Finishing eq2lldeg ...') 

    return (SLat, SLon)


