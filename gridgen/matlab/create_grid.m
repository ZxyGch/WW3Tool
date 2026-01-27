function create_grid(varargin)

% -------------------------------------------------------------------------
%|                                                                        |
%|                    +----------------------------+                      |
%|                    | GRIDGEN          NOAA/NCEP |                      |
%|                    |                            |                      |
%|                    | Last Update :  2024        |                      |
%|                    +----------------------------+                      |
%|                     Distributed with WAVEWATCH III                     |
%|                                                                        |
%|                 Copyright 2009 National Weather Service (NWS),         |
%|  National Oceanic and Atmospheric Administration.  All rights reserved.|
%|                                                                        |
%| DESCRIPTION                                                            |
%| Create a grid for WAVEWATCH III based on a rectilinear grid            |
%|                                                                        |
%| create_grid()                                                          |
%|   or                                                                   |
%| create_grid('param1', value1, 'param2', value2, ...)                 |
%|                                                                        |
%| INPUT (optional name-value pairs)                                     |
%|  bin_dir      : Path to matlab directory (default: '../matlab/')      |
%|  ref_dir      : Path to reference data directory (default: '../reference_data/')|
%|  out_dir      : Path to output directory (default: '../result/')      |
%|  fname        : Output file name prefix (default: 'grid')              |
%|  dx           : Grid resolution in longitude (degrees) (default: 0.05) |
%|  dy           : Grid resolution in latitude (degrees) (default: 0.05) |
%|  lon_range    : [lon_west, lon_east] (default: [110, 130])          |
%|  lat_range    : [lat_south, lat_north] (default: [10, 30])           |
%|  ref_grid     : Bathymetry source ('etopo1', 'etopo2', 'gebco')      |
%|                 (default: 'gebco')                                    |
%|  boundary     : GSHHS boundary level ('full','high','inter','low','coarse')|
%|                 (default: 'full')                                      |
%|  read_boundary: Read boundary data? (default: 1)                      |
%|  opt_poly     : Use optional polygons? (default: 0)                   |
%|  fname_poly   : Optional polygon file name (default: 'user_polygons.flag')|
%|  DRY_VAL      : Depth value for dry cells (default: 999999)           |
%|  CUT_OFF      : Cut-off depth to distinguish wet/dry (default: 0.1)  |
%|  LIM_BATHY    : Fraction of cell that must be wet (default: 0.1)     |
%|  LIM_VAL      : Fraction for polygon masking (default: 0.5)          |
%|  OFFSET       : Buffer around boundary (default: max(dx,dy))          |
%|  LAKE_TOL     : Lake removal tolerance (default: -1)                  |
%|  IS_GLOBAL    : Is global grid? (default: 0)                         |
%|  OBSTR_OFFSET : Obstruction offset (default: 1)                      |
%|  SPLIT_LIM    : Limit for splitting polygons (default: 5*max(dx,dy))|
%|  show_plots   : Show visualization plots? (default: 1)                |
% -------------------------------------------------------------------------

% 0. Parse input arguments
% Get the base directory (where this script is located)
script_path = mfilename('fullpath');
if isempty(script_path)
    script_path = which(mfilename);
end
[base_dir, ~, ~] = fileparts(script_path);
if isempty(base_dir)
    base_dir = pwd;
end
% If we're in matlab/ directory, go up one level to get project root
if strcmp(base_dir(end), filesep)
    base_dir = base_dir(1:end-1);  % Remove trailing separator
end
[parent_dir, base_name] = fileparts(base_dir);
if strcmp(base_name, 'matlab')
    project_root = parent_dir;
else
    project_root = base_dir;
end

p = inputParser;
addParameter(p, 'bin_dir', fullfile(project_root, 'matlab'), @ischar);
addParameter(p, 'ref_dir', fullfile(project_root, 'reference_data'), @ischar);
addParameter(p, 'out_dir', fullfile(project_root, 'result'), @ischar);
addParameter(p, 'fname', 'grid', @ischar);
addParameter(p, 'dx', 0.05, @isnumeric);
addParameter(p, 'dy', 0.05, @isnumeric);
addParameter(p, 'lon_range', [110, 130], @isnumeric);
addParameter(p, 'lat_range', [10, 30], @isnumeric);
addParameter(p, 'ref_grid', 'gebco', @ischar);
addParameter(p, 'boundary', 'full', @ischar);
addParameter(p, 'read_boundary', 1, @isnumeric);
addParameter(p, 'opt_poly', 0, @isnumeric);
addParameter(p, 'fname_poly', 'user_polygons.flag', @ischar);
addParameter(p, 'DRY_VAL', 999999, @isnumeric);
addParameter(p, 'CUT_OFF', 0.1, @isnumeric);
addParameter(p, 'LIM_BATHY', 0.1, @isnumeric);
addParameter(p, 'LIM_VAL', 0.5, @isnumeric);
addParameter(p, 'OFFSET', [], @isnumeric);  % Will be set to max(dx,dy) if empty
addParameter(p, 'LAKE_TOL', -1, @isnumeric);
addParameter(p, 'IS_GLOBAL', 0, @isnumeric);
addParameter(p, 'OBSTR_OFFSET', 1, @isnumeric);
addParameter(p, 'SPLIT_LIM', [], @isnumeric);  % Will be set to 5*max(dx,dy) if empty
addParameter(p, 'show_plots', 1, @isnumeric);

parse(p, varargin{:});
params = p.Results;

% Set default values for computed parameters
if isempty(params.OFFSET)
    params.OFFSET = max([params.dx, params.dy]);
end
if isempty(params.SPLIT_LIM)
    params.SPLIT_LIM = 5 * max([params.dx, params.dy]);
end

% 0. Initialization
tic;
fprintf('===============================================================================\n');
title_str = 'WAVEWATCH III Grid Generator Matlab Version';
title_len = length(title_str);
padding = 70 - title_len;
fprintf('%s%s\n', repmat(' ', 1, padding), title_str);
fprintf('===============================================================================\n');
fprintf('Grid name: %s\n', params.fname);
fprintf('Bathymetry source: %s\n', params.ref_grid);
fprintf('Resolution: %.4f x %.4f degrees\n', params.dx, params.dy);
fprintf('Domain: [%.2f, %.2f] x [%.2f, %.2f]\n', ...
    params.lon_range(1), params.lon_range(2), ...
    params.lat_range(1), params.lat_range(2));
fprintf('===============================================================================\n\n');

% Add matlab directory to path
if exist(params.bin_dir, 'dir') == 7
    addpath(params.bin_dir, '-end');
else
    error('Matlab directory not found: %s', params.bin_dir);
end

% Create output directory if it doesn't exist
if exist(params.out_dir, 'dir') ~= 7
    mkdir(params.out_dir);
    fprintf('Created output directory: %s\n', params.out_dir);
end

% 1. Define grid coordinates
fprintf('Step 1: Defining grid coordinates...\n');
lon1d = params.lon_range(1):params.dx:params.lon_range(2);
lat1d = params.lat_range(1):params.dy:params.lat_range(2);
[lon, lat] = meshgrid(lon1d, lat1d);
fprintf('  Grid size: %d x %d points\n', size(lon, 2), size(lon, 1));
fprintf('  Done.\n\n');

% 2. Read boundary data
if params.read_boundary
    fprintf('Step 2: Reading GSHHS boundary data...\n');
    boundary_file = fullfile(params.ref_dir, ['coastal_bound_', params.boundary, '.mat']);
    if exist(boundary_file, 'file') == 2
        load(boundary_file);
        N = length(bound);
        fprintf('  Loaded %d boundary polygons\n', N);
        
        % Load optional polygons if requested
        Nu = 0;
        if params.opt_poly == 1
            fname_poly = fullfile(params.ref_dir, params.fname_poly);
            if exist(fname_poly, 'file') == 2
                [bound_user, Nu] = optional_bound(params.ref_dir, params.fname_poly);
                if Nu > 0
                    fprintf('  Loaded %d user-defined polygons\n', Nu);
                else
                    params.opt_poly = 0;
                end
            else
                fprintf('  Warning: Optional polygon file not found: %s\n', fname_poly);
                params.opt_poly = 0;
            end
        end
    else
        fprintf('  Warning: Boundary file not found: %s\n', boundary_file);
        fprintf('  Continuing without boundary data...\n');
        params.read_boundary = 0;
    end
    fprintf('  Done.\n\n');
else
    fprintf('Step 2: Skipping boundary data (read_boundary = 0)\n\n');
end

% 3. Generate bathymetry
fprintf('Step 3: Generating bathymetry from %s...\n', params.ref_grid);
fprintf('  This may take a while...\n');
try
    % generate_grid(x, y, ref_dir, bathy_source, limit, cut_off, dry)
    depth = generate_grid(lon, lat, params.ref_dir, params.ref_grid, ...
        params.LIM_BATHY, params.CUT_OFF, params.DRY_VAL);
    fprintf('  Done.\n\n');
catch ME
    fprintf('  ERROR: Failed to generate bathymetry\n');
    fprintf('  Error message: %s\n', ME.message);
    rethrow(ME);
end

% 4. Compute boundaries within grid
if params.read_boundary
    fprintf('Step 4: Computing boundaries within grid domain...\n');
    lon_start = min(lon(:)) - params.dx;
    lon_end = max(lon(:)) + params.dx;
    lat_start = min(lat(:)) - params.dy;
    lat_end = max(lat(:)) + params.dy;
    
    coord = [lat_start, lon_start, lat_end, lon_end];
    [b, N1] = compute_boundary(coord, bound);
    fprintf('  Found %d boundary segments in grid domain\n', N1);
    fprintf('  Done.\n\n');
else
    b = [];
    N1 = 0;
    fprintf('Step 4: Skipping boundary computation\n\n');
end

% 5. Create initial land-sea mask
fprintf('Step 5: Creating initial land-sea mask...\n');
m = ones(size(depth));
m(depth == params.DRY_VAL) = 0;
fprintf('  Initial wet cells: %d\n', sum(m(:) == 1));
fprintf('  Initial dry cells: %d\n', sum(m(:) == 0));
fprintf('  Done.\n\n');

% 6. Split large boundary polygons (for efficiency)
if params.read_boundary && N1 > 0
    fprintf('Step 6: Splitting large boundary polygons...\n');
    b_split = split_boundary(b, params.SPLIT_LIM);
    fprintf('  Done.\n\n');
else
    b_split = b;
    fprintf('Step 6: Skipping boundary splitting\n\n');
end

% 7. Clean mask using boundary polygons
if params.read_boundary && N1 > 0
    fprintf('Step 7: Cleaning mask using boundary polygons...\n');
    m2 = clean_mask(lon, lat, m, b_split, params.LIM_VAL, params.OFFSET);
    fprintf('  Wet cells after cleaning: %d\n', sum(m2(:) == 1));
    fprintf('  Dry cells after cleaning: %d\n', sum(m2(:) == 0));
    fprintf('  Done.\n\n');
else
    m2 = m;
    fprintf('Step 7: Skipping mask cleaning (no boundaries)\n\n');
end

% 8. Remove lakes and small water bodies
fprintf('Step 8: Removing lakes and small water bodies...\n');
[m4, mask_map] = remove_lake(m2, params.LAKE_TOL, params.IS_GLOBAL);
fprintf('  Final wet cells: %d\n', sum(m4(:) == 1));
fprintf('  Final dry cells: %d\n', sum(m4(:) == 0));
fprintf('  Done.\n\n');

% 9. Create obstruction grids
if params.read_boundary && N1 > 0
    fprintf('Step 9: Creating obstruction grids...\n');
    [sx1, sy1] = create_obstr(lon, lat, b, m4, params.OBSTR_OFFSET, params.OBSTR_OFFSET);
    fprintf('  Done.\n\n');
else
    fprintf('Step 9: Skipping obstruction grid creation (no boundaries)\n');
    sx1 = zeros(size(m4));
    sy1 = zeros(size(m4));
    fprintf('  Done.\n\n');
end

% 10. Write output files
fprintf('Step 10: Writing WAVEWATCH III output files...\n');
depth_scale = 1000;
obstr_scale = 100;

% Write bathymetry file
d = round(depth * depth_scale);
write_ww3file(fullfile(params.out_dir, [params.fname, '.bot']), d);
fprintf('  Written: %s.bot\n', params.fname);

% Write mask file
write_ww3file(fullfile(params.out_dir, [params.fname, '.mask']), m4);
fprintf('  Written: %s.mask\n', params.fname);

% Write obstruction file
% Always write obstruction file, even if no boundaries (write zeros)
% This ensures WAVEWATCH III has the required file
d1 = round(sx1 * obstr_scale);
d2 = round(sy1 * obstr_scale);
write_ww3obstr(fullfile(params.out_dir, [params.fname, '.obst']), d1, d2);
if params.read_boundary && N1 > 0
    fprintf('  Written: %s.obst (with obstructions)\n', params.fname);
else
    fprintf('  Written: %s.obst (no obstructions, all zeros)\n', params.fname);
end

% Write metadata file
write_ww3meta(fullfile(params.out_dir, params.fname), 'RECT', lon, lat, ...
    1/depth_scale, 1/obstr_scale, 1.0);
fprintf('  Written: %s.meta\n', params.fname);
fprintf('  Done.\n\n');

% 11. Visualization (optional)
if params.show_plots
    fprintf('Step 11: Creating visualization plots...\n');
    set(groot, 'DefaultFigureColormap', jet);
    
    % Figure 1: Bathymetry
    figure(1); clf;
    loc = m4 == 0;
    d2 = depth;
    d2(loc) = NaN;
    pcolor(lon, lat, d2);
    shading interp;
    colorbar;
    title(sprintf('Bathymetry (%s)', params.ref_grid));
    xlabel('Longitude');
    ylabel('Latitude');
    axis equal;
    
    % Figure 2: Land-sea mask
    figure(2); clf;
    pcolor(lon, lat, m4);
    shading flat;
    colorbar;
    title('Final Land-Sea Mask');
    xlabel('Longitude');
    ylabel('Latitude');
    axis equal;
    
    % Figure 3: X-direction obstruction
    if params.read_boundary && N1 > 0
        figure(3); clf;
        d2 = sx1;
        d2(loc) = NaN;
        pcolor(lon, lat, d2);
        shading flat;
        colorbar;
        title('Sx Obstruction');
        xlabel('Longitude');
        ylabel('Latitude');
        axis equal;
        
        % Figure 4: Y-direction obstruction
        figure(4); clf;
        d2 = sy1;
        d2(loc) = NaN;
        pcolor(lon, lat, d2);
        shading flat;
        colorbar;
        title('Sy Obstruction');
        xlabel('Longitude');
        ylabel('Latitude');
        axis equal;
    end
    
    fprintf('  Done.\n\n');
end

% Summary
elapsed_time = toc;
fprintf('===============================================================================\n');
fprintf('                          Grid Generation Complete!\n');
fprintf('===============================================================================\n');
fprintf('Output directory: %s\n', params.out_dir);
fprintf('Output files:\n');
fprintf('  - %s.bot  (bathymetry)\n', params.fname);
fprintf('  - %s.mask (land-sea mask)\n', params.fname);
fprintf('  - %s.obst (obstructions', params.fname);
if params.read_boundary && N1 > 0
    fprintf(')\n');
else
    fprintf(', all zeros - no boundaries in domain)\n');
end
fprintf('  - %s.meta (metadata)\n', params.fname);
fprintf('Total time: %.2f seconds\n', elapsed_time);
fprintf('==============================================================================\n');

end

