"""
Write WAVEWATCH III output file.

Write the output array into ASCII file format.
"""

import os


def write_ww3file(fname, d):
    """
    Write 2D array to WAVEWATCH III format file.
    
    Parameters
    ----------
    fname : str
        Output file name
    d : ndarray
        2D array to write
    
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
        Ny, Nx = d.shape
        
        # Ensure output directory exists
        output_dir = os.path.dirname(fname)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        with open(fname, 'w') as fid:
            for i in range(Ny):
                a = d[i, :]
                # Format as space-separated integers
                # MATLAB fprintf(fid,' %d ',a) outputs each element with spaces before and after
                # For array [1,2,3], MATLAB outputs: ' 1  2  3 '
                line = ' '.join(f' {int(val)} ' for val in a) + '\n'
                fid.write(line)
            # 确保所有数据都写入磁盘（在文件关闭前刷新缓冲区）
            fid.flush()
        
    except Exception as e:
        messg = f"Cannot open file: {fname}\nError: {str(e)}"
        errno = -1
        print(f'!!ERROR!!: {messg}')
    
    return messg, errno

