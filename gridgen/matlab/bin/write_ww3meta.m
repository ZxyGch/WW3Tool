function [messg,errno] = write_ww3meta(output_dir,fname,fname_nml,gtype,lon,lat,varargin)

% -------------------------------------------------------------------------
%|                                                                        |
%|                    +----------------------------+                      |
%|                    | GRIDGEN          NOAA/NCEP |                      |
%|                    |                            |                      |
%|                    | Last Update :  29-Mar-2013 |                      |
%|                    +----------------------------+                      | 
%|                     Distributed with WAVEWATCH III                     |
%|                                                                        |
%|                 Copyright 2009 National Weather Service (NWS),         |
%|  National Oceanic and Atmospheric Administration.  All rights reserved.|
%|                                                                        |
%| DESCRIPTION                                                            |
%| Write the meta data associated with the grids generated in this        |
%| software. This data needs to be provided as input to ww3_grid.inp when |
%| generating the mod_def files for WAVEWATCH III. Note that the paths for|
%| the actual file locations as well as the file names may be changed from|
%| what is written out in the meta file                                   |
%|                                                                        |
%| [messg,errno] = ...                                                    |
%|        write_ww3meta(fname,gtype,lon,lat,N1,N2,N3(optional),N4,N5,N6)  |
%|                                                                        |
%| INPUT                                                                  |
%|  output_dir  : Output directory                                        |
%|  fname       : Output file name prefix                                 | 
%|  fname_nml   : namelist file name                                      |
%|  gtype       : Grid Type. Two options                                  |
%|                  'CURV' - For curvilinear grids                        |
%|                  'RECT' - For rectilinear grids                        |
%|  lon,lat     : Longitude array (x) and lattitude array (y) of the grid |
%|                 If gtype is 'rect' these are arrays and if it is       |
%|                 'curv' then they are 2D matrices                       |
%|  N1,N2,N3    : Scaling applied to bottom bathymetry data, obstruction  |
%|                grids and coordinate (x,y) grids respectively. The      |
%|                last number is optional and needed only for curvilinear |
%|                grids.                                                  |
%|  N4,N5,N6    : Optional extensions for labeling depth, mask and obs-   |
%|                truction files (must be equal to actual files).         |
%|                                                                        |
%| OUTPUT                                                                 |
%|  messg       : Error message. Is blank if no error occurs              |
%|  errno       : Error number. Is zero for succesful write               |
% -------------------------------------------------------------------------


fid = fopen([output_dir,'/ww3_grid.nml_',fname],'w');

[messg,errno] = ferror(fid);

if (errno ~= 0)
    fprintf(1,'!!ERROR!!: %s \n',messg);
    fclose(fid);
    return;
end;

init_nml    = read_namelist(fname_nml,'GRID_INIT');
outgrid_nml = read_namelist(fname_nml,'OUTGRID');
bathy_nml   = read_namelist(fname_nml,'BATHY_FILE');

% Grid type longitude/latitude or x/y
ref_dir  = init_nml.ref_dir;        % reference data location
ref_grid = bathy_nml.ref_grid;      % name of reference bathymetry file
xvar     = bathy_nml.xvar;          % variable name for longitudes in file

% COORD
fname_bathy = [ref_dir,'/',ref_grid,'.nc'];
f = netcdf.open(fname_bathy,'nowrite');
varid_lon = netcdf.inqVarID(f,xvar);
try
	lon_units = netcdf.getAtt(f,varid_lon,'units');
catch
	warning('No units attribute for spatial dimensions. Setting units to degree');
	lon_units = 'degree';
end
tf=~isempty(strfind(lon_units,'degree'));
switch tf
    case 1
        COORD='''SPHE''';
    case 0
        COORD='''CART''';
    otherwise
    fprintf(1,'!!ERROR!!: Unrecognized Grid Type\n');
    fclose(fid); 
    return;
end;

% CSTRNG
isglobal = outgrid_nml.is_global;
switch isglobal
  case 1
    CSTRNG='''SMPL''';
  case 0
    CSTRNG='''NONE''';
  otherwise
    fprintf(1,'!!ERROR!!: Unrecognized Grid Closure\n');
    fclose(fid); 
    return;
end;

Fmin = 0.0373;

fprintf(fid,'%s\n','&SPECTRUM_NML');
fprintf(fid,'%s%4.2f\n','  SPECTRUM%XFR         =  ',1.1);
fprintf(fid,'%s%6.4f\n','  SPECTRUM%FREQ1       =  ',Fmin);
fprintf(fid,'%s%d\n','  SPECTRUM%NK          =  ',32);
fprintf(fid,'%s%d\n','  SPECTRUM%NTH         =  ',24);
fprintf(fid,'%s\n','/');
fprintf(fid,'%s\n','');

fprintf(fid,'%s\n','&RUN_NML');
fprintf(fid,'%s\n','  RUN%FLCX             = T');
fprintf(fid,'%s\n','  RUN%FLCY             = T');
fprintf(fid,'%s\n','  RUN%FLCTH            = T');
fprintf(fid,'%s\n','  RUN%FLSOU            = T');
fprintf(fid,'%s\n','/');
fprintf(fid,'%s\n','');

minlon = min(min(lon));
maxlon = max(max(lon));
[Ny,Nx] = size(lon);
reslon = abs(maxlon-minlon)/Nx;
minlat = min(min(lat));
maxlat = max(max(lat));
dx = min(reslon * cos(maxlat*pi/180)*1852*60, reslon * cos(minlat*pi/180)*1852*60);
Tcfl = dx / (9.81 / (Fmin*4*pi) );
maxTcfl = 0.9 * Tcfl;
if maxTcfl>60
  maxTcfl = round(maxTcfl/60)*60;
else
  maxTcfl = round(maxTcfl/6)*6;
end

Tglob = 3*maxTcfl;
Tref = Tglob / 6;
Tsrc = 1;

fprintf(fid,'%s\n','&TIMESTEPS_NML');
fprintf(fid,'%s%5.2f\n','  TIMESTEPS%DTMAX      =  ',Tglob);
fprintf(fid,'%s%5.2f\n','  TIMESTEPS%DTXY       =  ',maxTcfl);
fprintf(fid,'%s%5.2f\n','  TIMESTEPS%DTKTH      =  ',Tref);
fprintf(fid,'%s%5.2f\n','  TIMESTEPS%DTMIN      =   ',Tsrc);
fprintf(fid,'%s\n','/');
fprintf(fid,'%s\n','');


fprintf(fid,'%s\n','&GRID_NML');
fprintf(fid,'%s%s%s\n','  GRID%NAME            =  ''',init_nml.fname,'''');
fprintf(fid,'%s%s%s\n','  GRID%NML             =  ''namelists_',init_nml.fname,'.nml''');
fprintf(fid,'%s%s%s\n','  GRID%TYPE            =  ''',gtype,'''');
fprintf(fid,'%s%s\n','  GRID%COORD           =  ',COORD);
fprintf(fid,'%s%s\n','  GRID%CLOS            =  ',CSTRNG);
fprintf(fid,'%s%5.2f\n','  GRID%ZLIM            =  ',-0.10);
fprintf(fid,'%s%5.2f\n','  GRID%DMIN            =  ',2.5);
fprintf(fid,'%s\n','/');
fprintf(fid,'%s\n','');


switch gtype
   case 'RECT'
        [Ny,Nx] = size(lon);
        fprintf(fid,'%s\n','&RECT_NML');
        fprintf(fid,'%s%d\n','  RECT%NX              =  ',Nx);
        fprintf(fid,'%s%d\n','  RECT%NY              =  ',Ny);
        fprintf(fid,'%s\n','!');
        fprintf(fid,'%s%15.12f\n','  RECT%SX              =  ',(lon(1,2)-lon(1,1)));
        fprintf(fid,'%s%15.12f\n','  RECT%SY              =  ',(lat(2,1)-lat(1,1)));
        %fprintf(fid,'%s%5.2f\n','  RECT%SF              =  ',1.);
        fprintf(fid,'%s%8.4f\n','  RECT%X0              =  ',lon(1,1));        
        fprintf(fid,'%s%8.4f\n','  RECT%Y0              =  ',lat(1,1));
        %fprintf(fid,'%s%8.4f\n','  RECT%SF0             =  ',1.);        
        fprintf(fid,'%s\n','/');
       
    case 'CURV'
        N3 = varargin{3};
        [Ny,Nx] = size(lon);
        fprintf(fid,'%s\n','&CURV_NML');
        fprintf(fid,'%s%d\n','  CURV%NX               =  ',Nx);
        fprintf(fid,'%s%d\n','  CURV%NY               =  ',Ny);
        fprintf(fid,'%s\n','!');
        fprintf(fid,'%s%5.2f\n','  CURV%XCOORD%SF        =  ',N3);
        fprintf(fid,'%s%s\n','  CURV%XCOORD%FILENAME  =  ',['''',fname,'.lon','''']);
        fprintf(fid,'%s\n','!');
        fprintf(fid,'%s%5.2f\n','  CURV%YCOORD%SF        =  ',N3);
        fprintf(fid,'%s%s\n','  CURV%YCOORD%FILENAME  =  ',['''',fname,'.lat','''']);
        fprintf(fid,'%s\n','/');
        
    otherwise
       fprintf(1,'!!ERROR!!: Unrecognized Grid Type\n');
       fclose(fid);
       return;
end;
fprintf(fid,'%s\n','');


if nargin <= 9
 ext1='.bot';
 ext2='.obst';
 ext3='.mask';
else
 ext1=varargin{4};
 ext2=varargin{5};
 ext3=varargin{6};
end

N1 = varargin{1};
fprintf(fid,'%s\n','&DEPTH_NML');
fprintf(fid,'%s%5.3f\n','  DEPTH%SF             = ',N1);
fprintf(fid,'%s%s\n','  DEPTH%FILENAME       = ',['''',fname,ext1,'''']);
fprintf(fid,'%s\n','/');
fprintf(fid,'%s\n','');

fprintf(fid,'%s\n','&MASK_NML');
fprintf(fid,'%s%s\n','  MASK%FILENAME        = ',['''',fname,ext3,'_nobound','''']);
fprintf(fid,'%s\n','/');
fprintf(fid,'%s\n','');

N2 = varargin{2};
fprintf(fid,'%s\n','&OBST_NML');
fprintf(fid,'%s%5.3f\n','  OBST%SF              = ',N2);
fprintf(fid,'%s%s\n','  OBST%FILENAME        = ',['''',fname,ext2,'''']);
fprintf(fid,'%s\n','/');
fprintf(fid,'%s\n','');


fclose(fid);

return;
