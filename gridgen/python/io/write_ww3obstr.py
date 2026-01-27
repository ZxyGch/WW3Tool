"""
Write WAVEWATCH III obstruction file.

Write the output obstruction arrays into ASCII file format.
"""

import os


def write_ww3obstr(fname, d1, d2):
    """
    Write obstruction arrays to WAVEWATCH III format file.
    
    Parameters
    ----------
    fname : str
        Output file name
    d1 : ndarray
        2D array with x obstruction data
    d2 : ndarray
        2D array with y obstruction data
    
    Returns
    -------
    messg : str
        Error message (empty if successful)
    errno : int
        Error number (0 if successful)
    """
    messg = ""
    errno = 0
    
    try:
        Ny, Nx = d1.shape
        
        # Ensure output directory exists
        output_dir = os.path.dirname(fname)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        with open(fname, 'w') as fid:
            # Write d1 (x obstruction)
            for i in range(Ny):
                a = d1[i, :]
                # MATLAB fprintf(fid,' %d ',a) outputs each element with spaces before and after
                line = ' '.join(f' {int(val)} ' for val in a) + '\n'
                fid.write(line)
            
            # Write blank line separator
            fid.write('\n')
            
            # Write d2 (y obstruction)
            for i in range(Ny):
                a = d2[i, :]
                # MATLAB fprintf(fid,' %d ',a) outputs each element with spaces before and after
                line = ' '.join(f' {int(val)} ' for val in a) + '\n'
                fid.write(line)
        
    except Exception as e:
        messg = f"Cannot open file: {fname}\nError: {str(e)}"
        errno = -1
        print(f'!!ERROR!!: {messg}')
    
    return messg, errno

