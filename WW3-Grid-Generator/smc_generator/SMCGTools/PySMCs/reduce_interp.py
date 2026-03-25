#==================================================================================
# BSD License
#
# Copyright (c)2023, ww3-opentools developers, all rights reserved
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice, this
#  list of conditions and the following disclaimer in the documentation and/or
#  other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#  contributors may be used to endorse or promote products derived from this
#  software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
# OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
# OF THE POSSIBILITY OF SUCH DAMAGE.
#
#==================================================================================
# gebco_reduce_interp.py
#
# PURPOSE:
#  Functions library for generating a reduced version of the GEBCO bathymetry
#  product, either based on averaging over an integer number of GEBCO grid cells
#  or using scipy interpolate functions. The reduction makes subsequent work for 
#  gridgen quicker and easier, since the cell finding loops in that code then get 
#  to work with smaller source grid files and arrays.
#
#  Functions are also used to calculate the obstruction ratio of each averaged 
#  cell, or the land_area/total_area ratio.  This obstruction ratio is used in 
#  wave propagation scheme to count for the partial blocking by large cells. 
#
# REVISION HISTORY:
#
# A. Saulter; Met Office; May-2020
#  Code prepared for initial release on github
#
# Jian-Guo Li; Met Office; May-2023
#  Add obstruction ratio and simplify configure input with a main() function.
#  Lake corrections are moved into SMC grid generating program.
#
#==================================================================================

import netCDF4 as nc
import numpy as np
import scipy.interpolate as interp

from datetime import datetime 

def writedepthobstrNC(outfile, dx, dy, depthmin, latout, lonout, depout, obsout):
    """ Write out depth and obstruction as a new netCDF file """

    descriptions=' Grided bathymetry and obstruction ratio. \n'+ \
                 ' Mean depth values are at cell centre and \n'+ \
                 ' obstruction ratio is land_area/cell_area.  '

    print('[INFO] Writing depth and obstruction data to %s' %outfile)
    with nc.Dataset(outfile, 'w') as nbg:
        ndimx = nbg.createDimension('lon',size=np.size(lonout))
        ndimy = nbg.createDimension('lat',size=np.size(latout))

        ndep = nbg.createVariable('lat','f8',dimensions=('lat'))
        ndep.units = 'degrees_east'
        ndep[:] = latout[:]

        ndep = nbg.createVariable('lon','f8',dimensions=('lon'))
        ndep.units = 'degrees_north'
        ndep[:] = lonout[:]

        ndep = nbg.createVariable('elevation','f8',dimensions=('lat','lon'))
        ndep.units = 'm'
        ndep[:,:] = depout[:,:]

        ndep = nbg.createVariable('obstruction','f8',dimensions=('lat','lon'))
        ndep.units = '1.0'
        ndep[:,:] = obsout[:,:]

        # add global attributes to describe processing
        nbg.description = descriptions 
        nbg.longitude_increment = dx
        nbg.latitude_increment = dy
        nbg.minimum_depth = depthmin

def writeReducedNCxy(outfile, scalefac, depthmin, latout, lonout, depout, obsout):
    """ Write out the reduced dataset to a new netCDF file """

    print('[INFO] Writing reduced grid data to %s' %outfile)
    with nc.Dataset(outfile, 'w') as nbg:
        ndimx = nbg.createDimension('lon',size=np.size(lonout))
        ndimy = nbg.createDimension('lat',size=np.size(latout))

        ndep = nbg.createVariable('lat','f8',dimensions=('lat'))
        ndep.units = 'degrees_east'
        ndep[:] = latout[:]

        ndep = nbg.createVariable('lon','f8',dimensions=('lon'))
        ndep.units = 'degrees_north'
        ndep[:] = lonout[:]

        ndep = nbg.createVariable('elevation','f8',dimensions=('lat','lon'))
        ndep.units = 'm'
        ndep[:,:] = depout[:,:]

        ndep = nbg.createVariable('obstruction','f8',dimensions=('lat','lon'))
        ndep.units = '1.0'
        ndep[:,:] = obsout[:,:]

        # add global attributes to describe processing
        nbg.description = 'Reduced GEBCO bathymetry grid: mean depth values over cell'
        nbg.reduction_lon_factor = scalefac[0]
        nbg.reduction_lat_factor = scalefac[1]
        nbg.minimum_depth = depthmin


def rebin(arr, new_shape):
    """ Bin a large array to a smaller one by averaging """

    if np.size(new_shape) == 1:
        shape = (new_shape[0], arr.shape[0] // new_shape[0])
        arrout = arr.reshape(shape).mean(-1)
    elif np.size(new_shape) == 2:
        shape = (new_shape[0], arr.shape[0] // new_shape[0],
                 new_shape[1], arr.shape[1] // new_shape[1])
#       arrout = arr.reshape(shape).mean(-1).mean(1)
##  Bug. Either .mean(-1).mean(0) or .mean(). JGLi21Oct2022
        arrout = arr.reshape(shape).mean(-1).mean(0) 

    return arrout

def depthobstr(subathy, depmin=0.0):
    """ Average the subathy into a single value and caculate obstruction ratio """

##  Flatten the array first as only mean value is needed.
    fbathy=subathy.flatten()
    nxy=len(fbathy) 
    lnd=sum(fbathy >= depmin)
    obstr = float(lnd)/float(nxy) 
    depth = np.mean( fbathy )
       
    return (depth, obstr)


def reduceGEBCObstr(gebcofile='./GEBCO_2022.nc', scalefac=[8,6], depthmin=0.0, 
                    cutout=None, region=None, workdir='./'):
    """ Reduce the size of GEBCO grid and save obstruction ratio as land/total points.
    """
    print('[INFO] Reading data from %s' %gebcofile)
    print('[INFO] Running reduction of GEBCO data at scale factor ', scalefac)
    print('[INFO] Water point criterion is depth < %f ' %depthmin)
    dh = nc.Dataset(gebcofile)
    nlat = dh.dimensions['lat'].size
    nlon = dh.dimensions['lon'].size
    dlat = 180.0 / float(nlat)
    dlon = 360.0 / float(nlon)
    print( " Raw bathymetry dimensions:", nlon, nlat, dlon, dlat )

    ylat = dh.variables['lat'][:]
    xlon = dh.variables['lon'][:]
    y0lat= ylat[0]  - 0.5*dlat
    ynlat= ylat[-1] + 0.5*dlat
    x0lon= xlon[0]  - 0.5*dlon
    xnlon= xlon[-1] + 0.5*dlon
    print( " Raw bathymetry domain range:", x0lon, y0lat, xnlon, ynlat )

##  Work out new bathymetry dimension, to be whole integer factor.
    nfax = scalefac[0]
    nfay = scalefac[1]

##  For global bathy (cutout=None) use full GEBCO data.
    if( cutout is None ):
        ndmx = int((nlon/nfax)+0.001)
        ndmy = int((nlat/nfay)+0.001)
        iffx = 0
        jffy = 0
        if( ndmx*nfax != nlon or ndmy*nfay != nlat ):
            print( " New dimension not a whole integer factor:", ndmx, ndmy, nlon/nfax, nlat/nfay)
            return

##  For a regional bathy, round the region edge to align with global mesh, 
##  assuming global mesh is at 4 times of regional grid length. 
    else:
        stlon=cutout[0]; stlat=cutout[1]        
        edlon=cutout[2]; edlat=cutout[3]        
##  GEBCO_2019 longitude range is from -180.0 to 180.0.
        if( cutout[0] > xnlon ): stlon = cutout[0]-360.0
        if( cutout[2] > xnlon ): edlon = cutout[0]-360.0  

##  Round cutput domain to align with global mesh (4 times in mesh length).
        iffx = int( round( (stlon - x0lon)/(4*nfax*dlon) ) )*4
        jffy = int( round( (stlat - y0lat)/(4*nfay*dlat) ) )*4
        ndmx = int( round( (edlon - x0lon)/(4*nfax*dlon) ) )*4 - iffx
        ndmy = int( round( (edlat - y0lat)/(4*nfay*dlat) ) )*4 - jffy
        
    print( " New dimension iffx, jffy, ndmx, ndmy:", iffx, jffy, ndmx, ndmy )
    print( " New bathymetry domain:", xlon[iffx*nfax], ylat[jffy*nfay], 
                        xlon[(iffx+ndmx)*nfax-1], ylat[(jffy+ndmy)*nfay-1] ) 

##  Declare new bathy array
    depth = np.zeros([ndmy, ndmx], dtype=float)
    obstr = np.zeros([ndmy, ndmx], dtype=float)
    nwlat = np.zeros(ndmy)
    nwlon = np.zeros(ndmx)

##  Break raw data into roughly 400-cell tiles to speed up process.
    ntlx=400
    while (ntlx > 0):
        if( int(ndmx/ntlx)*ntlx == ndmx ): break
        ntlx -= 1

    ntly=400
    while (ntly > 0):
        if( int(ndmy/ntly)*ntly == ndmy ): break
        ntly -= 1

    print(' Tile size ntlx, ntly =', ntlx, ntly )
    nhtx=ntlx*nfax
    nhty=ntly*nfay

##  Loop over merged sub-arrays to calculate new depth and obstruction ratio
    print (" Reduction loop started at ", datetime.now().strftime('%F %H:%M:%S') )
    for ix in range(0,ndmx,ntlx):
        ihx = (ix+iffx)*nfax
        tmplon = dh.variables['lon'][ihx:ihx+nhtx]
        nwlon[ix:ix+ntlx] = rebin(tmplon, [ntlx]) 

        if( ix % ntlx*10 == 0 ):
            print(" ... processing ix =", ix, ' at ', datetime.now().strftime('%H:%M:%S') )
        for jy in range(0,ndmy,ntly):
            jhy = (jy+jffy)*nfay
##  Calculate new latitude only when ix == 0
            tmplat = dh.variables['lat'][jhy:jhy+nhty]
            nwlat[jy:jy+ntly] = rebin(tmplat, [ntly]) 
            if( ix == 0 and jy % ntly*100 == 0):
                print(" ... processing jy = ", jy )

##  Loop over depth sub-arrays to calculate new depth and obstruction ratio.
            tmpdep = dh.variables['elevation'][jhy:jhy+nhty,ihx:ihx+nhtx]

            for iix in range(ntlx):
                irx=iix*nfax
                for jjy in range(ntly):
                    jry=jjy*nfay
                    depth[jy+jjy,ix+iix], obstr[jy+jjy,ix+iix] =  \
                        depthobstr(tmpdep[jry:jry+nfay,irx:irx+nfax], depmin=depthmin)

##  End of sub-array loop and close raw data file.
    dh.close()
    print (" Reduction loop finished at ", datetime.now().strftime('%F %H:%M:%S') )

##  Save the reduced bathymetry and obstruction ratio.
    if region is None:
        outfile = workdir+'GEBCO_reduced_%d_%d' % (scalefac[0], scalefac[1]) + '.nc'
    else:
        outfile = workdir+region+'_reduced_%d_%d' % (scalefac[0], scalefac[1]) + '.nc'

    writeReducedNCxy(outfile, scalefac, depthmin, nwlat, nwlon, depth, obstr)    

    return  0 


##  Modified reduction with both elevation and obstruction.  JGLi19Apr2023
def reduceGEBCOxy(scalefac=[8,6], depthmin=0.0, cutout=None, region=None,
                  gebcofile='./GEBCO_2022.nc', workdir='./'):
    """ Controls the grid reduction process with built in lake corrections. """

    # generate the reduced grid
##  Test reducobstr function. Note mskout is replaced with obstruction ratio.  JGLi03Nov2022
    latout, lonout, depout, obsout = reducobstr(gebcofile, scalefac=scalefac, depthmin=depthmin, cutout=cutout)

##  Save the reduced bathymetry and obstruction ratio.
    if region is None:
        outfile = workdir+'GEBCO_reduced_%d_%d' % (scalefac[0], scalefac[1]) + '.nc'
    else:
        outfile = workdir+region+'_reduced_%d_%d' % (scalefac[0], scalefac[1]) + '.nc'
    writeReducedNCxy(outfile, scalefac, depthmin, latout, lonout, depout, obsout)    



##  Functions added to interpolate high resolution depth and obstruction ratios.
def interpdepthobstr(hiresfile, dx=0.5, dy=0.5, depthmin=0.0, cutout=None, workdir='./'):
    """ Interpolating depth and obstruction ratio into new resolution data. """

    print('[INFO] Reading data from %s' %hiresfile)
    print('[INFO] Interpolating data to resolution dx:%.6f, dy:%.6f' %(dx,dy))
    dh = nc.Dataset(hiresfile)
    nlat = dh.dimensions['lat'].size
    nlon = dh.dimensions['lon'].size
    ylat = dh.variables['lat'][:]
    xlon = dh.variables['lon'][:]
    dlat = (ylat[-1] - ylat[0])/float(nlat-1)
    dlon = (xlon[-1] - xlon[0])/float(nlon-1)
    print( " Raw bathymetry dimensions:", nlon, nlat, dlon, dlat )

    y0lat= ylat[0]  - 0.5*dlat
    ynlat= ylat[-1] + 0.5*dlat
    x0lon= xlon[0]  - 0.5*dlon
    xnlon= xlon[-1] + 0.5*dlon
    print( " Raw bathymetry domain range:", x0lon, y0lat, xnlon, ynlat )

    if cutout is None:
        x0 = -180.0 + dx / 2.0
        y0 = -90.0  + dy / 2.0
        xl = -1.0 * x0
        yl = -1.0 * y0
        offsx = 0
        offsy = 0
    else:
        if cutout[0] > 180.0: cutout[0] = cutout[0]-360.0
        if cutout[2] > 180.0: cutout[2] = cutout[2]-360.0
        print('[INFO] Cutout region lon-lat range:', cutout )
        x0 = cutout[0]
        y0 = cutout[1]
        xl = cutout[2]
        yl = cutout[3]
        offsx = int( round( (cutout[0]-x0lon)/dlon ))
        offsy = int( round( (cutout[1]-y0lat)/dlat ))

#  set the output arrays for interpolated grid,
#  assuming cutput values are at edge cell centre.
    newy = int((yl-y0)/dy+1.001)
    newx = int((xl-x0)/dx+1.001)
    print (" Interpolaton newx, newy, offsx, offsy = ", newx, newy, offsx, offsy )

    depout = np.zeros([newy, newx])
    obsout = np.zeros([newy, newx])
    latout = np.arange(y0, yl+dy/5.0, dy)
    lonout = np.arange(x0, xl+dx/5.0, dx)

##  Break raw data into roughly 1000 raw bathy points to speed up process.
    ntlx=400 
#   while (ntlx > 0):
#       if( int(nlon/ntlx)*ntlx == nlon ): break
#       ntlx -= 1

    ntly=300
#   while (ntly > 0):
#       if( int(nlat/ntly)*ntly == nlat ): break
#       ntly -= 1

    print(' Tile size ntlx, ntly =', ntlx, ntly )

    print (" Interpolaton loop started at ", datetime.now().strftime('%F %H:%M:%S') )

    # using loops/tiles here to avoid memory problems with read in of full dataset.
    ix = offsx
    ioutx = 0
    while ix < nlon-1:

        addx = np.min([ntlx+1, nlon-ix])
        tmplon = xlon[ix:ix+addx]
        print(' tmplog range ix, ix+addx = ', ix, ix+addx)
        tedlon = np.min( [tmplon[-1], lonout[-1]] )
        addoutx = int(np.floor((tedlon - lonout[ioutx]) / dx))
#       print('[INFO] Working on tile from x:%d' %ix)
#       print('[INFO] Raw longitude range: %.8f to %.8f' %(tmplon[0],tmplon[-1]))
#       print('[INFO] Number of processed grid cells in x dimension: %d' %addoutx)
#       print('[INFO] Processed grid longitude range: %.8f to %.8f' 
#             %(lonout[ioutx],lonout[ioutx+addoutx]))
        print(" ... Processing ix =",ix,' with step',addoutx,' at ',datetime.now().strftime('%H:%M:%S'))

        iy = offsy
        iouty = 0        
        while iy < nlat-1:
#           print('[INFO] Working on tile from x:%d, y:%d' %(ix,iy))
            addy = np.min([ntly+1, nlat-iy])
            tmplat = dh.variables['lat'][iy:iy+addy]
            tedlat = np.min( [tmplat[-1], latout[-1]] )
            addouty = int(np.floor((tedlat - latout[iouty]) / dy))
#           print('[INFO] GEBCO latitude range: %.8f to %.8f' %(tmplat[0],tmplat[-1]))
#           print('[INFO] Number of processed grid cells in y dimension: %d' %addouty)
#           print('[INFO] Processed grid latitude range: %.8f to %.8f' 
#                 %(latout[iouty],latout[iouty+addouty]))
#           print('[INFO]... read subdomain from file')
            if( iouty == 0 ):
                print(' ... Working on tile from x:%d, y:%d with step %d' %(ix,iy, addouty))
            tmpdep = dh.variables['elevation'  ][iy:iy+addy,ix:ix+addx]
            tmpobs = dh.variables['obstruction'][iy:iy+addy,ix:ix+addx]

#           print('[INFO]... interpolated to new subdomain')
            splinedep = interp.RectBivariateSpline(tmplat,tmplon,tmpdep)
            depout[iouty:iouty+addouty+1,ioutx:ioutx+addoutx+1] = \
              splinedep(latout[iouty:iouty+addouty+1],lonout[ioutx:ioutx+addoutx+1])
            splineobs = interp.RectBivariateSpline(tmplat,tmplon,tmpobs)
            obsout[iouty:iouty+addouty+1,ioutx:ioutx+addoutx+1] = \
              splineobs(latout[iouty:iouty+addouty+1],lonout[ioutx:ioutx+addoutx+1])
            iy = iy + addy - 1
            iouty = iouty + addouty + 1
        ix = ix + addx - 1
        ioutx = ioutx + addoutx + 1

    print (" Interpolation loop finished at ", datetime.now().strftime('%F %H:%M:%S') )

    # correct spline interpolation limits for obstruction ratio.
    obsout[obsout < 0.001] = 0.0
    obsout[obsout > 0.999] = 1.0

    dh.close()
 
##  Remove thin river points and straighten coastlines.  JGLi03Feb2023
##  Suspended for global tsunami model grid.   JGLi21Nov2023
#   print (" Removing isolated river points or straightening coastline ... ")
#   depout = remove_river(latout, lonout, depout, depmin=0.0)

    # write out data to a new netCDF file
    outfile = workdir+'Bathy_interpolated_' + datetime.now().strftime('%F_%H%M') + '.nc'
    writedepthobstrNC(outfile, dx, dy, depthmin, latout, lonout, depout, obsout)

    return latout, lonout 


def remove_river(latout, lonout, depout, depmin=0.0):
    """ Remove thin river heads to straighten coastlines. JGLi03Feb2023 """

##  Check whether it is a global bathymetry.
    nlon=len(lonout); nlat=len(latout)
    dlon=(lonout[-1] - lonout[0])/(float(nlon) - 1.0)
    if( dlon*nlon - 360.0 < 1.0E-6): 
        globl=True
        istr = 0; iend = nlon
        print(" Global bathy, dlon, nlon =", dlon, nlon)
    else:
        globl=False
        istr = 1; iend = nlon-1

##  Start removal loop until all isolated cells are removed.
    nloop = 0
    irivr = 10
    while irivr > 0:
        irmvd = 0 
        for jy in range(1,nlat-1,1):
            for ix in range(istr, iend, 1):
##  Break if it is a land point or continue for a sea point.
                if( depout[jy,ix] > depmin ): 
                    break
                else:
                    nij=0
                    bth=0.0
                    if( depout[jy-1,ix] > depmin ):
                        nij += 1
                        bth = bth + depout[jy-1,ix]
                    if( depout[jy+1,ix] > depmin ):
                        nij += 1
                        bth = bth + depout[jy+1,ix]
                    if( depout[jy,ix-1] > depmin ):
                        nij += 1
                        bth = bth + depout[jy,ix-1]
                    im = ix + 1
                    if( im == nlon and globl ): im = 0
                    if( depout[jy,im] > depmin ):
                        nij += 1
                        bth = bth + depout[jy,im]

##  Fill thin river point with average of all side land points bathy.
                    if( nij >= 3 ):
                        depout[jy,ix] = bth/float(nij) 
                        irmvd += 1

## End of one loop over all sea points, update nloop and irivr.
        nloop += 1
        irivr = irmvd 
        print( " nloop, irivr =", nloop, irivr )
 
## Continue while loop if irivr > 0, otherwise return.
    return depout 

##  End of function remove_river.



##  Include Andy's run_gebco_reduce.py as the main() function here and 
##  simplify input with a dict array.   JGLi19Apr2023

def main():

##  Import relevant modules and functions
    import sys
    from readmerg import readmerg

##  Read online arguments and input information file.
    if len(sys.argv) > 1:
       cfgfile = sys.argv[1]
    else:
       cfgfile = './configreduce.txt'

# read updated info from the configuration file
    cfginpt = readmerg(cfgfile)
    cfginfo = eval(cfginpt)
    for key in cfginfo.keys():
        print(key,' : ', cfginfo[key])

    action = cfginfo['action']

    if  action.lower()[0:6] == 'reduce':
##  Modified to use new reduceGEBCObstr function.  JGLi20Apr2023
        reduceGEBCObstr( gebcofile=cfginfo['gebcofile'],
                          scalefac=cfginfo['scalefac'],
                          depthmin=cfginfo['depthmin'],
                            cutout=cfginfo['extents'],
                            region=cfginfo['region'],
                           workdir=cfginfo['workdir'])

    elif action.lower()[0:6] == 'interp':
##  Modified to use new interpdepthobstr function.  JGLi08Nov2022
        interpdepthobstr(cfginfo['bathyfile'], 
                      dx=cfginfo['dxlon'], 
                      dy=cfginfo['dylat'], 
                depthmin=cfginfo['depthmin'],
                  cutout=cfginfo['extents'],
                 workdir=cfginfo['workdir'])


##  End of main program.


if __name__ == '__main__':
    main()


