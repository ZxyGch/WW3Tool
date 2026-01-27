"""
Compute Boundary Function

Computes the shoreline polygons from the GSHHS database that lie within
the grid domain, properly accounting for polygons that cross the domain.
The routine has been designed to work with coastal polygons by default.

Copyright 2009 National Weather Service (NWS),
National Oceanic and Atmospheric Administration. All rights reserved.
Distributed with WAVEWATCH III

Last Update: 23-Oct-2012
"""

import numpy as np
from matplotlib.path import Path


def compute_boundary(coord, bound, min_val=None, bflg=None):
    """
    Compute shoreline polygons that lie within the grid domain.
    
    Parameters
    ----------
    coord : list or ndarray
        An array defining the corner points of the grid:
        coord[0] = Latitude (y) of lower left hand corner
        coord[1] = Longitude (x) of lower left hand corner
        coord[2] = Latitude (y) of upper right hand corner
        coord[3] = Longitude (x) of upper right hand corner
    bound : list
        A data structure array (list of dicts) of the basic polygons.
        Each dict should have keys: 'x', 'y', 'n', 'west', 'east', 'south',
        'north', 'level', etc.
    min_val : float, optional
        Threshold defining the minimum distance between the edge of polygon
        and the inside/outside boundary. A low value reduces computation time
        but can raise errors if the grid is too coarse. Default is 4.
    bflg : int, optional
        Optional definition of flag type from the gshhs boundary database:
        1 = land; 2 = lake margin; 3 = in-lake island.
        If left blank, defaults to land (1).
    
    Returns
    -------
    bound_ingrid : list
        Subset data structure array (list of dicts) of polygons that lie
        inside the grid
    Nb : int
        Total number of polygons found that lie inside the grid
    """
    # Handle optional arguments
    if min_val is None:
        min_val = 4  # Default value
    if bflg is None:
        bflg = 1  # Default: land boundaries
    
    min_val_ori = min_val
    
    lat_start = coord[0]
    lon_start = coord[1]
    lat_end = coord[2]
    lon_end = coord[3]
    
    # Definitions
    eps = 1e-5
    MAX_SEG_LENGTH = 0.25
    
    # Polygon defining the bounding grid. Bounding grid is defined in the
    # counter clockwise direction
    px = np.array([lon_start, lon_end, lon_end, lon_start, lon_start])
    py = np.array([lat_start, lat_start, lat_end, lat_end, lat_start])
    
    # Slope and intercepts for each of the 4 lines of the bounding box
    m_grid = np.zeros(4)
    c_grid = np.zeros(4)
    box_length = np.zeros(4)
    norm = np.zeros((5, 2))
    
    for i in range(4):
        if px[i + 1] == px[i]:
            m_grid[i] = np.inf
            c_grid[i] = 0
        else:
            # Linear fit: y = m*x + c
            # For two points: m = (y2-y1)/(x2-x1), c = y1 - m*x1
            m_grid[i] = (py[i + 1] - py[i]) / (px[i + 1] - px[i])
            c_grid[i] = py[i] - m_grid[i] * px[i]
        
        box_length[i] = np.sqrt((px[i + 1] - px[i])**2 + (py[i + 1] - py[i])**2)
        norm[i, 0] = (py[i + 1] - py[i]) / box_length[i]
        norm[i, 1] = -(px[i + 1] - px[i]) / box_length[i]
    
    norm[4, 0] = norm[0, 0]
    norm[4, 1] = norm[0, 1]
    
    # Initialize variables
    N = len(bound)
    in_coord = 0
    bound_ingrid = []
    itmp = 0
    itmp_prev = -1  # Initialize to -1 to ensure first log output
    
    # Pre-filter boundaries using bounding box check (fast)
    # This significantly reduces the number of boundaries to process
    candidate_indices = []
    for i in range(N):
        try:
            # Quick bounding box check
            level_val = bound[i].get('level', 0) if isinstance(bound[i], dict) else 0
            if isinstance(level_val, np.ndarray):
                level_val = float(level_val.item()) if level_val.size == 1 else float(level_val.flat[0]) if level_val.size > 0 else 0
            elif isinstance(level_val, (list, tuple)):
                level_val = float(level_val[0]) if len(level_val) > 0 else 0
            else:
                level_val = float(level_val)
            
            if level_val != bflg and level_val != 2:
                continue
            
            west_val = bound[i].get('west', 0) if isinstance(bound[i], dict) else 0
            east_val = bound[i].get('east', 0) if isinstance(bound[i], dict) else 0
            south_val = bound[i].get('south', 0) if isinstance(bound[i], dict) else 0
            north_val = bound[i].get('north', 0) if isinstance(bound[i], dict) else 0
            
            if isinstance(west_val, np.ndarray):
                west_val = west_val.item() if west_val.size == 1 else west_val[0]
            if isinstance(east_val, np.ndarray):
                east_val = east_val.item() if east_val.size == 1 else east_val[0]
            if isinstance(south_val, np.ndarray):
                south_val = south_val.item() if south_val.size == 1 else south_val[0]
            if isinstance(north_val, np.ndarray):
                north_val = north_val.item() if north_val.size == 1 else north_val[0]
            
            # Quick rejection: bounding box doesn't intersect grid
            if (west_val > lon_end or east_val < lon_start or
                    south_val > lat_end or north_val < lat_start):
                continue
            
            candidate_indices.append(i)
        except:
            continue
    
    N_candidates = len(candidate_indices)
    
    # Loop through candidate boundaries only
    for idx, i in enumerate(candidate_indices):
        try:
            # Limit boundaries to coastal type only
            # Handle both scalar and array values for level
            level_val = bound[i]['level']
            # Convert to scalar if it's an array
            if isinstance(level_val, np.ndarray):
                if level_val.size == 1:
                    level_val = float(level_val.item())
                elif level_val.size > 0:
                    level_val = float(level_val.flat[0])
                else:
                    continue  # Skip if empty
            elif isinstance(level_val, (list, tuple)):
                if len(level_val) > 0:
                    level_val = float(level_val[0])
                else:
                    continue  # Skip if empty
            else:
                level_val = float(level_val)
            
            if level_val == bflg or level_val == 2:
                # Determine if boundary lies completely outside the domain
                # Handle both scalar and array values
                west_val = bound[i]['west']
                east_val = bound[i]['east']
                south_val = bound[i]['south']
                north_val = bound[i]['north']
                
                if isinstance(west_val, np.ndarray):
                    west_val = west_val.item() if west_val.size == 1 else west_val[0]
                if isinstance(east_val, np.ndarray):
                    east_val = east_val.item() if east_val.size == 1 else east_val[0]
                if isinstance(south_val, np.ndarray):
                    south_val = south_val.item() if south_val.size == 1 else south_val[0]
                if isinstance(north_val, np.ndarray):
                    north_val = north_val.item() if north_val.size == 1 else north_val[0]
                
                if (west_val > lon_end or east_val < lon_start or
                        south_val > lat_end or north_val < lat_start):
                    in_grid = False
                else:
                    in_grid = True
                
                lev1 = level_val
                
                # Determine if boundary lies completely inside the domain
                if (west_val >= lon_start and east_val <= lon_end and
                        south_val >= lat_start and north_val <= lat_end):
                    inside_grid = True
                else:
                    inside_grid = False
                
                # Ignore boundaries outside the domain
                if in_grid:
                    # Modify boundaries that are not completely inside domain
                    if not inside_grid:
                        # Determine the points of the boundary that are
                        # inside/on/outside the bounding box
                        bbox_path = Path(np.column_stack([px[:-1], py[:-1]]))
                        
                        # Handle boundary x and y which might be arrays or lists
                        bound_x_raw = bound[i]['x']
                        bound_y_raw = bound[i]['y']
                        
                        # Convert to numpy arrays and flatten if needed
                        # Handle nested arrays (from MATLAB struct arrays)
                        def extract_array(data):
                            """Recursively extract array from nested structures"""
                            if isinstance(data, np.ndarray):
                                # If it's an object array, extract the first element
                                if data.dtype == object:
                                    if data.size > 0:
                                        first_elem = data.flat[0]
                                        # Recursively extract if still nested
                                        return extract_array(first_elem)
                                    else:
                                        return np.array([])
                                # Flatten multi-dimensional arrays
                                elif data.ndim > 1:
                                    return data.flatten()
                                else:
                                    return data
                            else:
                                return np.array(data).flatten()
                        
                        bound_x_raw = extract_array(bound_x_raw)
                        bound_y_raw = extract_array(bound_y_raw)
                        
                        # Ensure same length
                        min_len = min(len(bound_x_raw), len(bound_y_raw))
                        if min_len == 0:
                            # Skip this boundary if no points
                            continue
                        bound_x = bound_x_raw[:min_len]
                        bound_y = bound_y_raw[:min_len]
                        
                        points = np.column_stack([bound_x, bound_y])
                        # MATLAB inpolygon returns both in and on flags
                        # We need to check both separately
                        # Use a small positive radius to expand polygon and include boundary points
                        # Positive radius expands the polygon, making it more permissive for small islands
                        in_points = bbox_path.contains_points(points, radius=1e-6)
                        on_points = np.zeros(len(in_points), dtype=bool)
                        
                        # Check for points on the grid boundary edges
                        # MATLAB inpolygon treats points on edges as "in"
                        # We need to identify which points are exactly on edges
                        for j in range(len(points)):
                            x_pt = points[j, 0]
                            y_pt = points[j, 1]
                            
                            # Check if point is on any of the 4 grid edges
                            for k in range(4):
                                if np.isinf(m_grid[k]):
                                    # Vertical edge: check if x matches
                                    if abs(x_pt - px[k]) <= eps:
                                        # Check if y is within edge bounds
                                        y_min = min(py[k], py[k + 1])
                                        y_max = max(py[k], py[k + 1])
                                        if y_min - eps <= y_pt <= y_max + eps:
                                            on_points[j] = True
                                            in_points[j] = True  # Treat on as in
                                            break
                                else:
                                    # Non-vertical edge: check distance to line
                                    dist = abs(m_grid[k] * x_pt + c_grid[k] - y_pt)
                                    if dist <= eps:
                                        # Check if point is within edge bounds
                                        x_min = min(px[k], px[k + 1])
                                        x_max = max(px[k], px[k + 1])
                                        y_min = min(py[k], py[k + 1])
                                        y_max = max(py[k], py[k + 1])
                                        if (x_min - eps <= x_pt <= x_max + eps and
                                            y_min - eps <= y_pt <= y_max + eps):
                                            on_points[j] = True
                                            in_points[j] = True  # Treat on as in
                                            break
                        
                        loc1 = np.where(in_points)[0]
                        loc2 = np.where(on_points)[0]
                        
                        # Ignore points that lie on the domain but neighboring
                        # points do not
                        n = bound[i]['n']
                        # Ensure n is a scalar integer
                        if isinstance(n, np.ndarray):
                            n = int(n.item() if n.size == 1 else n.flat[0])
                        else:
                            n = int(n)
                        for j in range(len(loc2)):
                            point_idx = loc2[j]  # Use point_idx to avoid overwriting outer loop idx
                            if point_idx == 0:
                                p1 = n - 1
                                p2 = 1
                            elif point_idx == n - 1:
                                p1 = point_idx - 1
                                p2 = 0
                            else:
                                p1 = point_idx - 1
                                p2 = point_idx + 1
                            
                            if not in_points[p1] and not in_points[p2]:
                                in_points[point_idx] = False
                        
                        # Points of domain in the boundary
                        # Use the same bound_x and bound_y we prepared above
                        poly_path = Path(np.column_stack([bound_x, bound_y]))
                        # MATLAB: domain_inb = inpolygon(px,py,bound(i).x,bound(i).y)
                        # px and py have 5 elements (closed polygon: 4 corners + repeat first)
                        # We check all 5 points to match MATLAB behavior
                        domain_points = np.column_stack([px, py])
                        # Use a small positive radius to include boundary points
                        # Positive radius expands the polygon, making it more permissive for small islands
                        domain_inb = poly_path.contains_points(domain_points, radius=1e-6)
                        loc_t = np.where(domain_inb)[0]
                        domain_inb_lth = len(loc_t)
                        
                        if len(loc1) == 0:
                            # MATLAB: if (domain_inb_lth == length(px))
                            # px has 5 elements (4 corners + repeat), so length(px) = 5
                            if domain_inb_lth == 5:
                                # Domain is completely inside boundary
                                bound_dict = {
                                    'x': px[:-1],
                                    'y': py[:-1],
                                    'n': len(px) - 1,
                                    'west': lon_start,
                                    'east': lon_end,
                                    'north': lat_end,
                                    'south': lat_start,
                                    'height': lat_end - lat_start,
                                    'width': lon_end - lon_start,
                                    'level': lev1
                                }
                                bound_ingrid.append(bound_dict)
                                in_coord += 1
                        
                        # Loop through only if there are points inside the domain
                        if len(loc1) > 0:
                            n = bound[i]['n']
                            # Ensure n is a scalar integer
                            if isinstance(n, np.ndarray):
                                n = int(n.item() if n.size == 1 else n.flat[0])
                            else:
                                n = int(n)
                            
                            # Flag the points where the boundary moves from in
                            # to out of the domain as well as out to in
                            in2out = []
                            out2in = []
                            
                            for j in range(n - 1):
                                if in_points[j] and not in_points[j + 1]:
                                    in2out.append(j)
                                if not in_points[j] and in_points[j + 1]:
                                    out2in.append(j)
                            
                            in2out_count = len(in2out)
                            out2in_count = len(out2in)
                            
                            if in2out_count != out2in_count:
                                raise ValueError(f'Error: mismatch in grid crossings, check boundary {i}!!')
                            
                            # Crossing points are oriented to make sure we start
                            # from out to in
                            if in2out_count > 0 and in_points[0]:
                                in2out_tmp = in2out.copy()
                                for j in range(in2out_count - 1):
                                    in2out[j] = in2out_tmp[j + 1]
                                in2out[in2out_count - 1] = in2out_tmp[0]
                            
                            # For each in2out and out2in find a grid intersecting point
                            in2out_gridbox = np.zeros(in2out_count, dtype=int)
                            out2in_gridbox = np.zeros(out2in_count, dtype=int)
                            in2out_gridboxdist = np.zeros(in2out_count)
                            out2in_gridboxdist = np.zeros(out2in_count)
                            in2out_xcross = np.full(in2out_count, np.nan)
                            in2out_ycross = np.full(in2out_count, np.nan)
                            out2in_xcross = np.full(out2in_count, np.nan)
                            out2in_ycross = np.full(out2in_count, np.nan)
                            
                            # Calculate intersection points with grid boundaries
                            for j in range(in2out_count):
                                # Check if point is on grid boundary
                                if on_points[in2out[j]]:
                                    x1 = bound_x[in2out[j]]
                                    y1 = bound_y[in2out[j]]
                                    
                                    # Find which grid edge the point is on
                                    for k in range(4):
                                        if np.isinf(m_grid[k]):
                                            g = abs(x1 - px[k])
                                        else:
                                            g = abs(m_grid[k] * x1 + c_grid[k] - y1)
                                        
                                        if g <= eps:
                                            in2out_gridbox[j] = k
                                            in2out_gridboxdist[j] = k + np.sqrt((px[k] - x1)**2 + (py[k] - y1)**2) / box_length[k]
                                            break
                                    
                                    in2out_xcross[j] = np.nan
                                    in2out_ycross[j] = np.nan
                                else:
                                    # Calculate line-line intersection
                                    x1 = bound_x[in2out[j]]
                                    x2 = bound_x[in2out[j] + 1]
                                    y1 = bound_y[in2out[j]]
                                    y2 = bound_y[in2out[j] + 1]
                                    
                                    # Handle longitude wrapping
                                    if x2 == x1:
                                        m = np.inf
                                        c = 0
                                    else:
                                        if abs(x2 - x1) > 90:
                                            x2 = x2 + 360
                                            if abs(x2 - x1) > 90:
                                                x2 = x2 - 720
                                        # Linear fit: y = m*x + c
                                        m = (y2 - y1) / (x2 - x1)
                                        c = y1 - m * x1
                                    
                                    d = np.sqrt((x1 - x2)**2 + (y1 - y2)**2)
                                    
                                    # Find intersection with grid edges
                                    for k in range(4):
                                        if m != m_grid[k]:
                                            if not np.isinf(m) and not np.isinf(m_grid[k]):
                                                x = (c_grid[k] - c) / (m - m_grid[k])
                                                y = m * x + c
                                            elif np.isinf(m):
                                                x = x1
                                                y = m_grid[k] * x + c_grid[k]
                                            else:  # m_grid[k] is inf
                                                x = px[k]
                                                y = m * x + c
                                            
                                            # Check if intersection is on the line segment
                                            d1 = np.sqrt((x1 - x)**2 + (y1 - y)**2)
                                            d2 = np.sqrt((x - x2)**2 + (y - y2)**2)
                                            if abs(1 - (d1 + d2) / d) < 0.001:
                                                in2out_gridbox[j] = k
                                                in2out_xcross[j] = x
                                                in2out_ycross[j] = y
                                                in2out_gridboxdist[j] = k + np.sqrt((px[k] - x)**2 + (py[k] - y)**2) / box_length[k]
                                                break
                                
                                # Similar calculation for out2in points
                                if on_points[out2in[j] + 1]:
                                    x1 = bound_x[out2in[j] + 1]
                                    y1 = bound_y[out2in[j] + 1]
                                    
                                    for k in range(4):
                                        if np.isinf(m_grid[k]):
                                            g = abs(x1 - px[k])
                                        else:
                                            g = abs(m_grid[k] * x1 + c_grid[k] - y1)
                                        
                                        if g <= eps:
                                            out2in_gridbox[j] = k
                                            out2in_gridboxdist[j] = k + np.sqrt((px[k] - x1)**2 + (py[k] - y1)**2) / box_length[k]
                                            break
                                    
                                    out2in_xcross[j] = np.nan
                                    out2in_ycross[j] = np.nan
                                else:
                                    x1 = bound_x[out2in[j]]
                                    x2 = bound_x[out2in[j] + 1]
                                    y1 = bound_y[out2in[j]]
                                    y2 = bound_y[out2in[j] + 1]
                                    
                                    if x2 == x1:
                                        m = np.inf
                                        c = 0
                                    else:
                                        if abs(x2 - x1) > 90:
                                            x1 = x1 + 360
                                            if abs(x2 - x1) > 90:
                                                x1 = x1 - 720
                                        m = (y2 - y1) / (x2 - x1)
                                        c = y1 - m * x1
                                    
                                    d = np.sqrt((x1 - x2)**2 + (y1 - y2)**2)
                                    
                                    for k in range(4):
                                        if m != m_grid[k]:
                                            if not np.isinf(m) and not np.isinf(m_grid[k]):
                                                x = (c_grid[k] - c) / (m - m_grid[k])
                                                y = m * x + c
                                            elif np.isinf(m):
                                                x = x1
                                                y = m_grid[k] * x + c_grid[k]
                                            else:
                                                x = px[k]
                                                y = m * x + c
                                            
                                            d1 = np.sqrt((x1 - x)**2 + (y1 - y)**2)
                                            d2 = np.sqrt((x - x2)**2 + (y - y2)**2)
                                            if abs(1 - (d1 + d2) / d) < 0.001:
                                                out2in_gridbox[j] = k
                                                out2in_xcross[j] = x
                                                out2in_ycross[j] = y
                                                out2in_gridboxdist[j] = k + np.sqrt((px[k] - x)**2 + (py[k] - y)**2) / box_length[k]
                                                break
                            
                            # Build boundary segments properly
                            if in2out_count > 0:
                                subseg_acc = np.zeros(in2out_count, dtype=int)
                                # MATLAB: crnr_acc = 1 - domain_inb
                                # domain_inb has 5 elements (indices 0-4), but we only track 4 corners
                                # In MATLAB, crnr_acc(k+1) where k is edge index (1-4), so k+1 is 2-5
                                # In Python, edge index k (0-3) corresponds to corner index k+1 (1-4)
                                # So we need crnr_acc to have 5 elements, but we only use indices 1-4
                                crnr_acc = 1 - domain_inb.astype(int)
                                
                                # Process each boundary segment
                                while np.any(subseg_acc == 0):
                                    # Find closest unprocessed segment
                                    # MATLAB: min_val = 4 (min_val_ori), but if no segment found
                                    # with distance <= 4, it will still use min_pos = 0 (first unprocessed)
                                    # So we need to find the minimum distance segment if none <= min_val_ori
                                    min_pos = -1
                                    min_val = min_val_ori
                                    min_val_any = np.inf  # Track minimum distance regardless of threshold
                                    min_pos_any = -1
                                    
                                    for j in range(in2out_count):
                                        if subseg_acc[j] == 0:
                                            # Track minimum distance regardless of threshold
                                            if out2in_gridboxdist[j] < min_val_any:
                                                min_val_any = out2in_gridboxdist[j]
                                                min_pos_any = j
                                            # Prefer segments within threshold
                                            if out2in_gridboxdist[j] <= min_val:
                                                min_val = out2in_gridboxdist[j]
                                                min_pos = j
                                    
                                    # If no segment found within threshold, use the closest one anyway
                                    if min_pos < 0:
                                        if min_pos_any >= 0:
                                            min_pos = min_pos_any
                                            min_val = min_val_any
                                        else:
                                            # This should not happen if there are unprocessed segments
                                            raise ValueError('Error: no intersection point found. Consider increasing the SPLIT_LIM parameter')
                                    
                                    j = min_pos
                                    bound_x_seg = []
                                    bound_y_seg = []
                                    
                                    # Start with intersection point if available
                                    if not np.isnan(out2in_xcross[j]):
                                        bound_x_seg.append(out2in_xcross[j])
                                        bound_y_seg.append(out2in_ycross[j])
                                    
                                    # Add boundary points between intersections
                                    if (out2in[j] + 1) <= in2out[j]:
                                        bound_x_seg.extend(bound_x[out2in[j] + 1:in2out[j] + 1])
                                        bound_y_seg.extend(bound_y[out2in[j] + 1:in2out[j] + 1])
                                    else:
                                        # Handle wrap around
                                        bound_x_seg.extend(bound_x[out2in[j] + 1:])
                                        bound_x_seg.extend(bound_x[1:in2out[j] + 1])
                                        bound_y_seg.extend(bound_y[out2in[j] + 1:])
                                        bound_y_seg.extend(bound_y[1:in2out[j] + 1])
                                    
                                    # Add end intersection point if available
                                    if not np.isnan(in2out_xcross[j]):
                                        bound_x_seg.append(in2out_xcross[j])
                                        bound_y_seg.append(in2out_ycross[j])
                                    
                                    # Add grid corners if needed
                                    starting_edge = out2in_gridbox[j]
                                    ending_edge = in2out_gridbox[j]
                                    subseg_acc[j] = 1
                                    
                                    # Find next segments and add grid corners
                                    close_bound = False
                                    seg_index = j
                                    
                                    while not close_bound:
                                        # Check if all segments processed
                                        if np.all(subseg_acc == 1):
                                            # Add remaining grid corners
                                            # MATLAB: for k = in2out_gridbox(seg_index):4
                                            # Note: in2out_gridbox is 0-based edge index (0-3)
                                            # domain_inb has 4 elements (indices 0-3) for 4 corners
                                            # px and py have 5 elements (indices 0-4), but we use indices 0-3 for corners
                                            for k in range(in2out_gridbox[seg_index], 4):
                                                # MATLAB: domain_inb(k+1) where k is 1-4 (edge index), so k+1 is 2-5
                                                # But in MATLAB, domain_inb has 5 elements (for 5 px/py points)
                                                # In Python, we only check 4 corners, so domain_inb has 4 elements
                                                # Edge index k (0-3) corresponds to corner index k (0-3)
                                                if k < len(domain_inb) and domain_inb[k] and crnr_acc[k] == 0:
                                                    bound_x_seg.append(px[k])
                                                    bound_y_seg.append(py[k])
                                                    crnr_acc[k] = 1
                                                    ending_edge = k
                                                else:
                                                    close_bound = True
                                                    break
                                            
                                            if not close_bound:
                                                # MATLAB: for k = 1:(in2out_gridbox(seg_index)-1)
                                                # In Python, k goes from 0 to in2out_gridbox[seg_index]-1
                                                for k in range(in2out_gridbox[seg_index]):
                                                    if k < len(domain_inb) and domain_inb[k] and crnr_acc[k] == 0:
                                                        bound_x_seg.append(px[k])
                                                        bound_y_seg.append(py[k])
                                                        crnr_acc[k] = 1
                                                        ending_edge = k
                                                    else:
                                                        close_bound = True
                                                        break
                                                if not close_bound:
                                                    close_bound = True
                                        else:
                                            # Find next closest segment
                                            curr_seg = seg_index
                                            kstart = in2out_gridbox[curr_seg]
                                            start_dist = in2out_gridboxdist[curr_seg]
                                            min_pos = -1
                                            min_val = min_val_ori
                                            
                                            # Check all segments for next connection (MATLAB logic)
                                            for k1 in range(in2out_count):
                                                if (out2in_gridboxdist[k1] - start_dist) > eps and \
                                                   (out2in_gridboxdist[k1] - start_dist) < min_val:
                                                    min_pos = k1
                                                    min_val = out2in_gridboxdist[k1] - start_dist
                                            
                                            if min_pos < 0:
                                                # If no segment found going forward, check all out2in
                                                for k1 in range(out2in_count):
                                                    if out2in_gridboxdist[k1] < min_val:
                                                        min_pos = k1
                                                        min_val = out2in_gridboxdist[k1]
                                            
                                            if min_pos >= 0:
                                                if subseg_acc[min_pos] == 1:
                                                    close_bound = True
                                                    ending_edge = in2out_gridbox[curr_seg]
                                                else:
                                                    kend = out2in_gridbox[min_pos]
                                                    x_mid = []
                                                    y_mid = []
                                                    
                                                    # Add grid corners between segments if needed
                                                    # MATLAB: if (kstart ~= kend)
                                                    # kstart and kend are edge indices (0-3 in Python, 1-4 in MATLAB)
                                                    # MATLAB: domain_inb(k1+1) where k1 is edge index (1-4), so k1+1 is 2-5
                                                    # In Python, edge index k1 (0-3) corresponds to domain_inb[k1+1] (1-4)
                                                    if kstart != kend:
                                                        if kend > kstart:
                                                            # MATLAB: for k1 = kstart:(kend-1)
                                                            # In Python, k1 goes from kstart to kend-1 (edge indices)
                                                            # Corner indices are k1+1, so from kstart+1 to kend
                                                            for k1 in range(kstart, kend):
                                                                corner_idx = k1 + 1
                                                                if corner_idx < len(domain_inb) and domain_inb[corner_idx] and crnr_acc[corner_idx] == 0:
                                                                    x_mid.append(px[corner_idx])
                                                                    y_mid.append(py[corner_idx])
                                                                    crnr_acc[corner_idx] = 1
                                                        else:
                                                            # MATLAB: for k1 = kstart:4
                                                            for k1 in range(kstart, 4):
                                                                corner_idx = k1 + 1
                                                                if corner_idx < len(domain_inb) and domain_inb[corner_idx] and crnr_acc[corner_idx] == 0:
                                                                    x_mid.append(px[corner_idx])
                                                                    y_mid.append(py[corner_idx])
                                                                    crnr_acc[corner_idx] = 1
                                                            # MATLAB: for k1 = 1:(kend-1)
                                                            for k1 in range(kend):
                                                                corner_idx = k1 + 1
                                                                if corner_idx < len(domain_inb) and domain_inb[corner_idx] and crnr_acc[corner_idx] == 0:
                                                                    x_mid.append(px[corner_idx])
                                                                    y_mid.append(py[corner_idx])
                                                                    crnr_acc[corner_idx] = 1
                                                    
                                                    if len(x_mid) > 0:
                                                        bound_x_seg.extend(x_mid)
                                                        bound_y_seg.extend(y_mid)
                                                    
                                                    # Add next segment's boundary points
                                                    if not np.isnan(out2in_xcross[min_pos]):
                                                        bound_x_seg.append(out2in_xcross[min_pos])
                                                        bound_y_seg.append(out2in_ycross[min_pos])
                                                    
                                                    if (out2in[min_pos] + 1) <= in2out[min_pos]:
                                                        bound_x_seg.extend(bound_x[out2in[min_pos] + 1:in2out[min_pos] + 1])
                                                        bound_y_seg.extend(bound_y[out2in[min_pos] + 1:in2out[min_pos] + 1])
                                                    else:
                                                        bound_x_seg.extend(bound_x[out2in[min_pos] + 1:])
                                                        bound_x_seg.extend(bound_x[1:in2out[min_pos] + 1])
                                                        bound_y_seg.extend(bound_y[out2in[min_pos] + 1:])
                                                        bound_y_seg.extend(bound_y[1:in2out[min_pos] + 1])
                                                    
                                                    if not np.isnan(in2out_xcross[min_pos]):
                                                        bound_x_seg.append(in2out_xcross[min_pos])
                                                        bound_y_seg.append(in2out_ycross[min_pos])
                                                    
                                                    subseg_acc[min_pos] = 1
                                                    ending_edge = in2out_gridbox[min_pos]
                                                    seg_index = min_pos
                                            else:
                                                close_bound = True
                                    
                                    # Close the boundary by adding grid corners if needed
                                    # MATLAB: if (ending_edge ~= starting_edge)
                                    # ending_edge and starting_edge are edge indices (0-3 in Python, 1-4 in MATLAB)
                                    # MATLAB: domain_inb(k+1) where k is edge index (1-4), so k+1 is 2-5
                                    # In Python, edge index k (0-3) corresponds to domain_inb[k+1] (1-4)
                                    if ending_edge != starting_edge:
                                        if ending_edge < starting_edge:
                                            # MATLAB: for k = ending_edge:(starting_edge-1)
                                            # In Python, k goes from ending_edge to starting_edge-1 (edge indices)
                                            # Corner indices are k+1, so from ending_edge+1 to starting_edge
                                            for k in range(ending_edge, starting_edge):
                                                corner_idx = k + 1
                                                if corner_idx < len(domain_inb) and crnr_acc[corner_idx] == 0 and domain_inb[corner_idx]:
                                                    bound_x_seg.append(px[corner_idx])
                                                    bound_y_seg.append(py[corner_idx])
                                                    crnr_acc[corner_idx] = 1
                                        else:
                                            # MATLAB: for k = ending_edge:4
                                            for k in range(ending_edge, 4):
                                                corner_idx = k + 1
                                                if corner_idx < len(domain_inb) and crnr_acc[corner_idx] == 0 and domain_inb[corner_idx]:
                                                    bound_x_seg.append(px[corner_idx])
                                                    bound_y_seg.append(py[corner_idx])
                                                    crnr_acc[corner_idx] = 1
                                            # MATLAB: for k = 1:(starting_edge-1)
                                            for k in range(starting_edge):
                                                corner_idx = k + 1
                                                if corner_idx < len(domain_inb) and crnr_acc[corner_idx] == 0 and domain_inb[corner_idx]:
                                                    bound_x_seg.append(px[corner_idx])
                                                    bound_y_seg.append(py[corner_idx])
                                                    crnr_acc[corner_idx] = 1
                                    
                                    # Close the polygon
                                    if len(bound_x_seg) > 0:
                                        bound_x_seg.append(bound_x_seg[0])
                                        bound_y_seg.append(bound_y_seg[0])
                                        
                                        bound_dict = {
                                            'x': np.array(bound_x_seg),
                                            'y': np.array(bound_y_seg),
                                            'n': len(bound_x_seg),
                                            'west': np.min(bound_x_seg),
                                            'east': np.max(bound_x_seg),
                                            'north': np.max(bound_y_seg),
                                            'south': np.min(bound_y_seg),
                                            'height': np.max(bound_y_seg) - np.min(bound_y_seg),
                                            'width': np.max(bound_x_seg) - np.min(bound_x_seg),
                                            'level': lev1
                                        }
                                        bound_ingrid.append(bound_dict)
                                        in_coord += 1
                    
                    else:  # boundary lies completely inside the grid
                        # Add the boundary to the list
                        # Handle x and y which might be arrays
                        bound_x_full_raw = bound[i]['x']
                        bound_y_full_raw = bound[i]['y']
                        
                        # Use the same extraction function
                        def extract_array(data):
                            """Recursively extract array from nested structures"""
                            if isinstance(data, np.ndarray):
                                # If it's an object array, extract the first element
                                if data.dtype == object:
                                    if data.size > 0:
                                        first_elem = data.flat[0]
                                        # Recursively extract if still nested
                                        return extract_array(first_elem)
                                    else:
                                        return np.array([])
                                # Flatten multi-dimensional arrays
                                elif data.ndim > 1:
                                    return data.flatten()
                                else:
                                    return data.copy()
                            else:
                                return np.array(data).flatten()
                        
                        bound_x_full = extract_array(bound_x_full_raw)
                        bound_y_full = extract_array(bound_y_full_raw)
                        
                        # Get n value - ensure it's a scalar integer
                        n_val = bound[i]['n']
                        if isinstance(n_val, np.ndarray):
                            n_val = int(n_val.item() if n_val.size == 1 else n_val.flat[0])
                        else:
                            n_val = int(n_val)
                        
                        bound_dict = {
                            'x': bound_x_full,
                            'y': bound_y_full,
                            'n': n_val,
                            'east': east_val,
                            'west': west_val,
                            'north': north_val,
                            'south': south_val,
                            'height': north_val - south_val,
                            'width': east_val - west_val,
                            'level': lev1
                        }
                        bound_ingrid.append(bound_dict)
                        in_coord += 1
            
        except Exception as e:
            print(f'Error processing boundary {i}: {e}', flush=True)
            print(f'Boundary type: {type(bound[i])}', flush=True)
            if isinstance(bound[i], dict):
                print(f'Boundary keys: {list(bound[i].keys())}', flush=True)
                for key in bound[i].keys():
                    val = bound[i][key]
                    print(f'  {key}: type={type(val)}, shape={getattr(val, "shape", "N/A")}', flush=True)
            import traceback
            traceback.print_exc()
            # Continue to update progress even on error
            itmp = int((idx + 1) / N_candidates * 100) if N_candidates > 0 else 100
            if (itmp % 5 == 0) and (itmp_prev != itmp):
                print(f'Completed {itmp} per cent of {N_candidates} candidate boundaries and found {in_coord} internal boundaries', flush=True)
                import sys
                sys.stdout.flush()
                itmp_prev = itmp
            continue
        
        # Counter to keep tab on the level of processing
        itmp = int((idx + 1) / N_candidates * 100) if N_candidates > 0 else 100
        # Output progress every 5% for any number of candidates (removed N_candidates > 100 restriction)
        # This ensures logs are shown even when called from split_boundary with single boundaries
        if (itmp % 5 == 0) and (itmp_prev != itmp):
            print(f'Completed {itmp} per cent of {N_candidates} candidate boundaries and found {in_coord} internal boundaries', flush=True)
            import sys
            sys.stdout.flush()
            itmp_prev = itmp
    
    Nb = in_coord
    
    if Nb == 0:
        bound_ingrid = [-1]
    
    return bound_ingrid, Nb

