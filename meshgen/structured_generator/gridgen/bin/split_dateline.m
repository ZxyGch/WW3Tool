function polys = split_dateline(poly)
    % Split polygon ONLY when it crosses the dateline (±180°).
    % poly = [lon,lat]  (open polygon; last point optional)
    %
    % Output: cell array of polygons (usually 1 or 2)

    lon = poly(:,1);
    lat = poly(:,2);

    % Close polygon
    lon = [lon; lon(1)];
    lat = [lat; lat(1)];

    polys = {};
    current = [];

    for i = 1:length(lon)-1
        x1 = lon(i);   y1 = lat(i);
        x2 = lon(i+1); y2 = lat(i+1);

        % Always append current point
        current = [current; x1 y1];

        % Δlon > 180° means dateline crossing
        dlon = x2 - x1;
        if abs(dlon) > 180

            % Compute intersection with ±180
            if dlon > 0
                xi =  180;
            else
                xi = -180;
            end
            % linear interpolation for latitude
            t = (xi - x1) / (x2 - x1);
            yi = y1 + t*(y2 - y1);

            % Insert the intersection
            current = [current; xi yi];

            % Save current polygon part
            polys{end+1} = current;

            % Start new part from intersection
            current = [xi yi];
        end
    end

    % Close last piece
    polys{end+1} = current;
end
