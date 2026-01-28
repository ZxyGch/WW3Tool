% Create namelist for gridgen configuration

% Define the values to put in namelist

bin_dir = '../bin';              % matlab scripts location
ref_dir = '../reference';   % reference data location
data_dir = '../data';            % output grid directory

fname_poly = 'user_polygons.flag';

fname = 'glob_30m';              % file name prefix 
fnameb = 'n/a';                  % file name prefix base grid for boundaries
bound_select = 1;                % method for active boundary selection from
                                 % the base grid

ref_grid = 'etopo2';             % file name prefix digital elevation model                      
xvar='x';                       % name of variable defining longitudes in bathy file
yvar='y';                       % name of variable defining latitudes in bathy file
zvar='z';                       % name of variable defining depths in bathy file
lonfrom = -180; 
TYPE = 'rect';                  
dx = 0.5;
dy = 0.5; 
lon_west = -180;
lon_east = 179.5;
lat_south = -78;
lat_north = 80;
 
IS_GLOBAL = 0;                  % set to 1 if the grid is global, else 0
IS_GLOBALB = 0;                 % set to 1 if the base grid is global, else 0
boundary = 'low';               % Determine which GSHHS .mat file to load
read_boundary = 1;              % flag to determine if input boundary 
                                % information needs to be read ; boundary 
                                % data files can be significantly large 
                                % and need to be read only the first 
                                % time. So when making multiple grids 
                                % the flag can be set to 0 for subsequent 
                                % grids. (Note : If the workspace is
                                % cleared the boundary data will have to 
                                % be read again)
opt_poly = 0;                   % flag for reading the optional user 
                                % defined polygons.
min_dist=12;
 
DRY_VAL = 999999;               % Depth value for dry cells (can change as desired)
CUT_OFF = 0;                    % Cut_off depth to distinguish between dry and wet cells.
                                % All depths below the cut_off depth are marked wet
LIM_BATHY = 0.1;                % Proportion of base bathymetry cells that need to be 
                                % wet for the target cell to be considered wet. 
LIM_VAL = 0.54;                 % Fraction of cell that has to be inside a polygon for 
                                % cell to be marked dry;
SPLIT_LIM = 12.5;
OFFSET = max([dx dy]);          % Additional buffer around the boundary to check if cell 
                                % is crossing boundary. Should be set to largest grid res. 
LAKE_TOL = 100;
OBSTR_OFFSET = 1;               
  
% Create namelist file
fid=fopen('../namelist/test_1m.nml','w');
fprintf(fid,'%s\n','$-------------------------------------------------------------------------$');
fprintf(fid,'%s\n','$');
fprintf(fid,'%s\n','$ Grid namelist for gridgen routine');
fprintf(fid,'%s\n','$');
fprintf(fid,'%s\n','$-------------------------------------------------------------------------$');
fprintf(fid,'\n%s\n\n','$  Initialize parameters');
fprintf(fid,'%s\n','');
fprintf(fid,'%s\n','');
fprintf(fid,'%s\n\n','$ a. Path to directories and file names');
fprintf(fid,'%s\n','&GRID_INIT');
write_namelist_str(fid,'BIN_DIR',bin_dir);
write_namelist_str(fid,'REF_DIR',ref_dir);
write_namelist_str(fid,'DATA_DIR',data_dir);
write_namelist_str(fid,'FNAME_POLY',fname_poly);
write_namelist_str(fid,'FNAME',fname);
write_namelist_str(fid,'FNAMEB',fnameb);
write_namelist_int(fid,'BOUND_SELECT',bound_select);
fprintf(fid,'%s\n\n','/');
fprintf(fid,'%s\n\n','$ b. Information on bathymetry file');
fprintf(fid,'%s\n','&BATHY_FILE');
write_namelist_str(fid,'REF_GRID',ref_grid);
write_namelist_str(fid,'XVAR',xvar);
write_namelist_str(fid,'YVAR',yvar);
write_namelist_str(fid,'ZVAR',zvar);
write_namelist_flt(fid,'LONFROM',lonfrom);
fprintf(fid,'%s\n\n','/');
fprintf(fid,'%s\n\n','$ c. Required grid resolution and boundaries');
fprintf(fid,'%s\n','&OUTGRID');
write_namelist_flt(fid,'TYPE',type);
write_namelist_flt(fid,'DX',dx);
write_namelist_flt(fid,'DY',dy);
write_namelist_flt(fid,'LON_WEST',lon_west);
write_namelist_flt(fid,'LON_EAST',lon_east);
write_namelist_flt(fid,'LAT_SOUTH',lat_south);
write_namelist_flt(fid,'LAT_NORTH',lat_north);
write_namelist_int(fid,'IS_GLOBAL',IS_GLOBAL);
write_namelist_int(fid,'IS_GLOBALB',IS_GLOBALB);
fprintf(fid,'%s\n\n','/');
fprintf(fid,'%s\n\n','$ d. Boundary options');
fprintf(fid,'%s\n','&GRID_BOUND');
write_namelist_str(fid,'BOUNDARY',boundary);
write_namelist_int(fid,'READ_BOUNDARY',read_boundary);
write_namelist_int(fid,'OPT_POLY',opt_poly);
write_namelist_int(fid,'MIN_DIST',min_dist);
fprintf(fid,'%s\n\n','/');
fprintf(fid,'%s\n\n','$ e. Parameter values used in the software');
fprintf(fid,'%s\n','&GRID_PARAM');
write_namelist_int(fid,'DRY_VAL',DRY_VAL);
write_namelist_flt(fid,'CUT_OFF',CUT_OFF);
write_namelist_flt(fid,'LIM_BATHY',LIM_BATHY);
write_namelist_flt(fid,'LIM_VAL',LIM_VAL);
write_namelist_flt(fid,'SPLIT_LIM',SPLIT_LIM);
write_namelist_flt(fid,'OFFSET',OFFSET);
write_namelist_flt(fid,'LAKE_TOL',LAKE_TOL);
write_namelist_flt(fid,'OBSTR_OFFSET',OBSTR_OFFSET);
fprintf(fid,'%s\n\n','/');
fclose(fid);
