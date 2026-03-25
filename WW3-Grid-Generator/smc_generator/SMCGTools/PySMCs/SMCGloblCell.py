"""
## Program to generate Global SMC grid from a netCDF Bathymetry file. 
## Bathy resolution should match size-1 cell length.
## 
## First created:        JGLi06May2021
## Last modified:        JGLi02Jun2025
##
"""

def main():

## Import relevant modules and functions
    import sys
    import numpy   as np
    import netCDF4 as nc 

    from smcellgen import smcellgen

## Check input information file name if provided.
    print(sys.argv)
    if( len(sys.argv) > 1 ):
        if( len(sys.argv[1]) > 3 ):
            gridfile = sys.argv[1]
    else:
        gridfile = 'GridInfo61250.txt'

## Read global grid information file. 
    with open( gridfile, 'r' ) as flhdl:
## First line contains grid name and number of resolution levels.
        nxlne = flhdl.readline().split()
        Gname = nxlne[0]
        Level = int(nxlne[1])
        print(" Input grid name and number of levl= ", Gname, Level)
## Second line contains zlon zlat dlon dlat of size-1 cell parameters.
        nxlne = flhdl.readline().split()
        zdlnlt = np.array(nxlne, dtype=float)
        print(" Input grid zlon zlat dlon dlat = \n", zdlnlt) 
## Third line is the working directory and cell array subdirectory.
        nxlne = flhdl.readline().split()
        Wrkdir=nxlne[0]
        DatGMC=nxlne[1]
        print(" Working directory and DatGMC = \n", nxlne) 
## Final line starts with the number of polar cells.
        nxlne = flhdl.readline().split()
        npl = int(nxlne[0])
        print(" Number of polar cells = ", npl) 
        if( npl > 0 ): Arctic= True

## Read global bathymetric data file.
    bathyf='../Bathys/Bathy088_059deg.nc' 
    Global= True

## Open and read bathymetry data.
    datas = nc.Dataset(bathyf)

    print(datas)            ## Print information about the dataset.

    print(datas.__dict__)

    print(datas.__dict__['description'])

    for var in datas.dimensions.values(): print(var)

    nlat = datas.dimensions['lat'].size
    nlon = datas.dimensions['lon'].size
    dlat = 180.0 / float(nlat)
    dlon = 360.0 / float(nlon)

    print(" nlat, nlon, dlat, dlon =", nlat, nlon, dlat, dlon )

    xlon = datas.variables['lon'][:]
    ylat = datas.variables['lat'][:]
    Bathy= datas.variables['elevation'][:,:]
    depthmax = np.amin(Bathy)
    hightmax = np.amax(Bathy)
    print(' Bathy range=', depthmax, hightmax)
    print(' Bathy shape=', Bathy.shape )
    print(' x_lon range=', xlon[0], xlon[nlon-1])
    print(' y_lat range=', ylat[0], ylat[nlat-1])

    datas.close()

## Pack bathy parameters into one list.
    ndzlonlat=[ nlon, nlat, dlon, dlat, xlon[0], ylat[0] ]
## Check top row bathy values
    print('Bathy[',nlat-1,[f'{i:d}' for i in range(0,nlon,1024)],']')
    print(Bathy[nlat-1,0:nlon:1024])

## Check bathy data resolution matching with size-1 cell lenth.
    matchdxy=True
    if( abs( zdlnlt[2] - dlon ) > 1.0E-6 ):
        print(" Bathy dlon not matching dxlon:", dlon, zdlnlt[2])
        matchdxy=False
    if( abs( zdlnlt[3] - dlat ) > 1.0E-6 ):
        print(" Bathy dlat not matching dylat:", dlat, zdlnlt[3])
        matchdxy=False
    if( not matchdxy ): exit

## Default minimum depth set to be 0.
    depmin= 0.0

## Model resolution level and i, j index orgin zlon and zlat.
    mlvlxy0 = [ Level, zdlnlt[0], zdlnlt[1] ]

    smcellgen(Bathy, ndzlonlat, mlvlxy0, FileNm=Wrkdir+Gname, 
              Global=Global, Arctic=Arctic, depmin=depmin)
    
## End of main program.

if __name__ == '__main__':
    main()

## End of program SMCGloblCell.py.

