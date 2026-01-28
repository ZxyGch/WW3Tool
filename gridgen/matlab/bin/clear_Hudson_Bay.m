function new_mask = clear_bay(bot,old_mask,Nx,Ny)

% Clean the Hudson Bay in glob_30m.mask
for i=1:Nx
    for j=1:Ny
        if (i > 255) && (i < 300) && (j > 170) && (j < 230)
            if bot(i,j) < 0 && old_mask(i,j) == 0 %-0.1 && bot(i,j) < 0.05
                new_mask(i,j)=1;
            else
                new_mask(i,j)=old_mask(i,j);
            end
        elseif (i>262) && (i<228) (j>413) && (j<494)
            if bot(i,j) > 0 && old_mask(i,j) == 1 %-0.1 && bot(i,j) < 0.05
                new_mask(i,j)=0;
            else
                new_mask(i,j)=old_mask(i,j);
            end
        else
            new_mask(i,j)=old_mask(i,j);
        end
    end
end
figure
pcolor(new_mask)
shading flat

return;
