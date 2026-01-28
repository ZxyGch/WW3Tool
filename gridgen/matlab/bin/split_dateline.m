function polys = split_dateline(poly)
    % Split polygon ONLY when it crosses the dateline (±180°).
    % poly = [lon,lat]  (open polygon; last point optional)
    %
    % Output: cell array of polygons (usually 1 or 2)

    if isempty(poly)
        polys = {poly};
        return
    end

    lon = poly(:,1);
    lat = poly(:,2);
    lon = lon(:);
    lat = lat(:);

    if numel(lon) < 2
        polys = {poly};
        return
    end

    % Close polygon
    lonc = [lon; lon(1)];
    latc = [lat; lat(1)];

    dlon = diff(lonc);
    cross_idx = find(abs(dlon) > 180);
    if isempty(cross_idx)
        polys = {poly};
        return
    end

    nseg = length(lonc) - 1;
    nins = length(cross_idx);
    total_len = nseg + nins;

    new_lon = zeros(total_len, 1);
    new_lat = zeros(total_len, 1);
    split_pos = zeros(nins, 1);

    k = 1;
    c = 1;
    for i = 1:nseg
        x1 = lonc(i);   y1 = latc(i);
        x2 = lonc(i+1); y2 = latc(i+1);

        new_lon(k) = x1;
        new_lat(k) = y1;
        k = k + 1;

        d = x2 - x1;
        if abs(d) > 180
            if d > 0
                xi = 180;
            else
                xi = -180;
            end
            t = (xi - x1) / (x2 - x1);
            yi = y1 + t * (y2 - y1);

            new_lon(k) = xi;
            new_lat(k) = yi;
            split_pos(c) = k;
            k = k + 1;
            c = c + 1;
        end
    end

    new_lon = new_lon(1:k-1);
    new_lat = new_lat(1:k-1);

    polys = cell(nins + 1, 1);
    s = 1;
    for i = 1:nins
        e = split_pos(i);
        polys{i} = [new_lon(s:e) new_lat(s:e)];
        s = e;
    end
    polys{nins + 1} = [new_lon(s:end) new_lat(s:end)];
end
