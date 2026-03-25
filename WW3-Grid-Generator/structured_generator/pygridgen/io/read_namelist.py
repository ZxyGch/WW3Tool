"""
Read FORTRAN namelist file.

This module reads FORTRAN input namelist and returns the values as a dictionary.
"""

import re


def read_namelist(filename, namelist):
    """
    Read FORTRAN namelist and return values as dictionary.
    
    Parameters
    ----------
    filename : str or file
        Input namelist file name or file object
    namelist : str
        Name of the namelist section to read (e.g., 'GRID_INIT')
    
    Returns
    -------
    data : dict
        Dictionary containing namelist variables as keys
    """
    # Open file if filename is string
    if isinstance(filename, str):
        fid = open(filename, 'r')
        close_file = True
    else:
        fid = filename
        close_file = False
    
    try:
        # Find the namelist section
        line = fid.readline()
        while line and namelist not in line:
            line = fid.readline()
        
        if not line:
            raise ValueError(f'Namelist: {namelist} not found!')
        
        # Read the namelist content
        total_line = []
        line = fid.readline()
        while line:
            line = line.strip()
            # Check for end of namelist
            if line.startswith('/') or line.upper().startswith('&END') or line.upper().startswith('$END'):
                break
            
            # Remove comments
            if '!' in line:
                comment_pos = line.find('!')
                if comment_pos == 0:
                    line = ''
                else:
                    line = line[:comment_pos].strip()
            
            if len(line) > 1:
                total_line.append(' ' + line)
            
            line = fid.readline()
            # Skip blank lines
            while line and not line.strip():
                line = fid.readline()
        
        # Join all lines
        total_line = ''.join(total_line)
        
        # Replace common FORTRAN boolean values
        total_line = re.sub(r'\bT\b', '1', total_line, flags=re.IGNORECASE)
        total_line = re.sub(r'\bF\b', '0', total_line, flags=re.IGNORECASE)
        total_line = re.sub(r'\.true\.', '1', total_line, flags=re.IGNORECASE)
        total_line = re.sub(r'\.false\.', '0', total_line, flags=re.IGNORECASE)
        total_line = total_line.replace(',', ' ')
        
        # Parse variable assignments
        # Pattern: variable_name = value(s)
        pattern = r'([a-zA-Z0-9_]+)\s*=\s*([^=]+?)(?=\s+[a-zA-Z0-9_]+\s*=|$)'
        matches = re.findall(pattern, total_line)
        
        data = {}
        for var_name, value_str in matches:
            var_name = var_name.lower().strip()
            value_str = value_str.strip()
            
            # Remove quotes from strings
            if value_str.startswith("'") and value_str.endswith("'"):
                value = value_str[1:-1]
            else:
                # Try to parse as numbers
                try:
                    # Handle multiple values (arrays)
                    values = value_str.split()
                    if len(values) == 1:
                        value = float(values[0])
                        if value.is_integer():
                            value = int(value)
                    else:
                        value = []
                        for v in values:
                            try:
                                fv = float(v)
                                if fv.is_integer():
                                    value.append(int(fv))
                                else:
                                    value.append(fv)
                            except ValueError:
                                value.append(v)
                        # Convert to numpy array if all numeric
                        if all(isinstance(v, (int, float)) for v in value):
                            import numpy as np
                            value = np.array(value)
                except (ValueError, AttributeError):
                    value = value_str
            
            data[var_name] = value
        
        return data
    
    finally:
        if close_file:
            fid.close()

