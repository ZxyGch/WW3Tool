function create_boundary(fname_nml)

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
%| Create the polygon(s) which defined the active boundaries on the grid  |
%|                                                                        |
%| create_boundary(fname_nml)                                             |
%|                                                                        |
%| INPUT                                                                  |
%|  fname_nml   : Input namelist file name                                |
% -------------------------------------------------------------------------

% 0. Initialization
close all;
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

type = outgrid_nml.type;              % grid type 'rect' or 'curv'
fname = init_nml.fname;               % file name prefix
fname(fname=='''') = [];

[lon,lat] = read_ww3meta([in_dir,'/ww3_grid.nml_',fname]);  % read meta file

[Ny,Nx] = size(lon);
dx = (lon(1,Nx)-lon(1,1))/(Nx-1);
dy = (lat(Ny,1)-lat(1,1))/(Ny-1);
m = read_mask([in_dir,'/',fname,'.mask_nobound'],Nx,Ny); % read mask file

% 2. Read particulars from base grid (grid with which data has to be exchanged)

fnameb = init_nml.fnameb;
fnameb(fnameb=='''') = [];
[lonb,latb] = read_ww3meta([in_dir,'/ww3_grid.nml_',fnameb]);
[Nyb,Nxb] = size(lonb);
dxb = (lonb(1,Nxb)-lonb(1,1))/Nxb;
dyb = (latb(Nyb,1)-latb(1,1))/Nyb;
if (exist([in_dir,'/',fnameb,'.mask'], 'file') == 2)
    mb = read_mask([in_dir,'/',fnameb,'.mask'],Nxb,Nyb);
else
    mb = read_mask([in_dir,'/',fnameb,'.mask_nobound'],Nxb,Nyb);
end



% 3. Define the polygon that describes the computational area

plon=[];
plat=[];
plon_new=[];
plat_new=[];
j=1;
bound = init_nml.bound_select;         % boundary selection :
% 0 -> manually on the plot
% 1 -> automatically around the borders
% 2 -> from a .poly file
isglobalb = outgrid_nml.is_globalb;


% select polygon boundaries from file
if ( bound == 2 )
    bot = read_bot([in_dir,'/',fname,'.bot'],Nx,Ny);
    
    figure(7);
    clf;
    pcolor(lon,lat,bot./1000);
    shading flat;
    colorbar;
    caxis([-150,10]);
    title('Final Land-Sea Mask ','fontsize',14);
    set(gca,'fontsize',14);
    hold on;
    contour(lonb,latb,mb);
    
    %interactive generation of the polygon
    morepoly ='Y';
    np=0;
    pxall=[];
    pyall=[];
    npall=[];
    npoly=0;
    while (morepoly == 'Y')
        prompt='Give the name of your .poly file : ';
        fname=input(prompt);
        fid = fopen([in_dir,'/',fname,'.poly'],'r');
        [a1,count] = fscanf(fid,'%f');
        px = a1(1:2:count);
        py = a1(2:2:count);        
        px=round(px/dx)*dx;
        py=round(py/dy)*dy;
        npoly=npoly+1;
        %close the polygon
        np0=size(px,1);
        px(np0+1)=px(1);
        py(np0+1)=py(1);
        hold on;
        plot(px,py);
        npall=[npall np];
        pxall=[pxall' px']';
        pyall=[pyall' py']';
        m_tmp = modify_mask(m,lon,lat,mb,lonb,latb,isglobalb,px,py);         % save the mask info for every polygon in
        
        % Create boundary spec files for base grid resolution
        
        % Loop on the segments of the polygon
        for i=1:numel(px)-1
            % max number of elements along x or y for the current segment
            nelem=max(abs((px(i+1)-px(i))/dx),abs((py(i+1)-py(i))/dy) );
            % calculate the dx dy for the current segment
            pdx=(px(i+1)-px(i))/nelem;
            pdy=(py(i+1)-py(i))/nelem;
            % loop on the elements for the current segment
            for n=0:nelem-1
                plon=[plon px(i)+pdx*n];
                plat=[plat py(i)+pdy*n];
            end
        end
        
        % Keep only the active boundary points
        for i=1:numel(plon)
            % find the index lon & lat which match to the value of plon & plat
            % note : need to apply a scale factor and cast into integer to compare
            indx=find(abs(lon-plon(i)) < dx/2);
            indy=find(abs(lat-plat(i)) < dy/2);
            indcom=intersect(indx,indy);
            % keep only the plon & plat which are considered as active boundaries or
            % sea points depending on the precision of the polygon
            if (numel(indcom)>0)
                if (m_tmp(indcom(1))==2 || m_tmp(indcom(1))==1)
                    plon_new(j)=plon(i);
                    plat_new(j)=plat(i);
                    j=j+1;
                end
            end
        end
        
        % save the polygon if multiple ones                                                                  % a different variable
        if (npoly==1)
            m_new = m_tmp;
        else
            loc = find(m_tmp~=3);                                  % determine the active cells
            m_new(loc) = m_tmp(loc);                               % update the final mask for only those active cells
            clear loc;
        end
        
        morepoly = input('Add another polygon? Y/N [N]: ', 's');
        if isempty(morepoly)
            morepoly = 'N';
        end
    end
    
    px=pxall;
    py=pyall;
    np=npall;
    %save polygon_mask px py np
    hold on; plot(px,py)


% select polygon boundaries from grid contour
elseif ( bound == 1 )

    px=[lon(1,:) lon(2:end,size(lon,2))' flip(lon(size(lon,1),1:end-1)) flip(lon(1:end-1,1))'];
    py=[lat(1,:) lat(2:end,size(lat,2))' flip(lat(size(lat,1),1:end-1)) flip(lat(1:end-1,1))'];    
    
    m_new = modify_mask(m,lon,lat,mb,lonb,latb,isglobalb,px,py);   % save the mask info
    % for every polygon in
    % a different variable
    
    % Create boundary spec files for base grid resolution
    %TEST figure();pcolor(lon,lat,m_new);shading interp
    %TEST hold on;

    % Loop on each points of the polygon
    k=1;
    for i=1:numel(px)-1
        % Calculate distance from target to each grid point
        distance = sqrt((lat - py(i)).^2 + (lon - px(i)).^2);
        % Find minimum distance
        [min_dist, linear_idx] = min(distance(:));
        % Convert linear index to 2D indices
        [ilon, ilat] = ind2sub(size(lat), linear_idx);
        if (m_new(ilon,ilat)==2)
            plon_new(k)=px(i);
            plat_new(k)=py(i);
            %TEST plot(plon_new(k),plat_new(k),'rX')
            k=k+1;
        end
    end

    
% select polygon boundaries manually on the plot
elseif ( bound == 0 )
    bot = read_bot([in_dir,'/',fname,'.bot'],Nx,Ny);
    
    figure(7);
    clf;
    pcolor(lon,lat,bot./1000);
    shading flat;
    colorbar;
    caxis([-150,10]);
    title('Final Land-Sea Mask ','fontsize',14);
    set(gca,'fontsize',14);
    hold on;
    contour(lonb,latb,mb);
    
    %interactive generation of the polygon
    morepoly ='Y';
    np=0;
    pxall=[];
    pyall=[];
    npall=[];
    npoly=0;
    while (morepoly == 'Y')
        disp('Press Return key to terminate your polygon');
        [px,py]=ginput;
        px=round(px/dx)*dx;
        py=round(py/dy)*dy;
        npoly=npoly+1;
        %close the polygon
        np0=size(px,1);
        px(np0+1)=px(1);
        py(np0+1)=py(1);
        hold on;
        plot(px,py);
        npall=[npall np];
        pxall=[pxall' px']';
        pyall=[pyall' py']';
        m_tmp = modify_mask(m,lon,lat,mb,lonb,latb,isglobalb,px,py);         % save the mask info for every polygon in
        
        % Create boundary spec files for base grid resolution
        
        % Loop on the segments of the polygon
        for i=1:numel(px)-1
            % max number of elements along x or y for the current segment
            nelem=max(abs((px(i+1)-px(i))/dx),abs((py(i+1)-py(i))/dy) );
            % calculate the dx dy for the current segment
            pdx=(px(i+1)-px(i))/nelem;
            pdy=(py(i+1)-py(i))/nelem;
            % loop on the elements for the current segment
            for n=0:nelem-1
                plon=[plon px(i)+pdx*n];
                plat=[plat py(i)+pdy*n];
            end
        end
        
        % Keep only the active boundary points
        for i=1:numel(plon)
            % find the index lon & lat which match to the value of plon & plat
            % note : need to apply a scale factor and cast into integer to compare
            indx=find(abs(lon-plon(i)) < dx/2);
            indy=find(abs(lat-plat(i)) < dy/2);
            indcom=intersect(indx,indy);
            % keep only the plon & plat which are considered as active boundaries or
            % sea points depending on the precision of the polygon
            if (numel(indcom)>0)
                if (m_tmp(indcom(1))==2 || m_tmp(indcom(1))==1)
                    plon_new(j)=plon(i);
                    plat_new(j)=plat(i);
                    j=j+1;
                end
            end
        end
        
        % save the polygon if multiple ones                                                                  % a different variable
        if (npoly==1)
            m_new = m_tmp;
        else
            loc = find(m_tmp~=3);                                  % determine the active cells
            m_new(loc) = m_tmp(loc);                               % update the final mask for only those active cells
            clear loc;
        end
        
        morepoly = input('Add another polygon? Y/N [N]: ', 's');
        if isempty(morepoly)
            morepoly = 'N';
        end
    end
    
    px=pxall;
    py=pyall;
    np=npall;
    %save polygon_mask px py np
    hold on; plot(px,py)
    
end

% 6. Write out new mask file

write_ww3file([out_dir,'/',fname,'.mask'],m_new);

% 7. Replace mask_nobound by mask in ww3_grid.nml

filename = [in_dir,'/ww3_grid.nml_',fname]
file_content = fileread(filename);

% Replace all occurrences of old_str with new_str
new_content = strrep(file_content, 'mask_nobound', 'mask');

% Write the modified content back to the file
fid = fopen(filename, 'w');
if fid == -1
    error('Cannot open file for writing: %s', filename);
end

fputs(fid, new_content);
fclose(fid);


% 8. Vizualization (this step can be commented out if resources are limited)

figure(1);
clf;
pcolor(lon,lat,m);
shading interp;
colorbar;
title('Original Mask for grid','fontsize',14);
set(gca,'fontsize',14);

figure(2);
clf;
pcolor(lonb,latb,mb);
shading interp;
colorbar;
title('Mask for base grid','fontsize',14);
set(gca,'fontsize',14);

figure(3);
clf;
pcolor(lon,lat,m_new);
shading interp;
colorbar;
title('Final Mask for grid','fontsize',14);
set(gca,'fontsize',14);

% write the boundaries with a stride of the base grid resolution
fbound=fopen([out_dir,'/',fname,'.bound'],'w');
delta=round(dxb/dx);
figure(5);
clf;
pcolor(lon,lat,m_new);
shading interp;
colorbar;
title('Regular boundaries for grid','fontsize',14);
set(gca,'fontsize',14);
hold on;
for ipt = 1:delta:numel(plon_new)
    fprintf(fbound,' %+11.8f %+11.8f    BOUND%03d\n', ...
        plon_new(ipt), plat_new(ipt), ipt);
    plot(plon_new(ipt), plat_new(ipt), '*')
    text(plon_new(ipt), plat_new(ipt),int2str(ipt));
end

% write the boundaries with a stride of the output grid resolution
fbound=fopen([out_dir,'/',fname,'.fullbound'],'w');
figure(6);
clf;
pcolor(lon,lat,m_new);
shading interp;
colorbar;
title('Full boundaries for grid','fontsize',14);
set(gca,'fontsize',14);
hold on;
for ipt = 1:numel(plon_new)
    fprintf(fbound,' %+11.8f %+11.8f    BOUND%03d\n', ...
        plon_new(ipt), plat_new(ipt), ipt);
    plot(plon_new(ipt), plat_new(ipt), '*')
    text(plon_new(ipt), plat_new(ipt),int2str(ipt));
end

return
