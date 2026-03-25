function bot = read_bot(fname,Nx,Ny)

fid = fopen(fname,'r');

for i =  1:Ny
    a = fscanf(fid,'%g',Nx);
    bot(i,:) = a;

end;
fclose(fid);

return