function polys = split_dateline_360(poly)

  lon = poly(:,1);
  lat = poly(:,2);

  % close polygon if needed
  if lon(1) ~= lon(end) || lat(1) ~= lat(end)
    lon(end+1) = lon(1);
    lat(end+1) = lat(1);
  end

  polys = {};
  current = [lon(1), lat(1)];

  for i = 2:length(lon)

    lon1 = lon(i-1); lat1 = lat(i-1);
    lon2 = lon(i);   lat2 = lat(i);

    % check crossing of 180 meridian
    crosses = (lon1 < 180 && lon2 > 180) || ...
              (lon1 > 180 && lon2 < 180);

    if crosses
      % interpolate latitude at lon = 180
      t = (180 - lon1) / (lon2 - lon1);
      lat_cross = lat1 + t * (lat2 - lat1);

      % finish current polygon
      current(end+1,:) = [180, lat_cross];
      polys{end+1} = current;

      % start new polygon
      current = [180, lat_cross;
                 lon2, lat2];
    else
      current(end+1,:) = [lon2, lat2];
    end

  end

  if size(current, 1) > 2
    polys{end+1} = current;
  end

end
