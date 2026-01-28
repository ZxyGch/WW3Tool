function bound_ingrid = split_boundary(bound,lim,varargin)

% -------------------------------------------------------------------------
%|                                                                        |
%|                    +----------------------------+                      |
%|                    | GRIDGEN          NOAA/NCEP |                      |
%|                    |                            |                      |
%|                    | Last Update :  23-Oct-2012 |                      |
%|                    +----------------------------+                      |
%|                     Distributed with WAVEWATCH III                     |
%|                                                                        |
%|                 Copyright 2009 National Weather Service (NWS),         |
%|  National Oceanic and Atmospheric Administration.  All rights reserved.|
%|                                                                        |
%| DESCRIPTION                                                            |
%| This function splits up large boundary segments into smaller ones so   |
%| that they are more managable                                           |
%|                                                                        |
%| bound_ingrid = split_boundary(bound,lim,[bflg])                        |
%|                                                                        |
%| INPUT                                                                  |
%|  bound   : Data structure array of boundary polygons that lie inside   |
%|            grid domain                                                 |
%|  lim     : Limiting size to determine if a polygon needs to be split   |
%|  min_val : Optional argument. Threshold defining the minimum distance  |
%|            between the edge of polygon and the inside/outside boundary.|
%|            A low value reduces computation time but can raise errors   |
%|            if the grid is too coarse. If the script crashes, consider  |
%|            increasing the value.                                       |
%|                                                                        |
%| OUTPUT                                                                 |
%| bound_ingrid : A new data structure of boundary polygons where the     |
%|                larger polygons have been split up to more managable    |
%|                smaller sizes                                           |
%|                                                                        |
% -------------------------------------------------------------------------

narg=nargin;

% Determine if third input variable present (requesting inland features)
if narg == 3
    min_val = varargin{1};
elseif narg == 2
    min_val = 4; % Default value
else
  error('Wrong number of input arguments, exiting')
end  

eps = 1e-5;

N = length(bound);
in_coord = 1;
bound_ingrid = [];
itmp = 0;

for i = 1:N  % Loop on polygons previously obtained with compute_boundary
    % if the considered polygon is larger than the limit set by 'lim':
    if (bound(i).width > lim || bound(i).height > lim)
        low = floor(bound(i).west);
        high = ceil(bound(i).east);
        x_axis = [low:lim:high]; % create x array dividing the polygon into subsets
        if x_axis(end) < high
            x_axis(end+1) = high;
        end
        low = floor(bound(i).south);
        high = ceil(bound(i).north);
        y_axis = [low:lim:high]; % create y array dividing the polygon into subsets
        if y_axis(end) < high
            y_axis(end+1) = high;
        end
        
        Nx = length(x_axis);
        Ny = length(y_axis);
        % Loop on each "sub-polygon" & run compute_boundary for each of
        % them; store the results in one single array bound_ingrid
        for lx = 1:Nx-1
            for ly = 1:Ny-1
                lat_start = y_axis(ly);
                lon_start = x_axis(lx);
                lat_end = y_axis(ly+1);
                lon_end = x_axis(lx+1);
                
                %coord = [lat_start lon_start lat_end lon_end];
		px = [lon_start lon_end lon_end lon_start lon_start];
		py = [lat_start lat_start lat_end lat_end lat_start];
                %px=[lon(1,:) lon(:,size(lon,2))' flip(lon(size(lon,1),:)) flip(lon(:,1))' lon(1,1)];
                %py=[lat(1,:) lat(:,size(lat,2))' flip(lat(size(lat,1),:)) flip(lat(:,1))' lat(1,1)];
                % fprintf(1,'compute boundary of splitted polyon %d\n', i);
                [bt,Nb] = compute_boundary(px, py, bound(i), min_val, bound(i).level); 
                if (Nb > 0)
                    bound_ingrid = [bound_ingrid bt];
                    in_coord = in_coord + Nb;
                end
                clear bt;
            end
        end;
    else % if current polygon does not need subdivision
        if (isempty(bound_ingrid))
            bound_ingrid = bound(i); % append current polygon to output array
        else
            bound_ingrid(in_coord) = bound(i);
        end;
        in_coord = in_coord+1;
    end;
    itmp_prev = itmp;
    itmp = floor(i/N*100);
    if (mod(itmp,5)==0 && itmp_prev ~= itmp && N > 100)
        fprintf(1,'Completed %d per cent of %d boundaries and split into %d boundaries \n',...
            itmp,N,in_coord-1);
    end
end

return;
