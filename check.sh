#!/bin/bash
for jar in program/*.jar; do
  echo -n "$jar: "
  
  # 提取第一个类文件
  first_class=$(unzip -Z1 "$jar" | grep '\.class$' | head -1)
  if [ -z "$first_class" ]; then
    echo "No class files found"
    continue
  fi
  
  # 检查类版本
  unzip -p "$jar" "$first_class" > temp.class 2>/dev/null
  major_version=$(javap -verbose temp.class 2>/dev/null | grep "major version" | awk '{print $NF}')
  rm -f temp.class
  
  # 转换版本号
  case $major_version in
    52) jdk="JDK 8";;
    55) jdk="JDK 11";;
    61) jdk="JDK 17";;
    65) jdk="JDK 21";;
	66) jdk="JDK 22";;
    *)  jdk="Unknown (major=$major_version)";;
  esac
  
  echo "$jdk"
done
