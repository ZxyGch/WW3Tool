function tf = overlaps(poly1, poly2)
    % Fast polygon overlap test (no polybool, no geometry pkg)
    % poly format: [lon(:), lat(:)]

    % Quick bounding-box reject
    if ~bbox_overlap(poly1, poly2)
        tf = false;
        return;
    end

    % Check if any edges intersect
    if edges_intersect(poly1, poly2)
        tf = true;
        return;
    end

    % If no edge intersection, check containment
    % (polygon1 inside polygon2 or vice versa)
    if inpolygon(poly1(1,1), poly1(1,2), poly2(:,1), poly2(:,2)) || ...
       inpolygon(poly2(1,1), poly2(1,2), poly1(:,1), poly1(:,2))
        tf = true;
        return;
    end

    tf = false;
end


% ------------------------------------------
%      Helper: bounding box test
% ------------------------------------------
function tf = bbox_overlap(A, B)
    minA = min(A);  maxA = max(A);
    minB = min(B);  maxB = max(B);
    tf = ~(maxA(1) < minB(1) || maxB(1) < minA(1) || ...
           maxA(2) < minB(2) || maxB(2) < minA(2));
end


% ------------------------------------------
%      Helper: edge intersection test
% ------------------------------------------
function tf = edges_intersect(P, Q)
    P = [P; P(1,:)];   % close polygon
    Q = [Q; Q(1,:)];

    for i = 1:size(P,1)-1
        p1 = P(i,:);   p2 = P(i+1,:);
        for j = 1:size(Q,1)-1
            q1 = Q(j,:);  q2 = Q(j+1,:);
            if segments_intersect(p1,p2,q1,q2)
                tf = true;
                return;
            end
        end
    end
    tf = false;
end


% ------------------------------------------
%      Helper: segment intersection
% ------------------------------------------
function tf = segments_intersect(a,b,c,d)
    % Vector cross-based intersection test
    tf = (ccw(a,c,d) ~= ccw(b,c,d)) && (ccw(a,b,c) ~= ccw(a,b,d));
end


function tf = ccw(a,b,c)
    tf = (c(2)-a(2))*(b(1)-a(1)) > (b(2)-a(2))*(c(1)-a(1));
end
