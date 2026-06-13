function plot_bot_mask_obst(fname_nml)

mymap = [0.2 0.1 0.5
    0.1 0.5 0.8
    0.2 0.7 0.6
    0.8 0.7 0.3];

% 0. Initialization
set(groot,'DefaultFigureColormap',jet);

% 0.a Load namelist
init_nml = read_namelist(fname_nml,'GRID_INIT');
outgrid_nml = read_namelist(fname_nml,'OUTGRID');

% 0. Define paths

bin_dir = init_nml.bin_dir;         % matlab scripts location
ref_dir = init_nml.ref_dir;         % reference data location
in_dir  = init_nml.data_dir;        % input directory (for grid files)
out_dir = init_nml.data_dir;        % output directory (for grid files)

addpath(bin_dir,'-end');

% 1. Read particulars from grid to be modified

fname = init_nml.fname;                    % file name prefix
fname(fname=='''') = [];
fnamefig = strrep(fname,'_','\_');         % file name for figures
type = outgrid_nml.type;

% 2. Read meta
[lon,lat] = read_ww3meta([in_dir,'/ww3_grid.nml.',fname]);
[Ny,Nx] = size(lon);
dx = (lon(1,Nx)-lon(1,1))/Nx;
dy = (lat(Ny,1)-lat(1,1))/Ny;

% 3. Read and plot bot
mb = read_bot([in_dir,'/',fname,'.bot'],Nx,Ny);
mb = mb./1000;
loc = find(mb > 0);

figure();subplot(2,2,1);
d2 = mb;
d2(loc) = NaN;
if (strcmp(type,'rect'))
    pcolor(lon,lat,d2);
    shading interp;
else
    axesm eckert4
    geoshow(lat,lon,d2,'DisplayType','surface')
    framem
    gridm
end
colormap(mymap)
%shading interp;
clim([-4000,0]);
%clim([-150,10]);
title(['Bathymetry for ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);
clear d2;


% 3. Read and plot mask
%mm = read_mask([in_dir,'/',fname,'.mask'],Nx,Ny);
mm = read_mask([in_dir,'/',fname,'.mask_nobound'],Nx,Ny);

subplot(2,2,2);
if (strcmp(type,'rect'))
    pcolor(lon,lat,mm);
elseif (strcmp(type,'curv'))
    axesm eckert4
    geoshow(lat,lon,mm,'DisplayType','surface')
    framem
    gridm
end
shading flat;
colormap(mymap)
colorbar;
%shading interp;colorbar;axis square;
title(['Land-Sea Mask ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);

% 4. Read obstr
[mox,moy] = read_obstr([in_dir,'/',fname,'.obst'],Nx,Ny);
mox = mox./100;
moy = moy./100;

subplot(2,2,3);
d2 = mox;
d2(loc) = NaN;
if (strcmp(type,'rect'))
    pcolor(lon,lat,d2);
elseif (strcmp(type,'curv'))
    axesm eckert4
    geoshow(lat,lon,d2,'DisplayType','surface')
    framem
    gridm
end
shading flat;
colormap(mymap)
colorbar;
%shading interp;colorbar;axis square;
title(['Sx obstruction for ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);
clear d2;

subplot(2,2,4);
d2 = moy;
d2(loc) = NaN;
if (strcmp(type,'rect'))
    pcolor(lon,lat,d2);
elseif (strcmp(type,'curv'))
    axesm eckert4
    geoshow(lat,lon,d2,'DisplayType','surface')
    framem
    gridm
end
shading flat;
colormap(mymap)
colorbar;
%shading interp;colorbar;axis square;
title(['Sy obstruction for ',fnamefig],'fontsize',14);
set(gca,'fontsize',14);
clear d2;
