"""
Write WW3 Meta Data Function

Write the meta data associated with the grids generated in this software.
This data needs to be provided as input to ww3_grid.inp when generating
the mod_def files for WAVEWATCH III.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 29-Mar-2013
"""

import os

import netCDF4

from .read_namelist import read_namelist


def write_ww3meta(fname, fname_nml, gtype, lon, lat, *args):
    """
    Write WW3 metadata file.
    
    Parameters
    ----------
    fname : str
        Output file name prefix
    fname_nml : str
        Namelist file name
    gtype : str
        Grid Type. Two options:
        - 'CURV': For curvilinear grids
        - 'RECT': For rectilinear grids
    lon : ndarray
        Longitude array (x) of the grid
        If gtype is 'RECT' this is a 1D array, if 'CURV' it's a 2D matrix
    lat : ndarray
        Latitude array (y) of the grid
        If gtype is 'RECT' this is a 1D array, if 'CURV' it's a 2D matrix
    *args : tuple
        Optional arguments:
        - N1, N2, N3: Scaling applied to bottom bathymetry data, obstruction
          grids and coordinate (x,y) grids respectively. N3 is optional and
          needed only for curvilinear grids.
        - ext1, ext2, ext3: Optional extensions for labeling depth, mask and
          obstruction files (must be equal to actual files).
    
    Returns
    -------
    messg : str
        Error message. Is blank if no error occurs
    errno : int
        Error number. Is zero for successful write
    """
    meta_file = f'{fname}.meta'
    
    try:
        # 强制使用 UTF-8，避免 Windows 默认编码（如 GBK）导致写入失败
        fid = open(meta_file, 'w', encoding='utf-8', newline='')
    except IOError as e:
        messg = f'Cannot open file: {meta_file}'
        errno = -1
        print(f'!!ERROR!!: {messg}')
        return messg, errno
    
    # Read namelist sections (if fname_nml is provided)
    # If fname_nml is None, use default values (matching MATLAB version behavior)
    if fname_nml is not None:
        init_nml = read_namelist(fname_nml, 'GRID_INIT')
        outgrid_nml = read_namelist(fname_nml, 'OUTGRID')
        bathy_nml = read_namelist(fname_nml, 'BATHY_FILE')
    else:
        # Default values when no namelist is provided (matching MATLAB create_grid.m)
        init_nml = {'fname': os.path.basename(fname).replace('.meta', '')}
        outgrid_nml = {}
        bathy_nml = {}
    
    # Write header comments
    header_lines = [
        '$ Define grid -------------------------------------- $',
        '$ Five records containing :',
        '$  1 Type of grid, coordinate system and type of closure: GSTRG, FLAGLL,',
        '$    CSTRG. Grid closure can only be applied in spherical coordinates.',
        '$      GSTRG  : String indicating type of grid :',
        '$               ''RECT''  : rectilinear',
        '$               ''CURV''  : curvilinear',
        '$      FLAGLL : Flag to indicate coordinate system :',
        '$               T  : Spherical (lon/lat in degrees)',
        '$               F  : Cartesian (meters)',
        '$      CSTRG  : String indicating the type of grid index space closure :',
        '$               ''NONE''  : No closure is applied',
        '$               ''SMPL''  : Simple grid closure : Grid is periodic in the',
        '$                         : i-index and wraps at i=NX+1. In other words,',
        '$                         : (NX+1,J) => (1,J). A grid with simple closure',
        '$                         : may be rectilinear or curvilinear.',
        '$               ''TRPL''  : Tripole grid closure : Grid is periodic in the',
        '$                         : i-index and wraps at i=NX+1 and has closure at',
        '$                         : j=NY+1. In other words, (NX+1,J<=NY) => (1,J)',
        '$                         : and (I,NY+1) => (MOD(NX-I+1,NX)+1,NY). Tripole',
        '$                         : grid closure requires that NX be even. A grid',
        '$                         : with tripole closure must be curvilinear.',
        '$  2 NX, NY. As the outer grid lines are always defined as land',
        '$    points, the minimum size is 3x3.',
    ]
    
    for line in header_lines:
        fid.write(line + '\n')
    
    # Write grid type specific comments
    if gtype == 'RECT':
        strs = [
            '$  3 Grid increments SX, SY (degr.or m) and scaling (division) factor.',
            '$    If NX*SX = 360., latitudinal closure is applied.',
            '$  4 Coordinates of (1,1) (degr.) and scaling (division) factor.',
        ]
        for s in strs:
            fid.write(s + '\n')
    elif gtype == 'CURV':
        strs = [
            '$  3 Unit number of file with x-coordinate.',
            '$    Scale factor and add offset: x <= scale_fac * x_read + add_offset.',
            '$    IDLA, IDFM, format for formatted read, FROM and filename.',
            '$  4 Unit number of file with y-coordinate.',
            '$    Scale factor and add offset: y <= scale_fac * y_read + add_offset.',
            '$    IDLA, IDFM, format for formatted read, FROM and filename.',
        ]
        for s in strs:
            fid.write(s + '\n')
    else:
        print('!!ERROR!!: Unrecognized Grid Type')
        fid.close()
        return 'Unrecognized Grid Type', -1
    
    # Write bathymetry file format comments
    bathy_lines = [
        '$  5 Limiting bottom depth (m) to discriminate between land and sea',
        '$    points, minimum water depth (m) as allowed in model, unit number',
        '$    of file with bottom depths, scale factor for bottom depths (mult.),',
        '$    IDLA, IDFM, format for formatted read, FROM and filename.',
        '$      IDLA : Layout indicator :',
        '$                  1   : Read line-by-line bottom to top.',
        '$                  2   : Like 1, single read statement.',
        '$                  3   : Read line-by-line top to bottom.',
        '$                  4   : Like 3, single read statement.',
        '$      IDFM : format indicator :',
        '$                  1   : Free format.',
        '$                  2   : Fixed format with above format descriptor.',
        '$                  3   : Unformatted.',
        '$      FROM : file type parameter',
        '$             ''UNIT'' : open file by unit number only.',
        '$             ''NAME'' : open file by name and assign to unit.',
        '$  If the Unit Numbers in above files is 10 then data is read from this file',
        '$',
    ]
    
    for line in bathy_lines:
        fid.write(line + '\n')
    
    # Grid type longitude/latitude or x/y
    # If fname_nml is None, use default values (matching MATLAB version)
    if fname_nml is not None:
        ref_dir = init_nml['ref_dir']
        ref_grid = bathy_nml['ref_grid']
        xvar = bathy_nml['xvar']
        
        fname_bathy = os.path.join(ref_dir, f'{ref_grid}.nc')
        
        try:
            f = netCDF4.Dataset(fname_bathy, 'r')
            var_lon = f.variables[xvar]
            try:
                lon_units = var_lon.units
            except AttributeError:
                import warnings
                warnings.warn('No units attribute for spatial dimensions. Setting units to degree')
                lon_units = 'degree'
            f.close()
            
            # Check if units contain 'degree'
            if 'degree' in lon_units.lower():
                FLAGLL = 'T'
            else:
                FLAGLL = 'F'
        except Exception as e:
            print(f'!!ERROR!!: Cannot read bathymetry file: {e}')
            fid.close()
            return f'Cannot read bathymetry file: {e}', -1
        
        # Grid closure, longitude wrapping around or not
        isglobal = outgrid_nml.get('is_global', 0)
        if isglobal == 1:
            CSTRNG = 'SMPL'
        elif isglobal == 0:
            CSTRNG = 'NONE'
        else:
            print('!!ERROR!!: Unrecognized Grid Closure')
            fid.close()
            return 'Unrecognized Grid Closure', -1
    else:
        # When fname_nml is None, use defaults matching MATLAB create_grid.m
        # For rectilinear grids with lon/lat coordinates, use 'T' and 'NONE'
        FLAGLL = 'T'  # Spherical coordinates (lon/lat in degrees)
        CSTRNG = 'NONE'  # No closure
    
    # Write grid type, coordinate system, and closure
    fid.write(f"   '{gtype}'  {FLAGLL} '{CSTRNG}'\n")
    
    # Write grid dimensions and coordinates based on grid type
    if gtype == 'RECT':
        if len(args) < 2:
            fid.close()
            return 'Missing required arguments N1, N2 for RECT grid', -1
        N1 = args[0]
        N2 = args[1]
        Ny, Nx = lon.shape if len(lon.shape) == 2 else (len(lat), len(lon))
        fid.write(f'{Nx} \t {Ny} \n')
        # Calculate grid increments from actual grid points
        # IMPORTANT: Always use actual grid point spacing, not user input values
        # This ensures grid.meta dx/dy matches the actual grid.bot file structure
        # Using user input values can cause "PREMATURE END OF FILE" errors in ww3_grid
        # because the expected grid dimensions don't match the actual file
        if len(lon.shape) == 2:
            dx_minutes = (lon[0, 1] - lon[0, 0]) * 60
            dy_minutes = (lat[1, 0] - lat[0, 0]) * 60
        else:
            dx_minutes = (lon[1] - lon[0]) * 60
            dy_minutes = (lat[1] - lat[0]) * 60
        
        # Get starting coordinates
        if len(lon.shape) == 2:
            lon0 = lon[0, 0]
            lat0 = lat[0, 0]
        else:
            lon0 = lon[0]
            lat0 = lat[0]
        
        # Format dx/dy with fixed width (5 characters) to match MATLAB's %5.2f format
        # This ensures consistent formatting for ww3_grid to parse correctly
        # Note: When dx > 0.05, dx_minutes > 3.0, and formatting may not have leading space
        # but this matches MATLAB behavior and should be acceptable for ww3_grid
        fid.write(f'{dx_minutes:5.2f} \t {dy_minutes:5.2f} \t {60:5.2f} \n')
        fid.write(f'{lon0:8.4f} \t {lat0:8.4f} \t {1:5.2f}\n')
    elif gtype == 'CURV':
        if len(args) < 3:
            fid.close()
            return 'Missing required arguments N1, N2, N3 for CURV grid', -1
        N1 = args[0]
        N2 = args[1]
        N3 = args[2]
        Ny, Nx = lon.shape
        fid.write(f'{Nx} \t {Ny} \n')
        fid.write(f'{20}  {N3:f}  {0.0:5.2f}  {1}  {1} \'(....)\'  NAME  \'{fname}.lon\'  \n')
        fid.write(f'{30}  {N3:f}  {0.0:5.2f}  {1}  {1} \'(....)\'  NAME  \'{fname}.lat\'  \n')
    else:
        print('!!ERROR!!: Unrecognized Grid Type')
        fid.close()
        return 'Unrecognized Grid Type', -1
    
    # Determine file extensions
    # MATLAB: if nargin <= 7, use default extensions '.depth_ascii', '.obstr_lev1', '.mask'
    # But actual files written are '.bot', '.obst', '.mask'
    # We use the actual file extensions to match what's written
    if len(args) <= 5:
        # Use actual file extensions that match what create_grid writes
        ext1 = '.bot'  # Actual file: grid.bot (not grid.depth_ascii)
        ext2 = '.obst'  # Actual file: grid.obst (not grid.obstr_lev1)
        ext3 = '.mask'  # Actual file: grid.mask
    else:
        ext1 = args[3]
        ext2 = args[4]
        ext3 = args[5]
    
    # Write file information
    # MATLAB format: %5.2f  %5.2f  %d  %f  %d  %d %s  %s  %s
    fid.write('$ Bottom Bathymetry \n')
    fid.write(f'{-0.1:5.2f}  {2.5:5.2f}  {40}  {N1:f}  {1}  {1} \'(....)\'  NAME  \'{fname}{ext1}\' \n')
    fid.write('$ Sub-grid information \n')
    fid.write(f'{50}  {N2:f}  {1}  {1}  \'(....)\'  NAME  \'{fname}{ext2}\'  \n')
    fid.write('$ Mask Information \n')
    fid.write(f'{60}  {1}  {1}  \'(....)\'  NAME  \'{fname}{ext3}\'  \n')
    fid.write('$\n')
    
    fid.close()
    return '', 0

