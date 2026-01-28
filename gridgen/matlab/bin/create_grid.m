function create_grid(fname_nml)

% -------------------------------------------------------------------------
%|                                                                        |
%|                    +----------------------------+                      |
%|                    | GRIDGEN          NOAA/NCEP |                      |
%|                    |                            |                      |
%|                    | Last Update :  18-Jan-2017 |                      |
%|                    +----------------------------+                      |
%|                     Distributed with WAVEWATCH III                     |
%|                                                                        |
%|                 Copyright 2009 National Weather Service (NWS),         |
%|  National Oceanic and Atmospheric Administration.  All rights reserved.|
%|                                                                        |
%| DESCRIPTION                                                            |
%| Create a grid based on a rectilinear digital model elevation           |
%|                                                                        |
%| create_grid(fname_nml)                                                 |
%|                                                                        |
%| INPUT                                                                  |
%|  fname_nml   : Input namelist file name                                |
% -------------------------------------------------------------------------

% 0. Initialization
tic
fprintf('%s\n',fname_nml);
set(groot,'DefaultFigureColormap',jet);
close all;

% Load namelist
init_nml    = read_namelist(fname_nml,'GRID_INIT');
bathy_nml   = read_namelist(fname_nml,'BATHY_FILE');
outgrid_nml = read_namelist(fname_nml,'OUTGRID');
gridbound_nml =  read_namelist(fname_nml,'GRID_BOUND');
gridparam_nml =  read_namelist(fname_nml,'GRID_PARAM');

% Read namelist variables

% 0.a Path to directories and file names
bin_dir = init_nml.bin_dir;     % matlab scripts location
ref_dir = init_nml.ref_dir;     % reference data location
data_dir = init_nml.data_dir;   % output grid directory

fnamep = init_nml.fname_poly;         % file for user-defined polygons
fname_poly = [ref_dir, '/', fnamep];  % complete file name
fname = init_nml.fname;               % file name prefix
fname(fname=='''') = [];
fnamefig = strrep(fname,'_','\_');         % file name for figures

% 0.b Information on bathymetry file

ref_grid = bathy_nml.ref_grid;      % name of reference bathymetry file
lonfrom  = bathy_nml.lonfrom;       % origin of longitudes [ -180 | 0]
xvar     = bathy_nml.xvar;          % variable name for longitudes in file
yvar     = bathy_nml.yvar;          % variable name for latitudes in file
zvar     = bathy_nml.zvar;          % variable name for depths in file

% 0.c Required grid resolution and boundaries
type = outgrid_nml.type;              % grid type 'rect' or 'curv'
dx = outgrid_nml.dx;                  % resolution in longitudes (°)
dy = outgrid_nml.dy;                  % resolution in latitudes (°)

lon_west  = outgrid_nml.lon_west;     % western boundary for grid
lon_east  = outgrid_nml.lon_east;     % eastern boundary for grid
lat_south = outgrid_nml.lat_south;    % southern boundary for grid
lat_north = outgrid_nml.lat_north;    % northern boundary for grid
IS_GLOBAL = outgrid_nml.is_global;    % Set to 1 for global grids

% 0.e Boundary options
boundary = gridbound_nml.boundary;     % Determine which GSHHS .mat file to load
read_boundary = gridbound_nml.read_boundary; % flag: input boundary information to read ?
opt_poly = gridbound_nml.opt_poly;     % flag: user-defined polygons or not
MIN_DIST = gridbound_nml.min_dist;

% 0.f Parameter values used in the software

DRY_VAL = gridparam_nml.dry_val;       % Depth value for dry cells
CUT_OFF = gridparam_nml.cut_off;       % Cut_off depth to distinguish between
% dry and wet cells.
% All depths < CUT_OFF are marked wet
LIM_BATHY = gridparam_nml.lim_bathy;   % Proportion of base bathymetry cells
% that need to be wet for the target cell
% to be considered wet.
AVG = gridparam_nml.avg;               % 2D Averaging method for depth
LIM_VAL = gridparam_nml.lim_val;       % Fraction of cell that has to be inside
% a polygon for cell to be marked dry;
SPLIT_LIM = gridparam_nml.split_lim;   % Limit for splitting the polygons;
% used in split_boundary
OFFSET = gridparam_nml.offset;         % Additional buffer around the boundary
% to check if cell is crossing boundary.
LAKE_TOL = gridparam_nml.lake_tol;     % Tolerance value for 'remove_lake'

OBSTR_OFFSET = gridparam_nml.obstr_offset;
% Flag: neighbours to consider when
% creating obstruction?
% Used in create_obstr

% 0.g Setting the paths for subroutines

addpath(bin_dir,'-end');
fprintf('.........Create grid for %s..................\n',fname);

% Reading input data
if (read_boundary == 1)
    fprintf(1,'.........Reading Boundaries..................\n');
    
    % load in bound structure
    load([ref_dir,'/coastal_bound_',boundary,'.mat']);

    %figure(10);
    j=length(bound);

    % force polygons to be defined between -180 and 180
    for i = 1:length(bound)
        bound(i).x(bound(i).x >= 180) = bound(i).x(bound(i).x >= 180) - 360;
        bound(i).east = max(bound(i).x);
        bound(i).west = min(bound(i).x);
        
        % split polygon if crossing dateline
        if (bound(i).east > 179) && (bound(i).west < -179)
          %disp(i)
          poly = [bound(i).x, bound(i).y];
          polys = split_dateline(poly);
          if isempty(polys) || isempty(polys{1})
              continue
          end
          x=polys{1}(:,1);
          y=polys{1}(:,2);
          x(end)=x(1);
          y(end)=y(1);
          bound(i).x = x;
          bound(i).y = y;
          bound(i).east = max(bound(i).x);
          bound(i).west = min(bound(i).x);
          bound(i).north = max(bound(i).y);
          bound(i).south = min(bound(i).y);
          bound(i).n = length(bound(i).x);
          bound(i).level = 1;
          %plot(bound(i).x,bound(i).y,'-'); hold on
          
          for k = 2:length(polys)
              j=j+1;
              if isempty(polys{k})
                  continue
              end
              x=polys{k}(:,1);
              y=polys{k}(:,2);
              x(end)=x(1);
              y(end)=y(1);
              bound(j).x = x;
              bound(j).y = y;
              bound(j).east = max(bound(j).x);
              bound(j).west = min(bound(j).x);
              bound(j).north = max(bound(j).y);
              bound(j).south = min(bound(j).y);
              bound(j).n = length(bound(j).x);
              bound(j).level = 1;
              %plot(bound(j).x,bound(j).y,'-'); hold on
          end
        end
        %
        
    end

    % clean vertices with collinear points
    % for i = 1:length(bound)
    %     p = polyshape(bound(i).x,bound(i).y);
    %     bound(i).x = p.Vertices(:,1);
    %     bound(i).y = p.Vertices(:,2);
    %     bound(i).east = max(bound(i).x);
    %     bound(i).west = min(bound(i).x);
    %     bound(i).north = max(bound(i).y);
    %     bound(i).south = min(bound(i).y);
    %     bound(i).n = length(bound(i).x);
    % end

    Nu = 0;
    if (opt_poly == 1)
        [bound_user,Nu] = optional_bound(ref_dir,fname_poly);
    end
    if (Nu == 0)
        opt_poly = 0;
    end
end


%
% 1. Define type of run
%

if (strcmp(type,'rect'))
    
    %
    % Calculate the offset around the longitude 0
    %
    fname_bathy = [ref_dir,'/',ref_grid,'.nc'];
    f = netcdf.open(fname_bathy,'nowrite');
    dimid_lon = netcdf.inqDimID(f,xvar);
    [~,Nx_base]=netcdf.inqDim(f,dimid_lon);
    varid_lon = netcdf.inqVarID(f,xvar);
    lon_vals = double(netcdf.getVar(f,varid_lon));
    lon_range = [min(lon_vals(:)) max(lon_vals(:))];
    lons_base=lon_range(1);
    dx_base = diff(lon_range)/(Nx_base-1);
    rest=rem((lons_base-0)/dx_base,1);
    offset=rest*dx_base;
    
    % from lon,lat min,max: define the longitudes & latitudes arrays
    lon1d = single(lon_west:dx:lon_east);
    lat1d = single(lat_south:dy:lat_north);
    [lon,lat] = meshgrid(lon1d,lat1d);
    
    % curvilinear grid
elseif (strcmp(type,'curv'))
    fname_lat = [ref_dir, '/', fname, '.lat'];
    fname_lon = [ref_dir, '/', fname, '.lon'];
    lat=single(load(fname_lat));
    lon=single(load(fname_lon));
   
    % lambert conformal conic grid
elseif (strcmp(type,'lamb'))
    fname_bathy = [ref_dir,'/',ref_grid,'.nc'];
    f = netcdf.open(fname_bathy,'nowrite');
    dimid_lat = netcdf.inqDimID(f,'y');
    [~,Ny_base]=netcdf.inqDim(f,dimid_lat);
    varid_lat = netcdf.inqVarID(f,yvar);
    lat=single(netcdf.getVar(f,varid_lat))';
    dimid_lon = netcdf.inqDimID(f,'x');
    [~,Nx_base]=netcdf.inqDim(f,dimid_lon);
    varid_lon = netcdf.inqVarID(f,xvar);
    lon=single(netcdf.getVar(f,varid_lon))';
end

% 2. Generate the grid

fprintf(1,'.........Creating Bathymetry..................\n');

%load([data_dir,'/',fname,'_depth.mat']);
depth = generate_grid(type,lon,lat,ref_dir,ref_grid,LIM_BATHY,CUT_OFF,DRY_VAL,AVG,xvar,yvar,zvar);
%save([data_dir,'/',fname,'_depth.mat'],'depth');

% 3. Computing boundaries within the domain

fprintf(1,'.........Computing Boundaries..................\n');

% 3.a Set the domain big enough to include the cells along the edges of the grid
% /!\ The coordinates need to be defined so that they work with the coastal
% boundaries structure, which accepts only longitudes from -180° to 180°

px=[lon(1,:) lon(2:end,size(lon,2))' flip(lon(size(lon,1),1:end-1)) flip(lon(1:end-1,1))'];
py=[lat(1,:) lat(2:end,size(lat,2))' flip(lat(size(lat,1),1:end-1)) flip(lat(1:end-1,1))'];    


% 3.b Extract the boundaries from the GSHHS and the optional databases
%     The subset of polygons within the grid domain are stored in b and b_opt
%     for GSHHS and user defined polygons respectively

coastbound=1;


[b,N1] = compute_boundary(px,py,bound,MIN_DIST);
if (N1 == 0)
    fprintf(1,'[WARNING] no coastal boundaries found for this grid\n');
    coastbound=0;
end
if (opt_poly == 1)
    [b_opt,N2] = compute_boundary(px,py,bound_user);
end


% debug plot (WARNING : don't plot optionnal boundaries)
figure(9999); clf
title('boundary polygons')
for i = 1:N1
    plot(b(i).x,b(i).y,'-'); hold on
end



% 4. Set up Land - Sea Mask

% 4.a Set up initial land sea mask. The cells can either all be set to wet
%      or to make the code more efficient the cells marked as dry in
%      'generate_grid' can be marked as dry cells

m1 = ones(size(depth));
m1(depth == DRY_VAL) = 0;

% 4.b Split the larger GSHHS polygons for efficient computation of the
%     land sea mask. This step is optional  but recommended as it
%     significantly speeds up the computational time. Rule of thumb is to
%     set the limit for splitting the polygons at least 4-5 times dx,dy

% fprintf(1,'.........Splitting Boundaries........\n');
fprintf(1,'.........Splitting Boundaries is DISABLED DUE TO BUG IN SPLITTING........\n');
% only saves a few minutes...

SPLIT_LIM = 0;

if (coastbound)
    if (SPLIT_LIM>0)
        b_split = split_boundary(b,SPLIT_LIM,MIN_DIST);
    else
        b_split=b;
    end
end

% debug plot
if (coastbound &&  SPLIT_LIM > 0)
    figure(9998); clf
    for i = 1:numel(b_split)
        plot(b_split(i).x,b_split(i).y,'-'); hold on
    end
end

% 4.c Get a better estimate of the land sea mask using the polygon data sets.
%     (NOTE : This part will have to be commented out if cells above the
%      MSL are being marked as wet, like in inundation studies)

fprintf(1,'.........Cleaning Mask..................\n');

% GSHHS Polygons. If 'split_boundary' routine is not used then replace
% b_split with b

if (coastbound)
    m2 = clean_mask(lon,lat,m1,b_split,LIM_VAL,OFFSET);
    % Masking out regions defined by optional polygons
    if (opt_poly == 1 && N12 ~= 0)
        m3 = clean_mask(lon,lat,m2,b_opt,LIM_VAL,OFFSET);
    else
        m3 = m2;
    end
else
    m2=m1;
    m3=m2;
end


% 4.e Remove lakes and other minor water bodies

fprintf(1,'.........Separating Water Bodies..................\n');

[m4,mask_map] = remove_lake(m3,LAKE_TOL,IS_GLOBAL);


% 5. Generate sub - grid obstruction sets in x and y direction, based on
%    the final land/sea mask and the coastal boundaries

fprintf(1,'.........Creating Obstructions..................\n');

% The create_obstr function uses boundary structure with longitudes
% ranging from 0° to 360° -> need to shift the longitudes
if (coastbound)
    if (strcmp(type,'rect'))
        [sx1,sy1] = create_obstr(lon,lat,b,m4,OBSTR_OFFSET,OBSTR_OFFSET);
    elseif (strcmp(type,'curv'))
        [sx1,sy1] = create_obstr(lon,lat,b,m4,OBSTR_OFFSET,OBSTR_OFFSET);
    end
end


% 6. Output to ascii files for WAVEWATCH III

depth_scale = 1000;
obstr_scale = 100;

% create data
if ~exist(data_dir, 'dir'), mkdir(data_dir); end

% write bot file
d = round((depth)*depth_scale);
write_ww3file([data_dir,'/',fname,'.bot'],d);

% write mask file
write_ww3file([data_dir,'/',fname,'.mask'],m4);

% write obst file
if (coastbound)
    d1 = round((sx1)*obstr_scale);
    d2 = round((sy1)*obstr_scale);
    write_ww3obstr([data_dir,'/',fname,'.obst'],d1,d2);
end

% write meta file
if (strcmp(type,'rect'))
    write_ww3meta_file([data_dir,'/',fname],'RECT',lon,lat,1/depth_scale,...
        1/obstr_scale,'.bot','.obst','.mask');
else
    write_ww3meta_file([data_dir,'/',fname],'CURV',lon,lat,1/depth_scale,...
        1/obstr_scale,1.0,'.bot','.obst','.mask');
end


% 6. Vizualization (this part can be commented out if resources are limited)

%
%   Figures for tutorial
%
%   fig_dir=strrep(data_dir,'data','figures')
%   figure(1);
%   clf;
%   d=depth; d(d==DRY_VAL)=NaN;
%   pcolor(lon,lat,d); shading flat; colorbar
%   title('Bathymetry after generate\_grid function')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.bathymetry.png' ];
%   saveas(gcf, oname, 'png')
%
%   figure(1);clf;
%   for i = 1:numel(b)
%   plot(b(i).x,b(i).y);
%   hold on;
%   end
%   title('Boundary polygons before splitting')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.boundary_polygons.png' ];
%   saveas(gcf, oname, 'png')
%
%   figure(1);clf;
%   pcolor(lon,lat,m1);shading flat;caxis([0 3]);colorbar
%   title('Initial Land-Sea Mask')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.initial_mask.png' ];
%   saveas(gcf, oname, 'png')
%
%   figure(1);clf;
%   for i = 1:numel(b_split)
%   plot(b_split(i).x,b_split(i).y);
%   hold on;
%   end
%   title('Boundary polygons after splitting')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.boundary_polygons_split.png' ];
%   saveas(gcf, oname, 'png')
%
%   figure(1);clf;
%   pcolor(lon,lat,m2);shading flat;caxis([0 3]);colorbar
%   title('Mask after clean\_mask function')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.mask_after_cleaning.png' ];
%   saveas(gcf, oname, 'png')
%
%   figure(1);clf;
%   pcolor(lon,lat,m4);shading flat;caxis([0 3]);colorbar
%   title('Mask after remove\_lake')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.mask_after_remove_lake.png' ];
%   saveas(gcf, oname, 'png')
%
%   figure(1);clf;
%   pcolor(lon,lat,mask_map);shading flat;caxis([-1 6]);colorbar
%   title('Mask\_map')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.mask_map.png' ];
%   saveas(gcf, oname, 'png')
%
%   sx1(find(m4==0))=NaN;
%   sy1(find(m4==0))=NaN;
%   figure(1);clf;
%   pcolor(lon,lat,sx1);shading flat;caxis([0 1]);colorbar
%   title('Sx obstruction grid')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.Sx.png' ];
%   saveas(gcf, oname, 'png')
%
%   figure(2);clf;
%   pcolor(lon,lat,sy1);shading flat;caxis([0 1]);colorbar
%   title('Sy obstruction grid')
%   set(gca,'fontsize',14);
%   oname=[fig_dir '/' fname '.Sy.png' ];
%   saveas(gcf, oname, 'png')



%
% figure 1
%
figure(1);clf;subplot(2,1,1);
loc = find(m4 == 0);
d2 = depth;
d2(loc) = NaN;
pcolor(lon,lat,d2);
shading interp;colorbar;axis square;
title(['Bathymetry for ',fnamefig, ' from m4'],'fontsize',14);
set(gca,'fontsize',14);
clear d2;

%
% figure 2
%
subplot(2,1,2);
pcolor(lon,lat,m1);
shading flat;colorbar;axis square;
title(['Bathymetry mask for ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);

%
% figure 3
%
figure(3);clf;subplot(2,1,1);
pcolor(lon,lat,m2);
shading flat;colorbar;axis square;
title(['Land-Sea Mask m2 : after b\_split ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);

%
% figure 4
%
subplot(2,1,2);
d2 = mask_map;
loc2 = mask_map == -1;
d2(loc2) = NaN;
pcolor(lon,lat,d2);
shading flat;colorbar;axis square;
title(['Different water bodies for ',fnamefig],'fontsize',14);
caxis([-1 46])
set(gca,'fontsize',14);
clear d2;


%
% figure 5
%
figure(5);clf;subplot(2,1,1);
pcolor(lon,lat,m3);
shading flat;colorbar;axis square;
title(['Land-Sea Mask m3 : before removing lakes ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);

%
% figure 6
%
subplot(2,1,2);
pcolor(lon,lat,m4);
shading flat;colorbar;axis square;
title(['Final Land-Sea Mask ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);


if (coastbound)
    %
    % figure 7
    %
    figure(7);clf;subplot(2,1,1);
    d2 = sx1;
    d2(loc) = NaN;
    pcolor(lon,lat,d2);
    shading flat;colorbar;axis square;
    title(['Sx obstruction for ',fnamefig],'fontsize',14);
    set(gca,'fontsize',14);
    clear d2;
    
    %
    % figure 8
    %
    subplot(2,1,2);
    d2 = sy1;
    d2(loc) = NaN;
    pcolor(lon,lat,d2);
    shading flat;colorbar;axis square;
    title(['Sy obstruction for ',fnamefig],'fontsize',14);
    set(gca,'fontsize',14);
    clear d2;
end

toc
end

