function new_mask = clear_BS(bot,old_mask,Nx,Ny)
% Modification of the global mask
for i=1:Nx
    for j=1:Ny
        % Hudson Bay
        if (i > 255) && (i < 300) && (j > 170) && (j < 230)
            if bot(i,j) < 0 && old_mask(i,j) == 0
                new_mask(i,j)=1;
            else
                new_mask(i,j)=old_mask(i,j);
            end
        % Black Sea
        elseif (i>228) && (i<262) && (j>420) && (j<450)
            if bot(i,j) > 0 % && old_mask(i,j) == 1
                new_mask(i,j)=0;
            else
                new_mask(i,j)=1;
            end
        % Persian Gulf
        elseif (i>210) && (i<220) && (j>450) && (j<470)
            if bot(i,j) > 0 % && old_mask(i,j) == 1
                new_mask(i,j)=0;
            else
                new_mask(i,j)=1;
            end
        % Caspian Sea
        elseif (i > 228) && (i < 260) && (j > 448) && (j < 480)
            if bot(i,j) > 0 && old_mask(i,j) == 1
                new_mask(i,j)=0;
            else
                new_mask(i,j)=old_mask(i,j);
            end
        else
            new_mask(i,j)=old_mask(i,j);
        end
    end
end
figure(2000)
pcolor(new_mask)
shading flat
title('New mask after modification of the depth in the Caspian Sea')

return;
