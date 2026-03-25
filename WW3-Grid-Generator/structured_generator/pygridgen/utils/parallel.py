"""
Parallel Processing Utilities

Provides parallel processing capabilities for gridgen operations.
"""

import multiprocessing as mp

import numpy as np


def get_num_workers():
    """Get optimal number of worker processes."""
    return max(1, mp.cpu_count() - 1)


def chunk_list(lst, n_chunks):
    """Split a list into n chunks."""
    chunk_size = max(1, len(lst) // n_chunks)
    chunks = []
    for i in range(0, len(lst), chunk_size):
        chunks.append((i, lst[i:i + chunk_size]))
    return chunks


def process_boundary_chunk(args):
    """
    Process a chunk of boundaries for compute_boundary.
    
    This function is designed to be called by multiprocessing.Pool.map().
    """
    from matplotlib.path import Path
    
    (chunk_start, chunk, coord, bflg, eps, MAX_SEG_LENGTH,
     px, py, m_grid, c_grid, box_length, norm) = args
    
    lat_start, lon_start, lat_end, lon_end = coord
    
    bound_ingrid = []
    in_coord = 0
    
    for idx, boundary in enumerate(chunk):
        try:
            # Limit boundaries to coastal type only
            level_val = boundary.get('level', 0)
            if isinstance(level_val, np.ndarray):
                level_val = float(level_val.item()) if level_val.size == 1 else float(level_val.flat[0])
            elif isinstance(level_val, (list, tuple)):
                level_val = float(level_val[0]) if len(level_val) > 0 else 0
            else:
                level_val = float(level_val)
            
            if level_val != bflg and level_val != 2:
                continue
            
            # Get boundary extent
            west_val = boundary.get('west', 0)
            east_val = boundary.get('east', 0)
            south_val = boundary.get('south', 0)
            north_val = boundary.get('north', 0)
            
            for val_name in ['west_val', 'east_val', 'south_val', 'north_val']:
                val = locals()[val_name]
                if isinstance(val, np.ndarray):
                    locals()[val_name] = val.item() if val.size == 1 else val[0]
            
            west_val = float(west_val.item() if isinstance(west_val, np.ndarray) else west_val)
            east_val = float(east_val.item() if isinstance(east_val, np.ndarray) else east_val)
            south_val = float(south_val.item() if isinstance(south_val, np.ndarray) else south_val)
            north_val = float(north_val.item() if isinstance(north_val, np.ndarray) else north_val)
            
            # Check if boundary is in grid domain
            if (west_val > lon_end or east_val < lon_start or
                    south_val > lat_end or north_val < lat_start):
                continue  # Outside grid
            
            # Check if completely inside grid
            inside_grid = (west_val >= lon_start and east_val <= lon_end and
                          south_val >= lat_start and north_val <= lat_end)
            
            lev1 = level_val
            
            # Extract boundary coordinates
            def extract_array(data):
                if isinstance(data, np.ndarray):
                    if data.dtype == object and data.size > 0:
                        return extract_array(data.flat[0])
                    return data.flatten()
                elif isinstance(data, (list, tuple)):
                    return np.array(data).flatten()
                return np.array([data])
            
            bound_x = extract_array(boundary.get('x', []))
            bound_y = extract_array(boundary.get('y', []))
            
            if len(bound_x) == 0 or len(bound_y) == 0:
                continue
            
            n_val = int(boundary.get('n', len(bound_x)))
            if isinstance(n_val, np.ndarray):
                n_val = int(n_val.item() if n_val.size == 1 else n_val[0])
            
            if inside_grid:
                # Boundary is completely inside, add directly
                bound_dict = {
                    'x': bound_x,
                    'y': bound_y,
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
            else:
                # Boundary crosses domain, need to clip
                # Simplified: just check if any points are inside
                bbox_path = Path(np.column_stack([px[:-1], py[:-1]]))
                points = np.column_stack([bound_x, bound_y])
                in_points = bbox_path.contains_points(points, radius=1e-6)
                
                if np.any(in_points):
                    # At least some points inside, add the boundary
                    # (Full clipping logic would go here, but for performance
                    # we just add the whole boundary and let later stages handle it)
                    bound_dict = {
                        'x': bound_x,
                        'y': bound_y,
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
            continue
    
    return bound_ingrid, in_coord

