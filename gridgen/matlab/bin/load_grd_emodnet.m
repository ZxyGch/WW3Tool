function  [lon_sub,lat_sub,depth_sub] = load_grd(ref_dir,bathy_source,coord,dx,dy,coords,limit,cut_off,dry);
fid=fopen([bathy_source '.log'],'r');
%A=fscanf(fid,'%9f')
A=fscanf(fid,'%f')
fclose(fid);
nx=A(11);
ny=A(12);
nx
ny
fid=fopen([bathy_source '.grd'],'r');
%depth_base=-reshape(fread(fid,nx*ny,'float',0,'ieee-be'),ny,nx)
depth_base=reshape(fread(fid,nx*ny,'float',0,'n'),ny,nx);
lon_base0=linspace(A(3),A(4),nx);
lat_base0=linspace(A(1),A(2),ny);
status=fclose(fid);

min(lon_base0)
max(lon_base0)



dx_base = (round(3600.*(A(4)-A(3)))/(nx-1))/3600.;
dy_base = (round(3600.*(A(2)-A(1)))/(ny-1))/3600.;
Nx_base = nx;
Ny_base = ny;

lats = coord(1);
lons = coord(2);
late = coord(3);
lone = coord(4);


latss = lats;
lonss = lons;
lates = late;
lones = lone;


%@@@ Check the range of lattitudes and longitudes
if (coords ~= 0 && coords ~=1)
    fprintf(1,'incorrect value for coords\n');
    return;
end;

lats_base =A(1);
late_base = A(2); 
lons_base = A(3);
lone_base = A(4);

lats = coord(1);
lons = coord(2);
late = coord(3);
lone = coord(4);

if (lats < lats_base || lats > late_base || late < lats_base || late > late_base)
    fprintf(1,'ERROR : Lattitudes (%d,%d) beyond range (%d,%d) \n',lats,late,lats_base,late_base);
    return;
end;
  
if (lons < lons_base || lons > lone_base || lone < lons_base || lone > lone_base)
    fprintf(1,'ERROR : Longitudes (%d,%d) beyond range (%d,%d) \n',lons,lone,lons_base,lone_base);
    return;
end;

%@@@ Determine the starting and end points for extracting lattitude data from NETCDF

lat_start = floor(( (lats-2*dy) - lats_base)/dy_base);

if (lat_start < 1)
    lat_start = 1;
end;

 
lat_end = ceil(((late+2*dy) - lats_base)/dy_base) +1;

if (lat_end > Ny_base)
    lat_end = Ny_base;
end;


%@@@ Determine the starting and end points for extracting longitude data from NETCDF

%@@@ Code assumes that the longitude data in source file is stored in -180 to 180 range


lon_start = floor(((lons-2*dx) - lons_base)/dx_base);
lon_end = ceil(((lone+2*dx)- lons_base)/dx_base) +1;

if (lon_start < 1)
    lon_start = 1;
end;

if (lon_start > Nx_base)
    lon_start = Nx_base;
end;

if (lon_end < 1)
    lon_end = 1;
end;

if (lon_end >Nx_base)
    lon_end = Nx_base;
end;    


lat_base =lat_base0(lat_start:lat_end);                      %!!!! NETCDF DEPENDENCY !!!!!!!

if (coords == 1 & lone <= lons)
     lon1 = lon_base0(lon_start:Nx_base);                    %!!!! NETCDF DEPENDENCY !!!!!!!
     lon2 = lon_base0(2:lon_end);                            %!!!! NETCDF DEPENDENCY !!!!!!!

   % lon_base = [lon1;lon2];
     lon_base = [lon1;lon2];
    dep1 = f{'Depth'}(lat_start:lat_end,lon_start:Nx_base);       %!!!! NETCDF DEPENDENCY !!!!!!!
    dep2 = f{'Depth'}(lat_start:lat_end,2:lon_end);               %!!!! NETCDF DEPENDENCY !!!!!!!
    depth_base = [dep1 dep2];
else
    lon_base = lon_base0(lon_start:lon_end);                 %!!!! NETCDF DEPENDENCY !!!!!!!
    depth_base = depth_base(lat_start:lat_end,lon_start:lon_end); %!!!! NETCDF DEPENDENCY !!!!!!!
end;


fprintf(1,'read in the base bathymetry \n');

if (coords == 1)
    loc = find(lon_base < 0);
    lon_base(loc) = lon_base(loc)+360;
    if (lon_base(end) == 0)
        lon_base(end) = lon_base(end)+360;
    end;
end;

Nx0 = length(lon_base);
Ny0 = length(lat_base);

%@@@ Ratio of desired resolution to base resolution

ndx = round(dx/dx_base);
ndy = round(dy/dy_base);

%@@@ 2D averaging of bathymetry (only done if the desired grid is coarser than the base grid)
%@@@ Checks if grid cells wrap around in Longitudes. Does not do so for Lattitudes

if (ndx <= 1 & ndy <= 1)
    fprintf(1,'Target grid is too fine, returning base bathymetry \n');
    [tmp,lon_start] = min(abs(lon_base-lonss));
    [tmp,lon_end] = min(abs(lon_base-lones));
    [tmp,lat_start] = min(abs(lat_base-latss));
    [tmp,lat_end] = min(abs(lat_base-lates));
    lon_sub = lon_base(lon_start:lon_end);
    lat_sub = lat_base(lat_start:lat_end);
    depth_sub = depth_base(lat_start:lat_end,lon_start:lon_end);
    loc = find(depth_sub > cut_off);
    depth_sub(loc) = dry;
    clear loc;
    return;
end;


lon_sub = [lonss:dx:lones];
lat_sub = [latss:dy:lates];

Nx = length(lon_sub);
Ny = length(lat_sub);

if (ndx == 1 & ndy <= 2)
    fprintf(1,'Simple interpolation \n');
    dep1=zeros(lat_end-lat_start+1,Nx);
    for j = 1:lat_end-lat_start+1
       dep1(j,:)=interp1(lon_base,depth_base(j,:),lon_sub);
    end
    depth_sub=zeros(Ny,Nx);
        
    for i = 1:Nx
         depth_sub(:,i)=interp1(lat_base,depth_base(:,i),lat_sub);
    end
    loc = find(depth_sub > cut_off);
    depth_sub(loc) = dry;
    clear loc;
    return;
end;



fprintf(1,'Starting grid averaging ....\n');

itmp = 0;
Nb = Nx*Ny;

%@@@ 2D grid averaging over base bathymetry

for i = 1:Nx
    for j = 1:Ny

        %@@@ Determine the edges of each cell

        lon_start = lon_sub(i)-dx/2.0;
        lon_end = lon_sub(i)+dx/2.0;
        lat_start = lat_sub(j)-dy/2.0;
        lat_end = lat_sub(j)+dy/2.0;
        if (coords == 1)
            if (lon_start < 0)
                lon_start = lon_start + 360;
            end;
            if (lon_end > 360)
                lon_end = lon_end-360;
            end;
        else
            if (lon_start < -180)
                lon_start = lon_start + 360;
            end;
            if (lon_end > 180)
                lon_end = lon_end - 360;
            end;
        end;

        %@@@ Determine all the source points within this cell

        [tmp,lat_start_pos] = min(abs(lat_base-lat_start));
        [tmp,lat_end_pos] = min(abs(lat_base-lat_end));        
        [tmp,lon_start_pos] = min(abs(lon_base-lon_start));
        [tmp,lon_end_pos] = min(abs(lon_base-lon_end));

        %@@@ Average the depth over all the wet cells in source that lie within the cell
        %@@@ Cell is marked dry if the proportion of wet cells in source is less than specified
        %@@@ limit

        if (lon_start_pos < lon_end_pos)      %@@@ grid cells do not wrap around
            
            depth_tmp = depth_base(lat_start_pos:lat_end_pos,lon_start_pos:lon_end_pos);
            loc = find(depth_tmp <= cut_off);
            Nt = numel(depth_tmp);
            if (~isempty(loc))
                Ntt = length(loc);
                if (Ntt/Nt > limit)
                    depth_sub(j,i) = mean(depth_tmp(loc));
                else
                    depth_sub(j,i) = dry;
                end;
            else
                depth_sub(j,i) = dry;
            end;
            clear depth_tmp;
            clear loc;

	 else                                 %@@@ grid cell wraps around
 
            depth_tmp1 = depth_base(lat_start_pos:lat_end_pos,lon_start_pos:end);
            depth_tmp2 = depth_base(lat_start_pos:lat_end_pos,2:lon_end_pos);
            loc1 = find(depth_tmp1 <= cut_off);
            loc2 = find(depth_tmp2 <= cut_off);
            Nt = numel(depth_tmp1) + numel(depth_tmp2);
           
            if (~isempty(loc1) || ~isempty(loc2))
           % if (~isempty(loc1) && ~isempty(loc2))
            Ntt = length(loc1) + length(loc2);
                if (Ntt/Nt > limit)
                    if (isempty(loc1)) 
                        depth_sub(j,i) = mean(mean(depth_tmp2(loc2)));
                    elseif (isempty(loc2))  
                        depth_sub(j,i) = mean(mean(depth_tmp1(loc1)));
                    else
                        depth_sub(j,i) = mean(mean(depth_tmp1(loc1)) + mean(depth_tmp2(loc2)));
                    end;
                    %depth_sub(j,i) = mean(mean(depth_tmp1(loc1)) + mean(depth_tmp2(loc2)));
                    
                    
                else
                    depth_sub(j,i) = dry;
                end;
            else
                depth_sub(j,i) = dry;
            end;
            clear depth_tmp1;
            clear depth_tmp2;
            clear loc1;
            clear loc2;

        end;           %@@@ end of check to see if cell wraps around

        %@@@ Counter to check proportion of cells completed

        Nl = (i-1)*Ny+j;
        itmp_prev = itmp;
        itmp = floor(Nl/Nb*100);
        if (mod(itmp,5) == 0 & itmp_prev ~= itmp)
           fprintf(1,'Completed %d per cent of the cells \n',itmp);
        end;

    end;    %@@@ end of for loop through all the rows (lattitudes)

end;    %@@@ end of for loop through all the columns (longitudes)

clear lon_base;
clear lat_base;
clear depth_base;
