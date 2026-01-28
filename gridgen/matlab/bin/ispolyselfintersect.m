function tf = ispolyselfintersect(poly)
    % poly = [x(:), y(:)]  (open polygon; last point need not repeat first)
    % Returns true if polygon has crossing edges

    % close polygon
    P = [poly; poly(1,:)];

    n = size(P,1)-1;
    
    for i = 1:n
        a1 = P(i,:);
        a2 = P(i+1,:);

        for j = i+2:n
            % Skip adjacent edges (they share a vertex, not a crossing)
            if j == i || j == i-1 || (i == 1 && j == n)
                continue;
            end

            b1 = P(j,:);
            b2 = P(j+1,:);

            if segments_intersect(a1, a2, b1, b2)
                tf = true;
                return;
            end
        end
    end

    tf = false;
end


% ------- Segment intersection helpers -------

function tf = segments_intersect(a,b,c,d)
    tf = ccw(a,c,d) ~= ccw(b,c,d) && ccw(a,b,c) ~= ccw(a,b,d);
end

function tf = ccw(a,b,c)
    tf = (c(2)-a(2))*(b(1)-a(1)) > (b(2)-a(2))*(c(1)-a(1));
end
