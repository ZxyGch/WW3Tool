function new_mask = clear_Caspian_Sea_glob(bot,old_mask,Ny,Nx)

% Clean the zone corresponding to the Caspian Sea in global grid
% The test is done from longitude 43.0°E to longitude 62°E,
% and from latitude 35°N to latitude 52°N -> mask 1
minlon=-180;
maxlon= 359.5;
minlat= -78;
maxlat= 80;
dx=0.5;
dy=0.5;
ilonmin = (43-minlon)/dx
ilonmax = (62-minlon)/dx
ilatmin = (35-minlat)/dy
ilatmax = (52-minlat)/dy

for i=1:Nx
    for j=1:Ny
        if (i>ilatmin) && (i<ilatmax) && (j>ilonmin) && (j<ilonmax)
            if bot(i,j) < -28 % mean sea level for the Caspian Sea
                new_mask(i,j) = 1;
            else
                new_mask(i,j)=old_mask(i,j);
            end
        else
            new_mask(i,j) = old_mask(i,j);
        end
        
    end
end

figure(2500)
pcolor(old_mask)
shading flat
title('Old mask for glob\_30m')

figure(2501)
pcolor(bot)
shading flat
title('Depth for glob\_30m')

figure(3001)
pcolor(new_mask)
shading flat
title('New mask after adjustments in the Caspian Sea')

return;