function [bound_ingrid,Nb] = compute_boundary(px,py,bound,varargin)

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
%| Computes the shoreline polygons from the GSHHS database that lie within|
%| the grid domain, properly accounting for polygons that cross the domain|
%| The routine has been designed to work with coastal polygons by default.|
%| That can be changed by using a different boundary flag. See GSHHS      |
%| documentation (or below) for the meaning of the different flags        |
%| Use x and y polygon coordinates as input to handle both rect and curv  |
%| grids.                                                                 |
%|                                                                        |
%| [bound_ingrid,Nb] = compute_boundary(px,py,bound,[bflg])               |
%|                                                                        |
%| INPUT  
%|   px    : polygon for x coordinate counter clockwise
%|   py    : polygon for y coordinate counter clockwise
%|   bound : A data structure array of the basic polygons (The GSHHS      |
%|           polygons are stored as mat files with several different      |
%|           resolutions and the user should ensure that the files have   |
%|           been loaded before using this routine).                      |
%|                                                                        |
%|           The different available files are --                         |
%|             coastal_bound_ful.mat    -- Full resolution                |
%|                                         (188606 polygons)              |
%|		       coastal_bound_high.mat   -- High resolution        |
%|                                         (0.2 km; 153539 polygons)      |
%|		       coastal_bound_inter.mat  -- Intermediate resolution|
%|                                         (1 km; 41523 polygons)         |
%|		       coastal_bound_low.mat    -- Low resolution         |
%|                                         (5 km; 10769 polygons)         |
%|		       coastal_bound_coarse.mat -- Coarse resolution      |
%|                                         (25 km; 1866 polygons)         |
%|   min_val : threshold defining the minimum distance between the edge of|
%|             polygon and the inside/outside boundary.                   |
%|             A low value reduces computation time but can raise errors  |
%|             if the grid is too coarse. If the script crashes, consider |
%|             increasing the value.                                      |
%|                                                                        |
%|    bflg : Optional definition of flag type from the gshhs boundary     |
%|           database (1 = land; 2 = lake margin; 3 = in-lake island).    |
%|           If left blank, defaults to land (1).                         |
%|                                                                        |
%|	    Alternatively, a separate list of user defined polygons can   |
%|          be generated having the same fields as bound. One such list is|
%|	    "optional_coastal_polygons.mat" which is also distributed with|
%|          reference data. This is an ever growing list of water bodies  |
%|          that see very little wave action and for most practical       |
%|          purposes can be masked out as land.                           |
%|                                                                        |
%|          See also optional_bound.m which shows how the optional coastal|
%|          polygons are used                                             |
%|                                                                        |
%| OUTPUT                                                                 |
%|  bound_ingrid : Subset data structure array of polygons that lie inside|
%|                 the grid                                               |
%|  Nb           : Total number of polygons found that lie inside the grid|
%|                                                                        |
% -------------------------------------------------------------------------
narg=nargin;

% Determine if third input variable present (requesting inland features)
if narg == 5
    min_val_ori = varargin{1};
    bflg = varargin{2}; % Highest level admitted to provide shoreline data
elseif narg == 4
    min_val_ori = varargin{1};
    bflg = 1;
elseif narg == 3
    min_val_ori = 4; % Default value
    bflg = 1; % Normal application only continental bounds
else
    error('Too many input arguments, exiting')
end

lat_start = min(py);
lon_start = min(px);
lat_end = max(py);
lon_end = max(px);
cross_dateline = (lon_end - lon_start) > 180;
rect_domain = (~cross_dateline) && (numel(unique(px)) == 2) && (numel(unique(py)) == 2);

%@@@ Definitions

%@@@ Minimum distance between points (to avoid round off errors from points
%@@@ too close to each other)

eps = 1e-5;
epsdbl = 1e-4;

%@@@ Maximum distance between points. This is being defined so that we do
%@@@ not have large gaps between subsequent points of the final boundary
%@@@ polygon

MAX_SEG_LENGTH = 0.25;

%@@@ Slope and intercepts for each of the lines of the polygon bounding box

box_length=zeros(length(px)-1);
m_grid=zeros(length(px)-1);
c_grid=zeros(length(px)-1);
for i = 1:length(px)-1
    if (px(i+1)==px(i))
        m_grid(i)=inf;
        c_grid(i)=0;
    else
        p = polyfit(px(i:i+1),py(i:i+1),1);
        m_grid(i) = p(1);
        c_grid(i) = p(2);
    end
    if abs(m_grid(i))<epsdbl
        m_grid(i)=0;
    end
    if abs(px(i+1)-px(i))>180
        box_length(i) = sqrt((mod(px(i+1),360)-mod(px(i),360))^2+(py(i+1)-py(i))^2);
    else
        box_length(i) = sqrt((px(i+1)-px(i))^2+(py(i+1)-py(i))^2);
    end

end

%@@@ Initializing variables

N_orig = length(bound);
idx_list = 1:N_orig;
if N_orig > 0
    west_all = [bound.west];
    east_all = [bound.east];
    south_all = [bound.south];
    north_all = [bound.north];
    if cross_dateline
        in_lon = (east_all >= lon_start) | (west_all <= lon_end);
    else
        in_lon = ~(west_all > lon_end | east_all < lon_start);
    end
    in_lat = ~(south_all > lat_end | north_all < lat_start);
    in_bbox = in_lon & in_lat;
    idx_list = find(in_bbox);
end
N = length(idx_list);
fprintf(1,'Total boundaries: %d, candidates in bbox: %d\n', N_orig, N);
in_coord = 1;
itmp = 0;
truncated = zeros(1,N_orig);


% Create polyshape object for domain boundary
lon1=px;
lat1=py;
poly1 = [lon1(:), lat1(:)];

% Make sure it's closed (first point = last point)
if ~isequal(poly1(1,:), poly1(end,:))
    vertices = [poly1; poly1(1,:)];
end
%matlab poly1 = polyshape(lon1, lat1);

%@@@ Loop through all the boundaries in the database
for ii = 1:N
    i = idx_list(ii);

    %fprintf(1,'polygon:%d\n',i);
   
            
    %@@@ Limit boundaries to coastal type only. This flag needs to be
    %@@@ changed if interested in other boundaries. See GSHHS documentation
    %@@@ for boundary type flags
    
    %     if (bound(i).level == bflg )
    if (bound(i).level == bflg || bound(i).level ==2 )
        
        %@@@ Determine if boundary lies completely outside the domain
        if ((cross_dateline && (bound(i).west > lon_end && bound(i).east < lon_start)) || ...
                (~cross_dateline && (bound(i).west > lon_end || bound(i).east < lon_start)) || ...
                bound(i).south > lat_end || bound(i).north < lat_start)
            in_grid = 0;
            
        else
            skip_geom = 0;
            if rect_domain && bound(i).west >= lon_start && bound(i).east <= lon_end && ...
                    bound(i).south >= lat_start && bound(i).north <= lat_end
                in_grid = 1;
                vertices_inside = true(bound(i).n, 1);
                skip_geom = 1;
            end

            if ~skip_geom
                lon2 = bound(i).x;
                lat2 = bound(i).y;

            % test fprintf(1,'boundary polygon number :%d\n',i);

            % Create polyshape objects
            poly2 = [lon2(:), lat2(:)];

            % Make sure it's closed (first point = last point)
            if ~isequal(poly2(1,:), poly2(end,:))
                vertices = [poly2; poly2(1,:)];
            end
            %matlab poly2 = polyshape(lon2, lat2);



            % Check if polygon1 is completely outside polygon2
            % No vertices of poly1 should be inside poly2 AND no intersection
            %matlab vertices_inside = isinterior(poly1, poly2.Vertices(:,1), poly2.Vertices(:,2));
            %matlab has_intersection = overlaps(poly1, poly2);
            
            % Define polygon vertices for poly1 and poly2
            poly1_x = poly1(:, 1); % X-coordinates of poly1
            poly1_y = poly1(:, 2); % Y-coordinates of poly1
            poly2_x = poly2(:, 1); % X-coordinates of poly2
            poly2_y = poly2(:, 2); % Y-coordinates of poly2
            
                vertices_inside = inpolygon(poly2_x, poly2_y, poly1_x, poly1_y);
                if any(vertices_inside)
                    has_intersection = true;
                else
                    has_intersection = overlaps(poly1, poly2);
                end
                
                is_outside = ~any(vertices_inside) && ~has_intersection;

                if (is_outside == 0)
                    in_grid = 1;
                else
                    in_grid = 0;
                end
            end
        end

        %@@@ Ignore boundaries outside the domain
        
        if (in_grid)
          
            %@@@ Determine if boundary lies completely inside the domain
        
            if (all(vertices_inside))
                inside_grid = 1;
            else
                inside_grid = 0;
            end
            
            lev1 = bound(i).level;
            
            %@@@ Modify boundaries that are not completely inside domain
            
            if (~inside_grid)
                %fprintf(1,'modify on %d\n',i);
                
                %@@@ Determine the points of the boundary that are
                %@@@ inside/on/outside the bounding box
                
                [in_points,on_points] = inpolygon(bound(i).x,bound(i).y,px,py);
                
                loc1 = find(in_points == 1);
                loc2 = find(on_points == 1);
                
                %@@@ Ignore points that lie on the domain but neighboring
                %@@@ points do not
                
                for j = 1:length(loc2)
                    if (loc2(j) == 1)
                        p1 = bound(i).n;
                        p2 = loc2(j)+1;
                    elseif (loc2(j) == bound(i).n)
                        p1 = loc2(j)-1;
                        p2 = 1;
                    else
                        p1 = loc2(j)-1;
                        p2 = loc2(j)+1;
                    end
                    if (in_points(p1) == 0 && in_points(p2) == 0)
                        in_points(loc2(j)) = 0;
                    end
                end
                
                %@@@ Points of domain in the boundary
                
                domain_inb = inpolygon(px,py,bound(i).x,bound(i).y);
                loc_t = find(domain_inb == 1);
                domain_inb_lth = length(loc_t);
                
                if (isempty(loc1))
                    if (domain_inb_lth == length(px))
                        bound_ingrid(in_coord).x = px;
                        bound_ingrid(in_coord).y = py;
                        bound_ingrid(in_coord).n = length(px);
                        bound_ingrid(in_coord).west = lon_start;
                        bound_ingrid(in_coord).east = lon_end;
                        bound_ingrid(in_coord).north = lat_end;
                        bound_ingrid(in_coord).south = lat_start;
                        bound_ingrid(in_coord).height = lon_end - lon_start;
                        bound_ingrid(in_coord).width = lat_end - lat_start;
                        bound_ingrid(in_coord).level = lev1;
                        in_coord = in_coord + 1;
                    end
                    clear loc_t domain_inb;
                end
                
                %@@@ Loop through only if there are points inside the domain
                
                if (~isempty(loc1))
                    
                    n = bound(i).n;
                    
                    %@@@ Flag the points where the boundary moves from in
                    %@@@ to out of the domain as well as out to in
                    
                    in2out_count = 1;
                    out2in_count = 1;
                    
                    out2in = [];
                    in2out = [];
                    
                    for j = 1:bound(i).n-1
                        if (in_points(j) > 0 && in_points(j+1) == 0)
                            in2out(in2out_count) = j;
                            in2out_count = in2out_count+1;
                        end
                        if (in_points(j) == 0 && in_points(j+1) > 0)
                            out2in(out2in_count) = j;
                            out2in_count = out2in_count+1;
                        end
                    end
                    
                    in2out_count = in2out_count-1;
                    out2in_count = out2in_count-1;
                    if (in2out_count ~= out2in_count)
                        error('Error: mismatch in grid crossings, check boundary %d !! \n',i);
                    end
                    
                    %@@@ Crossing points are oriented to make sure we start
                    %@@@ from out to in
                    
                    if (in2out_count > 0 && in_points(1) > 0)
                        in2out_tmp = in2out;
                        for j = 1:in2out_count-1
                            in2out(j) = in2out_tmp(j+1);
                        end
                        in2out(in2out_count) = in2out_tmp(1);
                    end
                    
                    clear in2out_tmp;
                    
                    % debug plot
                    figure(666);
                    truncated(i)=1;
                    plot(bound(i).x,bound(i).y); hold on;
                    plot(bound(i).x(in2out(:)),bound(i).y(in2out(:)),'rx'); hold on;
                    plot(bound(i).x(out2in(:)),bound(i).y(out2in(:)),'ro'); hold on;
                    plot(px,py,'g-');

                    %@@@ For each in2out and out2in find a grid intersecting point
                    
                    clear in2out_gridbox in2out_gridboxdist in2out_xcross in2out_ycross;
                    clear out2in_gridbox out2in_gridboxdist out2in_xcross out2in_ycross;
                    
                    in2out_gridbox = zeros(in2out_count,1);
                    out2in_gridbox = zeros(out2in_count,1);
                    in2out_gridboxdist = zeros(in2out_count,1);
                    out2in_gridboxdist = zeros(out2in_count,1);
                    
                    for j = 1:in2out_count
                        
                        if(on_points(in2out(j)) == 1)
                            
                            x1 = bound(i).x(in2out(j));
                            y1 = bound(i).y(in2out(j));
                            
                            for k = 1:length(px)-1
                                
                                if (isinf(m_grid(k)))
                                    g = abs(x1-px(k));
                                else
                                    g = abs(m_grid(k)*x1+c_grid(k)-y1);
                                end
                                
                                if (g <= eps)
                                    in2out_gridbox(j) = k;
                                    if abs(px(k)-x1)>180
                                        dpxx1=mod(px(k),360)-mod(x1,360);
                                    else
                                        dpxx1=px(k)-x1;
                                    end
                                    in2out_gridboxdist(j) = k-1 + ...
                                        sqrt((dpxx1)^2+(py(k)-y1)^2)/box_length(k);
                                    break;
                                end
                                
                            end
                            
                            in2out_xcross(j) = NaN;
                            in2out_ycross(j) = NaN;
                            
                        else
                            
                            x1 = bound(i).x(in2out(j));
                            x2 = bound(i).x(in2out(j)+1);
                            y1 = bound(i).y(in2out(j));
                            y2 = bound(i).y(in2out(j)+1);
                            
                            if abs(x2-x1)>180
                                dx21=abs(mod(x2,360)-mod(x1,360));
                            else
                                dx21=abs(x2-x1);
                            end

                            if (dx21<epsdbl) % WRONG || abs(y2-y1)<epsdbl)
                                m = inf;
                                c = 0;
                            else
                                % set x2 at the same longitude side as x1
                                % if x1=179 and x2=-179.5, then x2=180.5
                                % it is needed for correct sign in polyfit
                                if (abs(x2-x1) > 90)
                                    x2 = x2+360;
                                    if (abs(x2-x1) > 90)
                                        x2 = x2-720;
                                    end
                                end
                                %fprintf(1,'polyfit on %d\n',i);
                                p = polyfit([x1 x2],[y1 y2],1);
                                m = p(1);
                                c = p(2);
                                if abs(m)<epsdbl
                                    m=0;
                                end
                            end
                            if abs(x1-x2)>180
                                d = sqrt((mod(x1,360)-mod(x2,360))^2+(y1-y2)^2);
                            else
                                d = sqrt((x1-x2)^2+(y1-y2)^2);
                            end
                            
                            for k = 1:length(px)-1
                                if (~isinf(m) && ~isinf(m_grid(k)))
                                    if (m ~= m_grid(k))
                                        x = (c_grid(k)-c)/(m-m_grid(k));
                                        y = m*x+c;
                                    else
                                        x = (c_grid(k)-c);
                                        y = m*x+c;
                                    end
                                elseif (isinf(m))
                                    x = x1;
                                    y = m_grid(k)*x+c_grid(k);
                                else
                                    x = px(k);
                                    y = m*x+c;
                                end
                                
                                if abs(x1-x)>180
                                    d1 = sqrt((mod(x1,360)-mod(x,360))^2+(y1-y)^2);
                                else
                                    d1 = sqrt((x1-x)^2+(y1-y)^2);
                                end

                                if abs(x-x2)>180
                                    d2 = sqrt((mod(x,360)-mod(x2,360))^2+(y-y2)^2);
                                else
                                    d2 = sqrt((x-x2)^2+(y-y2)^2);
                                end

                                if (abs(1-(d1+d2)/d) < 0.001)
                                    in2out_gridbox(j) = k;
                                    break;
                                end
                                % else
                                %      x = NaN;
                                %      y = NaN;
                                % end
                            end
                            if y <-90 || y > 90
                                error('boundary along latitude is wrong');
                            end
                            in2out_xcross(j) = x;
                            in2out_ycross(j) = y;

                            if abs(px(k)-x)>180
                                dpxx=mod(px(k),360)-mod(x,360);
                            else
                                dpxx=px(k)-x;
                            end

                            in2out_gridboxdist(j) = k-1 + ...
                                sqrt((dpxx)^2+(py(k)-y)^2)/box_length(k);
                            
                        end %@@@ corresponds to if(on_points(in2out(j)) == 1)
                        
                        if (on_points(out2in(j)+1) == 1)
                            
                            x1 = bound(i).x(out2in(j)+1);
                            y1 = bound(i).y(out2in(j)+1);
                            
                            for k = 1:length(px)-1
                                if (isinf(m_grid(k)))
                                    g = abs(x1-px(k));
                                else
                                    g = abs(m_grid(k)*x1+c_grid(k)-y1);
                                end

                                if (g <= eps)
                                    out2in_gridbox(j) = k;

                                    if abs(px(k)-x1)>180
                                        pxx1=mod(px(k),360)-mod(x1,360);
                                    else
                                        pxx1=px(k)-x1;
                                    end

                                    out2in_gridboxdist(j) = k-1 + ...
                                        sqrt((pxx1)^2+(py(k)-y1)^2)/box_length(k);
                                    break;
                                end
                            end
                            
                            out2in_xcross(j) = NaN;
                            out2in_ycross(j) = NaN;
                            
                        else
                            
                            x1 = bound(i).x(out2in(j));
                            x2 = bound(i).x(out2in(j)+1);
                            y1 = bound(i).y(out2in(j));
                            y2 = bound(i).y(out2in(j)+1);
                            
                            if abs(x2-x1)>180
                                dx2x1=abs(mod(x2,360)-mod(x1,360));
                            else
                                dx2x1=abs(x2-x1);
                            end

                            if (dx2x1<epsdbl) % WRONG || abs(y2-y1)<epsdbl)
                                m = inf;
                                c = 0;
                            else
                                % set x1 at the same longitude side as x2
                                % if x1=179 and x2=-179.5, then x1=-180.5
                                % it is needed for correct sign in polyfit
                                if (abs(x2-x1) > 90)
                                    x1 = x1+360;
                                    if (abs(x2-x1) > 90)
                                        x1 = x1-720;
                                    end
                                end
                                %fprintf(1,'polyfit on %d\n',i);
                                p = polyfit([x1 x2],[y1 y2],1);
                                m = p(1);
                                c = p(2);
                                if abs(m)<epsdbl
                                    m=0;
                                end
                            end

                            if abs(x1-x2)>180
                                d = sqrt((mod(x1,360)-mod(x2,360))^2+(y1-y2)^2);
                            else
                                d = sqrt((x1-x2)^2+(y1-y2)^2);

                            end
                            
                            % find the point of the polygon which is in
                            % between the point outside and inside the
                            % boundary polygon
                            for k = 1:length(px)-1
                                if (~isinf(m) && ~isinf(m_grid(k)))
                                    if (m ~= m_grid(k))
                                        x = (c_grid(k)-c)/(m-m_grid(k));
                                        y = m*x+c;
                                    else
                                        x = (c_grid(k)-c);
                                        y = m*x+c;
                                    end
                                elseif (isinf(m))
                                    x = x1;
                                    y = m_grid(k)*x+c_grid(k);
                                else
                                    x = px(k);
                                    y = m*x+c;
                                end
                                % test if x is on the same line 
                                % as d1 to d1
                                if abs(x1-x)>180
                                    d1 = sqrt((mod(x1,360)-mod(x,360))^2+(y1-y)^2);
                                else
                                    d1 = sqrt((x1-x)^2+(y1-y)^2);
                                end

                                if abs(x-x2)>180
                                    d2 = sqrt((mod(x,360)-mod(x2,360))^2+(y-y2)^2);
                                else
                                    d2 = sqrt((x-x2)^2+(y-y2)^2);
                                end

                                if (abs(1-(d1+d2)/d) < 0.001)
                                    out2in_gridbox(j) = k;
                                    break;
                                end
                                % else
                                %       x = NaN;
                                %       y = NaN;
                                % end
                            end
                            if y <-90 || y > 90
                                error('boundary along latitude is wrong');
                            end
                            out2in_xcross(j) = x;
                            out2in_ycross(j) = y;
                            % distance is actually the distance plus the
                            % point id 'k' in the polygon

                            if abs(px(k)-x)>180
                                dpxx=mod(px(k),360)-mod(x,360);
                            else
                                dpxx=px(k)-x;
                            end

                            out2in_gridboxdist(j) = k-1 + ...
                                sqrt((dpxx)^2+(py(k)-y)^2)/box_length(k);
                            
                        end %@@@ corresponds to if(on_points(out2in(j)) == 1)
                        
                    end     %@@@ end of j loop for all the intersection points
                    
                    %@@@ Loop through the intersection points
                    
                    if (in2out_count > 0)
                        
                        subseg_acc = zeros(in2out_count,1);
                        crnr_acc = 1 - domain_inb;
                        
                        % loop until find(...,1) is not empty
                        % which find the values at zero in subseg_acc
                        % and return the index of the first zero in the
                        % subseg_acc.
                        % *so it will loop until subseg_acc has no zero*
                        while(~isempty(find(subseg_acc == 0,1)))
                            
                            %@@@ Starting from the closest unaccounted
                            %@@@ segment
                            
                            min_pos = NaN;
                            min_val = max(out2in_gridboxdist)+eps;
                            for j = 1:in2out_count
                                if (subseg_acc(j) == 0)
                                    if (out2in_gridboxdist(j) < min_val)
                                        min_val = out2in_gridboxdist(j);
                                        min_pos = j;
                                    end
                                end
                            end
                            
                            j = min_pos;
                            
                            bound_ingrid(in_coord).x = [];
                            bound_ingrid(in_coord).y = [];
                            bound_ingrid(in_coord).n = 0;
                            bound_ingrid(in_coord).east = 0;
                            bound_ingrid(in_coord).west = 0;
                            bound_ingrid(in_coord).north = 0;
                            bound_ingrid(in_coord).south = 0;
                            bound_ingrid(in_coord).height = 0;
                            bound_ingrid(in_coord).width = 0;
                            
                            bound_x = [];
                            bound_y = [];
                            
                            if (j <= 0)
                                error('Error: no intersection point found. Consider increasing the MIN_DIST=%d parameter. max dist for this boundary is %d\n',min_val_ori,max(out2in_gridboxdist));
                            end
                            if (~isnan(out2in_xcross(j)))
                                bound_x = out2in_xcross(j);
                                bound_y = out2in_ycross(j);
                            end
                            
                            if ((out2in(j)+1) <= in2out(j))
                                bound_x = [bound_x;bound(i).x((out2in(j)+1):in2out(j))];
                                bound_y = [bound_y;bound(i).y((out2in(j)+1):in2out(j))];
                            else
                                bound_x = [bound_x;bound(i).x((out2in(j)+1):n);...
                                    bound(i).x(2:in2out(j))];
                                bound_y = [bound_y;bound(i).y((out2in(j)+1):n);...
                                    bound(i).y(2:in2out(j))];
                            end
                            
                            if (~isnan(in2out_xcross(j)))
                                bound_x = [bound_x;in2out_xcross(j)];
                                bound_y = [bound_y;in2out_ycross(j)];
                            end
                            
                            close_bound=0; %@@@ Flag initializing close boundary
                            
                            starting_edge = out2in_gridbox(j);
                            ending_edge = in2out_gridbox(j);
                            
                            subseg_acc(j) = 1;
                            
                            %@@@ Find the next closest segment going
                            %@@@ anti-clockwise
                            
                            seg_index = j;
                            
                            while (close_bound == 0)
                                
                                %@@@ Check if last segment and see if can
                                %@@@ proceed counter clockwise
                                
                                if (isempty(find(subseg_acc == 0,1)))
                                    for k = in2out_gridbox(seg_index):length(px)-1
                                        if (domain_inb(k+1) == 1 && crnr_acc(k+1) == 0)
                                            bound_x = [bound_x;px(k+1)];
                                            bound_y = [bound_y;py(k+1)];
                                            crnr_acc(k+1) = 1;
                                            ending_edge = k;
                                        else
                                            close_bound = 1;
                                            break;
                                        end
                                    end
                                    
                                    if (close_bound == 0)
                                        for k = 1:(in2out_gridbox(seg_index)-1)
                                            if (domain_inb(k+1) == 1 && crnr_acc(k+1) == 0)
                                                bound_x = [bound_x;px(k+1)];
                                                bound_y = [bound_y;py(k+1)];
                                                crnr_acc(k+1) = 1;
                                                ending_edge = k;
                                            else
                                                close_bound = 1;
                                                break;
                                            end
                                        end
                                        close_bound = 1;
                                    end
                                    
                                else
                                    
                                    curr_seg = seg_index;
                                    kstart = in2out_gridbox(curr_seg);
                                    start_dist = in2out_gridboxdist(curr_seg);
                                    min_pos = 0;
                                    min_val = 360+eps;
                                    
                                    %@@@ Check all segments
                                    
                                    for k1 = 1:in2out_count
                                        if (abs(out2in_gridboxdist(k1)-start_dist) > eps ...
                                                && abs(out2in_gridboxdist(k1)-start_dist) < min_val)
                                            min_pos = k1;
                                            min_val = abs(out2in_gridboxdist(k1)-start_dist);
                                        end
                                    end
                                    
                                    if (min_pos == 0)
                                        for k1 = 1:out2in_count
                                            if (out2in_gridboxdist(k1) < min_val)
                                                min_pos = k1;
                                                min_val = out2in_gridboxdist(k1);
                                            end
                                        end
                                    end
                                    
                                    if (min_pos <=0)
                                        fprintf(1,'min_pos : %d\n',min_pos);
                                    end

                                    if (subseg_acc(min_pos) == 1)
                                        close_bound = 1;
                                        ending_edge = in2out_gridbox(curr_seg);
                                    else
                                        kend = out2in_gridbox(min_pos);
                                        x_mid = [];
                                        y_mid = [];
                                        
                                        %@@@ If the boundary polygon crosses
                                        %@@@ the grid domain along different
                                        %@@@ domain edges then include the
                                        %@@@ common grid domain corner points
                                        
                                        
                                        if (kstart ~= kend)
                                            if (kstart < kend)
                                                for k1 = kstart:(kend-1)
                                                    if (domain_inb(k1+1) == 1 ...
                                                            && crnr_acc(k1+1) == 0)
                                                        x_mid = [x_mid;px(k1+1)];
                                                        y_mid = [y_mid;py(k1+1)];
                                                        crnr_acc(k1+1) = 1;
                                                    end
                                                end
                                            else
                                                for k1 = kstart:length(px)-1
                                                    if (domain_inb(k1+1) == 1 ...
                                                            && crnr_acc(k1+1) == 0)
                                                        x_mid = [x_mid;px(k1+1)];
                                                        y_mid = [y_mid;py(k1+1)];
                                                        crnr_acc(k1+1) = 1;
                                                    end
                                                end
                                                for k1 = 1:(kend-1)
                                                    if (domain_inb(k1+1) == 1 ...
                                                            && crnr_acc(k1+1) == 0)
                                                        x_mid = [x_mid;px(k1+1)];
                                                        y_mid = [y_mid;py(k1+1)];
                                                        crnr_acc(k1+1) = 1;
                                                    end
                                                end
                                            end
                                        end
                                        
                                        if (~isempty(x_mid))
                                            bound_x = [bound_x;x_mid];
                                            bound_y = [bound_y;y_mid];
                                        end
                                        
                                        %@@@ Adding the segment
                                        
                                        if (~isnan(out2in_xcross(min_pos)))
                                            bound_x = [bound_x;...
                                                out2in_xcross(min_pos)];
                                            bound_y = [bound_y;...
                                                out2in_ycross(min_pos)];
                                        end
                                        
                                        if ((out2in(min_pos)+1) <= in2out(min_pos))
                                            bound_x = [bound_x;...
                                                bound(i).x((out2in(min_pos)+1):...
                                                in2out(min_pos))];
                                            bound_y = [bound_y;...
                                                bound(i).y((out2in(min_pos)+1):...
                                                in2out(min_pos))];
                                        else
                                            bound_x = [bound_x;...
                                                bound(i).x((out2in(min_pos)+1):n);...
                                                bound(i).x(2:in2out(min_pos))];
                                            bound_y = [bound_y;...
                                                bound(i).y((out2in(min_pos)+1):n);...
                                                bound(i).y(2:in2out(min_pos))];
                                        end
                                        
                                        if (~isnan(in2out_xcross(min_pos)))
                                            bound_x = [bound_x;in2out_xcross(min_pos)];
                                            bound_y = [bound_y;in2out_ycross(min_pos)];
                                        end
                                        
                                        subseg_acc(min_pos) = 1;
                                        ending_edge = in2out_gridbox(min_pos);
                                        seg_index = min_pos;
                                    end
                                    
                                end
                                
                            end
                            
                            %@@@ Need to close the grid;
                            
                            if (ending_edge ~= starting_edge)
                                if (ending_edge < starting_edge)
                                    for k = ending_edge:(starting_edge-1)
                                        if (crnr_acc(k+1) == 0 && ...
                                                domain_inb(k+1) == 1)
                                            bound_x = [bound_x;px(k+1)];
                                            bound_y = [bound_y;py(k+1)];
                                            crnr_acc(k+1) = 1;
                                        end
                                    end
                                else
                                    for k = ending_edge:length(px)-1
                                        if (crnr_acc(k+1) == 0 && ...
                                                domain_inb(k+1) == 1)
                                            bound_x = [bound_x;px(k+1)];
                                            bound_y = [bound_y;py(k+1)];
                                            crnr_acc(k+1) = 1;
                                        end
                                    end
                                    for k =1:(starting_edge-1)
                                        if (crnr_acc(k+1) == 0 && ...
                                                domain_inb(k+1) == 1)
                                            bound_x = [bound_x;px(k+1)];
                                            bound_y = [bound_y;py(k+1)];
                                            crnr_acc(k+1) = 1;
                                        end
                                    end
                                end
                            end
                            
                            bound_x(end+1) = bound_x(1);
                            bound_y(end+1) = bound_y(1);
                            
                            %@@@ Making sure that the added points do not
                            %@@@ exceed max. defined seg length
                            
                            clear xt1 xt2 yt1 yt2 dist loc x_set y_set;
                            nsample = length(bound_x);
                            xt1 = bound_x(1:end-1);
                            yt1 = bound_y(1:end-1);
                            xt2 = bound_x(2:end);
                            yt2 = bound_y(2:end);
                            
                            if abs(xt2-xt1)>180
                                dist = sqrt((mod(xt2,360)-mod(xt1,360)).^2+(yt2-yt1).^2);
                            else
                                dist = sqrt((xt2-xt1).^2+(yt2-yt1).^2);
                            end

                            loc = find(dist > 2*MAX_SEG_LENGTH);

                            if (~isempty(loc))
                                x_set = bound_x(1:loc(1));
                                y_set = bound_y(1:loc(1));
                                nc = length(loc);
                                for k = 1:nc
                                    xp = bound_x(loc(k));
                                    yp = bound_y(loc(k));
                                    xn = bound_x(loc(k)+1);
                                    yn = bound_y(loc(k)+1);
                                    ns = floor(dist(loc(k))/MAX_SEG_LENGTH)-1;
                                    if (ns > 0)

                                        if abs(xp-xn)>180
                                            dxpxn=abs(mod(xp,360)-mod(xn,360));
                                        else
                                            dxpxn=abs(xp-xn);
                                        end

                                        if (dxpxn<epsdbl)
                                            x_set = [x_set;ones(ns,1)*xp];
                                            y_set = [y_set;(yp+sign(yn-yp)...
                                                *(1:ns)'*MAX_SEG_LENGTH)];
                                        else
                                            mth = atan2(yn-yp,xn-xp);
                                            x_set = [x_set;(xp+[1:ns]'...
                                                *MAX_SEG_LENGTH*cos(mth))];
                                            y_set = [y_set;(yp+[1:ns]'...
                                                *MAX_SEG_LENGTH*sin(mth))];
                                        end
                                    end
                                    x_set = [x_set;xn];
                                    y_set = [y_set;yn];
                                    if k == nc
                                        if ((loc(k)+1) < nsample)
                                            x_set = [x_set;bound_x((loc(k)+2:end))];
                                            y_set = [y_set;bound_y((loc(k)+2:end))];
                                        end
                                    else
                                        if ((loc(k)+1) < loc(k+1))
                                            x_set = [x_set;bound_x((loc(k)+2):loc(k+1))];
                                            y_set = [y_set;bound_y((loc(k)+2):loc(k+1))];
                                        end
                                    end
                                end
                            else
                                x_set = bound_x;
                                y_set = bound_y;
                            end
                            
                            %@@@ Setting up the boundary polygon
                            
                            bound_ingrid(in_coord).x = x_set;
                            bound_ingrid(in_coord).y = y_set;
                            bound_count = length(bound_ingrid(in_coord).x);
                            bound_ingrid(in_coord).n = bound_count;
                            bound_ingrid(in_coord).east = max(bound_ingrid(in_coord).x);
                            bound_ingrid(in_coord).west = min(bound_ingrid(in_coord).x);
                            bound_ingrid(in_coord).north = max(bound_ingrid(in_coord).y);
                            bound_ingrid(in_coord).south = min(bound_ingrid(in_coord).y);
                            if bound_ingrid(in_coord).south < -90-epsdbl
                                error('bound_ingrid(in_coord).south < -90 for polygon %d\n',in_coord);
                            end
                            if bound_ingrid(in_coord).north > 90+epsdbl
                                error('bound_ingrid(in_coord).north > 90 for polygon %d\n',in_coord);
                            end
                            bound_ingrid(in_coord).height = bound_ingrid(in_coord).north ...
                                - bound_ingrid(in_coord).south;
                            bound_ingrid(in_coord).width = bound_ingrid(in_coord).east ...
                                - bound_ingrid(in_coord).west;
                            bound_ingrid(in_coord).level = lev1;
                            
                            in_coord=in_coord+1;    %@@@ increment boundary
                            %@@@ counter
                            
                            crnr_acc(1) = crnr_acc(end);
                            
                        end         %@@@ corresponds to while loop that
                        %@@@ checks if all sections (subseg_acc)
                        %@@@ have been accounted for.
                        
                    end             %@@@ corresponds to if in2out_count > 0
                    
                end                 %@@@ corresponds to if statement checking
                %@@@ if there are boundary points inside
                %@@@ the domain
                
            else                     %@@@ boundary lies completely inside the grid
                
                %@@@ initializing and adding the boundary to the list
                bound_ingrid(in_coord).x = [];
                bound_ingrid(in_coord).y = [];
                bound_ingrid(in_coord).n = 0;
                bound_ingrid(in_coord).east = 0;
                bound_ingrid(in_coord).west = 0;
                bound_ingrid(in_coord).north = 0;
                bound_ingrid(in_coord).south = 0;
                bound_ingrid(in_coord).height = 0;
                bound_ingrid(in_coord).width = 0;
                bound_ingrid(in_coord).n = bound(i).n;
                bound_ingrid(in_coord).x = bound(i).x;
                bound_ingrid(in_coord).y = bound(i).y;
                bound_ingrid(in_coord).east = max(bound_ingrid(in_coord).x);
                bound_ingrid(in_coord).west = min(bound_ingrid(in_coord).x);
                bound_ingrid(in_coord).north = max(bound_ingrid(in_coord).y);
                bound_ingrid(in_coord).south = min(bound_ingrid(in_coord).y);
                bound_ingrid(in_coord).height = bound_ingrid(in_coord).north ...
                    - bound_ingrid(in_coord).south;
                bound_ingrid(in_coord).width = bound_ingrid(in_coord).east ...
                    - bound_ingrid(in_coord).west;
                bound_ingrid(in_coord).level = lev1;
                in_coord = in_coord+1;
                
            end     %@@@ corresponds to if statement that determines if boundary
            %@@@ lies partially/completely in domain
            
        end         %@@@ corresponds to if statement that determines if boundary
        %@@@ lies outside the domain
        
    end             %@@@ corresponds to if statement that determines boundary type
    
    %@@@ counter to keep tab on the level of processing
    
    itmp_prev = itmp;
    itmp = floor(ii/N*100);
    if (mod(itmp,5)==0 && itmp_prev ~= itmp && N > 100)
        fprintf(1,'Completed %d per cent of %d boundaries and found %d internal boundaries \n',...
            itmp,N,in_coord-1);
    end
    
end     %@@@ end of for loop that loops through all the GSHHS boundaries

Nb = in_coord-1;

if (Nb == 0)
    bound_ingrid(1) = -1;
end

fprintf('number of truncated polygons : \n'); fprintf('%d \n',length(truncated==1));
fprintf('list of truncated polygons : \n'); fprintf('%d \n',find(truncated==1));

return;
