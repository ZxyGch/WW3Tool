"""
Optional Boundary Function

This routine reads an optional polygon data set that has been created
to mask out water bodies that do not play a major role in wave
propagation. The polygons that are included are based on switches read
from a file.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 23-Oct-2012
"""

import os

import scipy.io


def optional_bound(ref_dir, fname):
    """
    Read optional boundary polygons based on switches in a file.
    
    Parameters
    ----------
    ref_dir : str
        PATH to reference directory that includes the file
        "optional_coastal_polygons.mat"
    fname : str
        Filename that has a list of switches to choose which of the
        optional polygons need to be switched off or on. The switches
        in the file should coincide with the polygons in the
        "optional_coastal_polygons.mat" file.
    
    Returns
    -------
    b : list
        An array of boundary polygon data structures (dictionaries)
    usr_cnt : int
        Total number of polygons found
    """
    # Load the optional coastal polygons MAT file
    mat_file = os.path.join(ref_dir, 'optional_coastal_polygons.mat')
    mat_data = scipy.io.loadmat(mat_file)
    user_bound = mat_data['user_bound']
    
    # Convert MATLAB struct array to Python list of dicts
    # MATLAB struct arrays are stored as structured arrays in scipy.io.loadmat
    N = user_bound.shape[0] if len(user_bound.shape) > 0 else 1
    
    # Read the switch file
    try:
        with open(fname, 'r') as fid:
            usr_cnt = 0
            b = []
            
            for i in range(N):
                line = fid.readline()
                if not line:
                    break
                
                # Parse the line: expect format like "1 1" (index, switch)
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        idx = int(parts[0])
                        switch = int(parts[1])
                        
                        if switch == 1:
                            # Extract polygon data from MATLAB struct
                            # user_bound is a structured array
                            if N == 1:
                                poly = user_bound
                            else:
                                poly = user_bound[i]
                            
                            # Convert to dictionary
                            poly_dict = {}
                            for field_name in poly.dtype.names:
                                field_data = poly[field_name][0, 0]
                                # Handle different data types
                                if field_data.size == 1:
                                    poly_dict[field_name] = float(field_data)
                                else:
                                    poly_dict[field_name] = field_data.flatten()
                            
                            b.append(poly_dict)
                            
                            # Calculate west and east bounds
                            if 'x' in poly_dict:
                                b[usr_cnt]['west'] = float(poly_dict['x'].min())
                                b[usr_cnt]['east'] = float(poly_dict['x'].max())
                            
                            usr_cnt += 1
                    except (ValueError, IndexError):
                        continue
    
    except IOError as e:
        print(f'!!ERROR!!: Cannot open file: {fname}')
        return [], 0
    
    if usr_cnt == 0:
        b = [-1]
    
    return b, usr_cnt

