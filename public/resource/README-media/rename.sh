#!/bin/bash

for file in *截屏*; do
    # 跳过不存在匹配的情况
    [ -e "$file" ] || continue

    # 新文件名（去掉“截屏”）
    newname="${file//截屏/}"

    # 避免覆盖已有文件
    if [ -e "$newname" ]; then
        echo "跳过（已存在）: $newname"
    else
        mv "$file" "$newname"
        echo "重命名: $file -> $newname"
    fi
done