function new_mask = clear_BS(bot,old_mask,Ny,Nx)

% Cleans ATNE mask taking into account the Black Sea and the Gulf of Botnie

for i=1:Nx
    for j=1:Ny
        % Black Sea
        if (i>96) && (i<135) && (j>228) && (j<245)
            if bot(i,j) < 0 % && old_mask(i,j) == 1
                new_mask(i,j)=3;
            else
                new_mask(i,j)=old_mask(i,j);
            end
        % Gulfe of Botnie (Norway)
        elseif (i>234) && (i<252) && (j>202) && (j<224)
            if bot(i,j) < 0
                new_mask(i,j) = 1;
            else
                new_mask(i,j) = old_mask(i,j);
            end
        else
            new_mask(i,j) = old_mask(i,j);
        end
    end
end
figure(2000)
pcolor(new_mask)
shading flat
title('New mask after adjustments in the Black Sea and Botnie Gulf')

return;
