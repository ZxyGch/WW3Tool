"""
## Adapted to generate AMM153 grid from netCDF Bathymetry files. 
##
## First created:    JGLi01Nov2022
## Last modified:    JGLi06Jul2023
##
"""

def main():

##  Import relevant modules and functions
    import numpy   as np
    import netCDF4 as nc 

    from smcellgen import smcellgen
    from smcellbdy import smcellbdy

## Path of the bathymetry file and working directory.
    MyCode='/home/users/jianguo.li/Python/MyCodes/'
    Wrkdir='/data/users/jianguo.li/Bathy/AMM15Wave/'
    bathyf='/data/users/jianguo.li/Bathy/AMM15Wave/Amm15Bathy.nc' 
    Global= False
    Arctic= False
    GridNm='AMM153km'

##  Open and read bathymetry data.
    datas = nc.Dataset(bathyf)

    print(datas)            ## Print information about the dataset.

    nlat = datas.dimensions['lat'].size
    nlon = datas.dimensions['lon'].size
    zlat = -7.2942; zlon = -10.8895   
    dlat =  0.0135; dlon = 0.0135
    ylat = zlat + np.arange(nlat)*dlat
    xlon = zlon + np.arange(nlon)*dlon

    print(" nlat, nlon, dlat, dlon =", nlat, nlon, dlat, dlon )
    print(" Grid range x0, y0, xn, yn =",xlon[0],ylat[0],xlon[-1],ylat[-1] )

##  Pack bathy parameters into one list.
    ndzlonlat=[ nlon, nlat, dlon, dlat, zlon, zlat ]

    Bathy= - datas.variables['Bathymetry'][:,:]
    depthmax = np.amin(Bathy)
    hightmax = np.amax(Bathy)
    print(' Bathy range=', depthmax, hightmax)
    print(' Bathy shape=', Bathy.shape )

    datas.close()

##  Check top row bathy values
    print('Bathy[',nlat-1,[f'{i:d}' for i in range(0,nlon,1024)],']')
    print(Bathy[nlat-1,0:nlon:1024])

##  Patch last row values to be exactly the ones in the next inner row.
#   Bathy[nlat-1,:] = Bathy[nlat-2,:]

##  Check last column bathy values
#   print('Bathy[',[f'{i:d}' for i in range(0,nlat,225)],',', nlon-1,']')
#   print(Bathy[0:nlat:225,nlon-1])
#   print('Bathy[',[f'{i:d}' for i in range(0,nlat,225)],',', 0,']')
#   print(Bathy[0:nlat:225,0])

##  Decide resolution levels and SMC grid i=j=0 lon-lat.
    NLvl = 2

## Rotated pole lat-lon for AMM15 grid.
    Polon = 177.5
    Polat =  37.5

##  For AMM15 domain, the refrence point is set to be at the SW corner of
##  the AMM15 rotated grid, half-grid length offset for the true cell corner. 
    x0lon = xlon[0] - 0.5*dlon 
    y0lat = ylat[0] - 0.5*dlat 
    print( GridNm+" grid x0lon, y0lat =", x0lon, y0lat )

##  Lift minimum depth to 5 m above sea level to include dry points.
    wlevel=  0.0
    depmin=  5.0
    dshalw= -150.0
    mlvlxy0 = [ NLvl, x0lon, y0lat, xlon[0], ylat[0], xlon[-4], ylat[-3] ]

    smcellgen(Bathy, ndzlonlat, mlvlxy0, FileNm=Wrkdir+GridNm, wlevel=wlevel,  
              Global=Global, Arctic=Arctic, depmin=depmin, dshalw=dshalw) 
    
##  Redefine grid area to include boundary cells.
    mlvlxy0 = [ NLvl, x0lon, y0lat, xlon[0], ylat[0], xlon[-1], ylat[-2] ]

    smcellbdy(Bathy, ndzlonlat, mlvlxy0, FileNm=Wrkdir+GridNm, wlevel=wlevel,  
              Global=Global, Arctic=Arctic, depmin=depmin, dshalw=dshalw)

## Save some parameters for later use.
    Flon = zlon + dlon     ## First size-2 cell centre lon
    Flat = zlat + dlat     ## First size-2 cell centre lat
    NX = int( (nlon)/2 )   ## nlon and nlat are halved.
    NY = int( (nlat)/2 )
    NLvl = 2
    IShft = 0
    JEqut = 0
    
    with open(Wrkdir+GridNm+'Info.txt', 'w') as grdl:
        grdl.write('  Grid parameters for '+GridNm+'\n\n' )
        grdl.write(f' Number of levels = {NLvl:5d} IShft = {IShft:d} JEqut = {JEqut:d} \n' )
        grdl.write(f' nx and ny in size-1 unit: {nlon:6d}, {nlat:6d} \n' )
        grdl.write(f' dlon dlat in size-1 unit: {dlon:.6f}, {dlat:.6f} \n' )
        grdl.write(f' Lon range of bathy input: {zlon:.4f}, {xlon[-1]:.4f} \n' )
        grdl.write(f' Lat range of bathy input: {zlat:.4f}, {ylat[-1]:.4f} \n' )
        grdl.write(f' x0lon y0lat of ij origin: {x0lon:.4f}, {y0lat:.4f} \n' )
        grdl.write(f' NX, NY for  ww3_grid.inp: {NX:d}, {NY:d} \n' )
        grdl.write(f' X0, Y0 for  WW3_Grid.inp: {Flon:.4f}, {Flat:.4f} \n' )
        grdl.write(f' SX, SY for  WW3_Grid.inp: {dlon*2.0:.6f}, {dlat*2.0:.6f} \n' )
        grdl.write(f' Polon Polat WW3_Grid.inp: {polon:.2f}, {polat:.2f} \n' )

##  End of main program.

if __name__ == '__main__':
    main()

## End of program AMM153kmCells.py.

